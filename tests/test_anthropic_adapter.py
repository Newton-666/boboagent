"""GitHub #9 — Anthropic Messages adapter vs OpenAI chat/completions.

Audit finding: provider 登记 Anthropic 为 /v1/messages，llm_caller 却发
OpenAI chat/completions + tool_calls。本文件：
  1. 核验登记与运行时选择一致
  2. 请求/响应/工具调用形态对齐（可复现，真 HTTP 假服务端）
  3. OpenRouter（含 anthropic/claude-* 模型）不进适配器、不回归
"""
import json
import os
import socket
import threading
import time

import pytest
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

from core.anthropic_adapter import (
    ANTHROPIC_STREAM_DONE,
    AnthropicStreamState,
    anthropic_event_to_openai_chunk,
    build_anthropic_headers,
    from_anthropic_response,
    to_anthropic_payload,
    to_anthropic_tools,
    uses_anthropic_protocol,
)
from core.llm_caller import create_llm_caller
from core.provider import PROVIDERS, get_provider

os.environ.setdefault("NO_PROXY", "127.0.0.1,localhost")
os.environ.setdefault("no_proxy", "127.0.0.1,localhost")

WEB_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "Search the web",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
}

OPENAI_TOOL_ROUND = [
    {"role": "system", "content": "You are bobo."},
    {"role": "user", "content": "search python"},
    {
        "role": "assistant",
        "content": None,
        "tool_calls": [{
            "id": "toolu_01ABC",
            "type": "function",
            "function": {
                "name": "web_search",
                "arguments": '{"query": "python"}',
            },
        }],
    },
    {
        "role": "tool",
        "tool_call_id": "toolu_01ABC",
        "content": "Python is a programming language.",
    },
]


# ── 1. registry vs runtime selection ───────────────────────────────


class TestProtocolSelection:
    def test_all_providers_declare_protocol(self):
        for name, cfg in PROVIDERS.items():
            proto = cfg.get("protocol")
            assert proto in ("openai_chat", "anthropic_messages"), (
                f"{name} protocol 非法: {proto!r}"
            )

    def test_anthropic_registry_is_messages(self):
        cfg = get_provider("anthropic")
        assert cfg["protocol"] == "anthropic_messages"
        assert cfg["base_url"].endswith("/v1/messages")
        assert "/chat/completions" not in cfg["base_url"]
        assert uses_anthropic_protocol(cfg, cfg["base_url"]) is True

    def test_openrouter_stays_openai_even_for_claude_models(self):
        cfg = get_provider("openrouter")
        assert cfg["protocol"] == "openai_chat"
        assert "/chat/completions" in cfg["base_url"]
        assert "anthropic/claude-sonnet-4" in cfg["models"]
        assert uses_anthropic_protocol(cfg, cfg["base_url"]) is False

    def test_chat_completions_url_wins_over_anthropic_proto(self):
        """API_BASE_URL 改成 OpenAI 兼容代理时，禁止误转 Messages。"""
        proto = {"protocol": "anthropic_messages"}
        url = "https://openrouter.ai/api/v1/chat/completions"
        assert uses_anthropic_protocol(proto, url) is False

    def test_messages_url_without_proto_still_adapts(self):
        """spawn_worker 等漏传 provider_proto 时，靠 URL 仍走适配器。"""
        assert uses_anthropic_protocol(
            None, "https://api.anthropic.com/v1/messages") is True

    def test_openai_compat_urls_never_adapt(self):
        for url in (
            "https://api.deepseek.com/v1/chat/completions",
            "https://api.openai.com/v1/chat/completions",
            "http://127.0.0.1:9/v1/chat/completions",
        ):
            assert uses_anthropic_protocol(None, url) is False
            assert uses_anthropic_protocol({"protocol": "openai_chat"}, url) is False


# ── 2. request / response / tool-call shape (pure) ─────────────────


