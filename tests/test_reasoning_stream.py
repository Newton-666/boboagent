"""tests/test_reasoning_stream.py — 票 P：reasoning 模型兼容（真服务器验收）

破案背景：Kimi K2.6/K3 "不回复" = 服务端对 stream=True 直接回普通 JSON
（非 SSE），或 SSE 流里只发 reasoning_content。旧代码把 reasoning_content
丢弃、非 SSE 响应当空流，用户看到的就是"闭嘴"。

验收铁规：真 HTTP 服务器，禁止 Mock。
"""

import os
import json
import time
import socket
import threading
import pytest
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

from core.llm_caller import create_llm_caller

os.environ.setdefault("NO_PROXY", "127.0.0.1,localhost")
os.environ.setdefault("no_proxy", "127.0.0.1,localhost")


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _ReasoningSseHandler(BaseHTTPRequestHandler):
    """SSE 流：先发 3 块 reasoning_content，再发 1 块 content，再 [DONE]。"""

    def do_POST(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.close_connection = True
        self.end_headers()
        lines = []
        for r in ["让我想想", "这个问题", "答案显然是"]:
            lines.append(f"data: {json.dumps({'choices': [{'delta': {'reasoning_content': r}}]})}\n\n")
        lines.append(f"data: {json.dumps({'choices': [{'delta': {'content': '42'}}]})}\n\n")
        lines.append("data: [DONE]\n\n")
        for ln in lines:
            self.wfile.write(ln.encode())
            self.wfile.flush()
            time.sleep(0.01)

    def log_message(self, *a):
        pass


class _NonSseJsonHandler(BaseHTTPRequestHandler):
    """对 stream=True 直接回普通 JSON（moonshot 部分模型行为）。"""

    def do_POST(self):
        body = json.dumps({
            "choices": [{"message": {
                "role": "assistant",
                "content": "正经回答",
                "reasoning_content": "内心戏一大堆",
            }}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10},
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.close_connection = True
        self.end_headers()
        self.wfile.write(body)
        self.wfile.flush()

    def log_message(self, *a):
        pass


@pytest.fixture
def reasoning_sse_server():
    port = _find_free_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), _ReasoningSseHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    time.sleep(0.05)
    yield f"http://127.0.0.1:{port}/v1/chat/completions"
    server.shutdown()


@pytest.fixture
def non_sse_server():
    port = _find_free_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), _NonSseJsonHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    time.sleep(0.05)
    yield f"http://127.0.0.1:{port}/v1/chat/completions"
    server.shutdown()


class TestReasoningStream:
    def test_reasoning_separated_from_content(self, reasoning_sse_server):
        """reasoning_content 绝不混入正文；独立返回 + 回调被调。"""
        caller = create_llm_caller("k", reasoning_sse_server, "m")
        reasoning_tokens = []
        result = caller(
            [{"role": "user", "content": "hi"}],
            stream_callback=lambda x: None,
            reasoning_callback=reasoning_tokens.append,
        )
        assert "error" not in result, f"不应报错: {result}"
        # 正文纯净
        assert result["choices"][0]["message"]["content"] == "42"
        # reasoning 独立返回
        assert result["reasoning"] == "让我想想这个问题答案显然是"
        # 回调逐 token 被调
        assert "".join(reasoning_tokens) == "让我想想这个问题答案显然是"

    def test_non_sse_json_fallback(self, non_sse_server):
        """非 SSE JSON 响应 → 兜底解析出 content + reasoning，不再装死。"""
        caller = create_llm_caller("k", non_sse_server, "m")
        result = caller(
            [{"role": "user", "content": "hi"}],
            stream_callback=lambda x: None,
        )
        assert "error" not in result, f"不应报错: {result}"
        assert result["choices"][0]["message"]["content"] == "正经回答"
        assert result["reasoning"] == "内心戏一大堆"
        assert result["usage"]["total_tokens"] == 10