class TestRequestConversion:
    def test_system_split_and_tool_round(self):
        payload = to_anthropic_payload({
            "model": "claude-sonnet-4-20250514",
            "messages": OPENAI_TOOL_ROUND,
            "temperature": 0.3,
            "max_tokens": 1024,
            "tools": [WEB_SEARCH_TOOL],
            "tool_choice": "auto",
        })
        assert payload["model"] == "claude-sonnet-4-20250514"
        assert payload["system"] == "You are bobo."
        assert payload["max_tokens"] == 1024
        assert "tool_choice" in payload
        assert payload["tool_choice"] == {"type": "auto"}
        assert "messages" in payload
        # no OpenAI-only keys
        assert "tool_calls" not in json.dumps(payload)
        roles = [m["role"] for m in payload["messages"]]
        assert roles[0] == "user"
        assert "assistant" in roles
        # tool role is gone; results are user + tool_result
        assert "tool" not in roles
        assistant = next(m for m in payload["messages"] if m["role"] == "assistant")
        uses = [b for b in assistant["content"] if b["type"] == "tool_use"]
        assert len(uses) == 1
        assert uses[0]["id"] == "toolu_01ABC"
        assert uses[0]["name"] == "web_search"
        assert uses[0]["input"] == {"query": "python"}
        user_with_result = payload["messages"][-1]
        assert user_with_result["role"] == "user"
        results = [b for b in user_with_result["content"] if b["type"] == "tool_result"]
        assert results[0]["tool_use_id"] == "toolu_01ABC"
        assert "Python is a programming language" in results[0]["content"]

    def test_parallel_tool_results_merge_into_one_user(self):
        messages = [
            {"role": "user", "content": "do two things"},
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "a", "type": "function",
                 "function": {"name": "web_search", "arguments": '{"query":"a"}'}},
                {"id": "b", "type": "function",
                 "function": {"name": "web_search", "arguments": '{"query":"b"}'}},
            ]},
            {"role": "tool", "tool_call_id": "a", "content": "A"},
            {"role": "tool", "tool_call_id": "b", "content": "B"},
        ]
        payload = to_anthropic_payload({"model": "m", "messages": messages, "max_tokens": 10})
        roles = [m["role"] for m in payload["messages"]]
        assert roles == ["user", "assistant", "user"]
        results = payload["messages"][-1]["content"]
        assert [b["tool_use_id"] for b in results] == ["a", "b"]

    def test_tools_schema_openai_to_anthropic(self):
        tools = to_anthropic_tools([WEB_SEARCH_TOOL])
        assert tools == [{
            "name": "web_search",
            "description": "Search the web",
            "input_schema": WEB_SEARCH_TOOL["function"]["parameters"],
        }]

    def test_headers_are_anthropic_not_bearer(self):
        headers = build_anthropic_headers("sk-ant-test")
        assert headers["x-api-key"] == "sk-ant-test"
        assert headers["anthropic-version"] == "2023-06-01"
        assert "Authorization" not in headers


class TestResponseConversion:
    def test_text_and_tool_use(self):
        body = from_anthropic_response({
            "id": "msg_1",
            "type": "message",
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Let me look that up."},
                {"type": "tool_use", "id": "toolu_01ABC",
                 "name": "web_search", "input": {"query": "python"}},
            ],
            "stop_reason": "tool_use",
            "usage": {"input_tokens": 12, "output_tokens": 30},
        })
        msg = body["choices"][0]["message"]
        assert msg["content"] == "Let me look that up."
        assert msg["tool_calls"][0]["id"] == "toolu_01ABC"
        assert msg["tool_calls"][0]["type"] == "function"
        assert msg["tool_calls"][0]["function"]["name"] == "web_search"
        assert json.loads(msg["tool_calls"][0]["function"]["arguments"]) == {"query": "python"}
        assert body["choices"][0]["finish_reason"] == "tool_calls"
        assert body["usage"]["prompt_tokens"] == 12
        assert body["usage"]["completion_tokens"] == 30
        assert body["usage"]["total_tokens"] == 42

    def test_max_tokens_maps_to_length(self):
        body = from_anthropic_response({
            "type": "message",
            "content": [{"type": "text", "text": ""}],
            "stop_reason": "max_tokens",
            "usage": {"input_tokens": 1, "output_tokens": 1},
        })
        assert body["choices"][0]["finish_reason"] == "length"

    def test_engine_extract_shape(self):
        """Engine._extract_response 读 choices[0].message.{content,tool_calls}。"""
        body = from_anthropic_response({
            "type": "message",
            "content": [
                {"type": "tool_use", "id": "t1", "name": "web_search",
                 "input": {"query": "x"}},
            ],
            "stop_reason": "tool_use",
            "usage": {},
        })
        choice = body.get("choices", [{}])[0]
        message = choice.get("message", {})
        content = message.get("content") or ""
        tool_calls = message.get("tool_calls") or []
        assert content == ""
        assert tool_calls[0]["function"]["name"] == "web_search"


class TestStreamConversion:
    def test_text_then_tool_use_then_done(self):
        state = AnthropicStreamState()
        events = [
            {"type": "message_start", "message": {
                "usage": {"input_tokens": 9, "output_tokens": 0}}},
            {"type": "content_block_start", "index": 0,
             "content_block": {"type": "text", "text": ""}},
            {"type": "content_block_delta", "index": 0,
             "delta": {"type": "text_delta", "text": "Hi"}},
            {"type": "content_block_stop", "index": 0},
            {"type": "content_block_start", "index": 1,
             "content_block": {"type": "tool_use", "id": "toolu_9",
                               "name": "web_search", "input": {}}},
            {"type": "content_block_delta", "index": 1,
             "delta": {"type": "input_json_delta", "partial_json": '{"query":'}},
            {"type": "content_block_delta", "index": 1,
             "delta": {"type": "input_json_delta", "partial_json": '"py"}'}},
            {"type": "message_delta",
             "delta": {"stop_reason": "tool_use"},
             "usage": {"output_tokens": 4}},
            {"type": "message_stop"},
        ]
        contents = []
        tool_args = []
        finish = None
        for ev in events:
            chunk = anthropic_event_to_openai_chunk(ev, state)
            if chunk is ANTHROPIC_STREAM_DONE:
                break
            if not chunk:
                continue
            delta = (chunk.get("choices") or [{}])[0].get("delta") or {}
            if delta.get("content"):
                contents.append(delta["content"])
            for tc in delta.get("tool_calls") or []:
                tool_args.append(tc)
            if delta.get("finish_reason"):
                finish = delta["finish_reason"]
        else:
            pytest.fail("message_stop should yield ANTHROPIC_STREAM_DONE")
        assert "".join(contents) == "Hi"
        assert finish == "tool_calls"
        names = [tc.get("function", {}).get("name") for tc in tool_args if tc.get("function", {}).get("name")]
        assert "web_search" in names
        args_joined = "".join(
            (tc.get("function") or {}).get("arguments") or "" for tc in tool_args)
        assert json.loads(args_joined) == {"query": "py"}


# ── 3. full llm_caller path against a fake Anthropic HTTP server ───


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _Capture:
    body = None
    headers = None
    path = None


class _AnthropicMessagesHandler(BaseHTTPRequestHandler):
    """Fake Anthropic /v1/messages: non-stream text+tool_use JSON."""

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length)
        _Capture.path = self.path
        _Capture.headers = {k.lower(): v for k, v in self.headers.items()}
        _Capture.body = json.loads(raw.decode("utf-8"))
        body = json.dumps({
            "id": "msg_fake",
            "type": "message",
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Looking it up."},
                {"type": "tool_use", "id": "toolu_01ABC",
                 "name": "web_search", "input": {"query": "python"}},
            ],
            "stop_reason": "tool_use",
            "usage": {"input_tokens": 20, "output_tokens": 15},
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.close_connection = True
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


class _AnthropicStreamHandler(BaseHTTPRequestHandler):
    """Fake Anthropic SSE: text + tool_use + message_stop (no [DONE])."""

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length)
        _Capture.path = self.path
        _Capture.headers = {k.lower(): v for k, v in self.headers.items()}
        _Capture.body = json.loads(raw.decode("utf-8"))
        events = [
            {"type": "message_start", "message": {
                "id": "msg_s", "type": "message", "role": "assistant",
                "content": [], "usage": {"input_tokens": 8, "output_tokens": 0}}},
            {"type": "content_block_start", "index": 0,
             "content_block": {"type": "text", "text": ""}},
            {"type": "content_block_delta", "index": 0,
             "delta": {"type": "text_delta", "text": "On it."}},
            {"type": "content_block_stop", "index": 0},
            {"type": "content_block_start", "index": 1,
             "content_block": {"type": "tool_use", "id": "toolu_stream",
                               "name": "web_search", "input": {}}},
            {"type": "content_block_delta", "index": 1,
             "delta": {"type": "input_json_delta",
                       "partial_json": '{"query": "sse"}'}},
            {"type": "content_block_stop", "index": 1},
            {"type": "message_delta",
             "delta": {"stop_reason": "tool_use"},
             "usage": {"output_tokens": 11}},
            {"type": "message_stop"},
        ]
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.close_connection = True
        self.end_headers()
        for ev in events:
            line = f"event: {ev['type']}\ndata: {json.dumps(ev)}\n\n"
            self.wfile.write(line.encode())
            self.wfile.flush()
            time.sleep(0.005)

    def log_message(self, *a):
        pass


class _OpenAICompatHandler(BaseHTTPRequestHandler):
    """OpenRouter-shaped chat/completions: must NOT receive Anthropic body."""

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length)
        _Capture.path = self.path
        _Capture.headers = {k.lower(): v for k, v in self.headers.items()}
        _Capture.body = json.loads(raw.decode("utf-8"))
        body = json.dumps({
            "choices": [{"message": {"role": "assistant", "content": "via openrouter"},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.close_connection = True
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


@pytest.fixture
def anthropic_messages_url():
    _Capture.body = _Capture.headers = _Capture.path = None
    port = _find_free_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), _AnthropicMessagesHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    time.sleep(0.05)
    yield f"http://127.0.0.1:{port}/v1/messages"
    server.shutdown()


@pytest.fixture
def anthropic_stream_url():
    _Capture.body = _Capture.headers = _Capture.path = None
    port = _find_free_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), _AnthropicStreamHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    time.sleep(0.05)
    yield f"http://127.0.0.1:{port}/v1/messages"
    server.shutdown()


@pytest.fixture
def openrouter_compat_url():
    _Capture.body = _Capture.headers = _Capture.path = None
    port = _find_free_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), _OpenAICompatHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    time.sleep(0.05)
    yield f"http://127.0.0.1:{port}/api/v1/chat/completions"
    server.shutdown()


class TestLlmCallerAnthropicLive:
    def test_nonstream_request_response_tool_calls(self, anthropic_messages_url):
        proto = get_provider("anthropic")
        caller = create_llm_caller(
            "sk-ant-test", anthropic_messages_url, "claude-sonnet-4-20250514",
            tools_schema=[WEB_SEARCH_TOOL], provider_proto=proto,
        )
        result = caller(OPENAI_TOOL_ROUND, use_tools=True)
        assert "error" not in result, result
        # request on the wire is Messages API
        assert _Capture.path.endswith("/v1/messages")
        assert _Capture.headers.get("x-api-key") == "sk-ant-test"
        assert _Capture.headers.get("anthropic-version") == "2023-06-01"
        assert "authorization" not in _Capture.headers
        wire = _Capture.body
        assert wire["model"] == "claude-sonnet-4-20250514"
        assert wire["system"] == "You are bobo."
        assert wire["tools"][0]["name"] == "web_search"
        assert "input_schema" in wire["tools"][0]
        assert wire["tool_choice"] == {"type": "auto"}
        assert all(m["role"] in ("user", "assistant") for m in wire["messages"])
        # response back to engine is OpenAI-shaped
        msg = result["choices"][0]["message"]
        assert msg["content"] == "Looking it up."
        assert msg["tool_calls"][0]["function"]["name"] == "web_search"
        assert json.loads(msg["tool_calls"][0]["function"]["arguments"]) == {"query": "python"}
        assert result["choices"][0]["finish_reason"] == "tool_calls"

    def test_stream_text_and_tool_calls(self, anthropic_stream_url):
        proto = get_provider("anthropic")
        streamed = []
        caller = create_llm_caller(
            "sk-ant-test", anthropic_stream_url, "claude-haiku-3-20240307",
            tools_schema=[WEB_SEARCH_TOOL], provider_proto=proto,
        )
        result = caller(
            [{"role": "user", "content": "search sse"}],
            use_tools=True,
            stream_callback=streamed.append,
        )
        assert "error" not in result, result
        assert _Capture.body.get("stream") is True
        assert "".join(streamed) == "On it."
        msg = result["choices"][0]["message"]
        assert msg["content"] == "On it."
        tcs = msg.get("tool_calls") or []
        assert tcs, f"expected tool_calls, got {result}"
        assert tcs[0]["id"] == "toolu_stream"
        assert tcs[0]["function"]["name"] == "web_search"
        assert json.loads(tcs[0]["function"]["arguments"]) == {"query": "sse"}
        assert result.get("finish_reason") == "tool_calls"

    def test_url_fallback_without_provider_proto(self, anthropic_messages_url):
        """漏传 proto 时 URL /v1/messages 仍走适配器。"""
        caller = create_llm_caller("sk-ant-test", anthropic_messages_url, "claude-x")
        result = caller([{"role": "user", "content": "hi"}], use_tools=False)
        assert "error" not in result, result
        assert _Capture.headers.get("x-api-key") == "sk-ant-test"
        assert _Capture.body["messages"][0]["role"] == "user"
        assert result["choices"][0]["message"]["content"] == "Looking it up."


class TestOpenRouterNoRegression:
    def test_openrouter_claude_stays_openai_chat(self, openrouter_compat_url):
        proto = get_provider("openrouter")
        caller = create_llm_caller(
            "sk-or-test", openrouter_compat_url, "anthropic/claude-sonnet-4",
            tools_schema=[WEB_SEARCH_TOOL], provider_proto=proto,
        )
        result = caller(
            [{"role": "user", "content": "hi claude via or"}],
            use_tools=True,
        )
        assert "error" not in result, result
        assert _Capture.path.endswith("/chat/completions")
        assert _Capture.headers.get("authorization") == "Bearer sk-or-test"
        assert "x-api-key" not in _Capture.headers
        wire = _Capture.body
        assert wire["model"] == "anthropic/claude-sonnet-4"
        assert wire["messages"][0] == {"role": "user", "content": "hi claude via or"}
        assert wire["tools"][0]["type"] == "function"
        assert wire["tools"][0]["function"]["name"] == "web_search"
        assert wire["tool_choice"] == "auto"
        assert result["choices"][0]["message"]["content"] == "via openrouter"
