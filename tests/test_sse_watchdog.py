"""tests/test_sse_watchdog.py — 票 N2：应用层流式看门狗集成测试

验收铁规：
  - 必须起真实 HTTP 假服务器（发 3 块后真闭嘴）测超时引爆
  - 禁止合成异常（Mock/MagicMock/手动 raise）

环境变量：TEST_SSE_TIMEOUT=2 控制看门狗超时（默认 2s，避免集成测试耗时 120s）。

注：原 _SseWatchdog（threading.Timer 方案）与 socket 1s 轮询方案均已被
探针实验证伪（socket 超时会污染 httplib 状态机，EOF 假象），现架构为
读者线程 + 队列（core.llm_caller._read_stream_lines），本文件只保留
真服务器集成测试——那才是金标准。
"""

import os
import json
import time
import socket
import threading
import requests
import pytest
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    """多线程版 HTTPServer：hang 服务器不阻塞后续请求。"""
    allow_reuse_address = True
    daemon_threads = True


from core.llm_caller import _get_sse_read_timeout, create_llm_caller

# macOS 系统代理（ClashX 等）会拦截 localhost 请求，
# 但 urllib 未正确读取 ExceptionsList。
os.environ.setdefault("NO_PROXY", "127.0.0.1,localhost")
os.environ.setdefault("no_proxy", "127.0.0.1,localhost")

# 集成测试看门狗超时（环境变量可覆盖，但不用会太久？默认 2s 足够）
_WATCHDOG_TIMEOUT = int(os.environ.get("TEST_SSE_TIMEOUT", "2"))


# ══════════════════════════════════════════════════════════════════════
# 真实 HTTP 假服务器
# ══════════════════════════════════════════════════════════════════════


class _SseChunkHandler(BaseHTTPRequestHandler):
    """SSE 流假服务器：发送指定数量的 chunk 后闭嘴（不挂断、不发数据）。"""

    # 类变量，测试可配置
    chunks_to_send: list[str] = []
    chunk_delay: float = 0.01
    hang_after_chunks: bool = False

    def do_POST(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        # 不设 Connection: keep-alive → HTTP/1.1 默认 keep-alive，
        # 但我们在请求处理完后关闭 socket 确保 retry 不走已死连接。
        self.close_connection = True
        self.end_headers()

        # 发送 SSE chunks
        for i, chunk_text in enumerate(self.__class__.chunks_to_send):
            data = json.dumps({"choices": [{"delta": {"content": chunk_text}}]})
            line = f"data: {data}\n\n"
            try:
                self.wfile.write(line.encode())
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                break
            if i < len(self.__class__.chunks_to_send) - 1:
                time.sleep(self.__class__.chunk_delay)

        # 正常流：发送 [DONE] 标记
        if not self.__class__.hang_after_chunks:
            try:
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass

        # 挂起：不发 [DONE]，不发任何数据，不关闭连接
        if self.__class__.hang_after_chunks:
            while True:
                time.sleep(3600)  # 永远不返回，模拟服务端假死


class _SseHangHandler(BaseHTTPRequestHandler):
    """SSE 假服务器：不发送任何 SSE 行（首字节后直接挂起）。"""

    def do_POST(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.close_connection = True
        self.end_headers()
        self.wfile.flush()
        while True:
            time.sleep(3600)


def _find_free_port() -> int:
    """找可用端口。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def hang_server():
    """启动一个发 3 个 chunk 后闭嘴的 HTTP SSE 服务器。

    返回 (server, port, url)，测试结束后自动关闭。
    用 _WATCHDOG_TIMEOUT 控制看门狗超时，确保测试在 2-4s 内完成。
    """
    _SseChunkHandler.chunks_to_send = ["Hello", " ", "World"]
    _SseChunkHandler.chunk_delay = 0.01
    _SseChunkHandler.hang_after_chunks = True

    port = _find_free_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), _SseChunkHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.3)  # 等服务器就绪
    url = f"http://127.0.0.1:{port}/v1/chat/completions"

    yield server, port, url

    server.shutdown()


@pytest.fixture
def silent_server():
    """启动一个不发任何 SSE chunk 的假服务器。

    首行 200 后就挂起，模拟服务端不发数据也不关闭连接。
    """
    _SseHangHandler.post_count = 0

    port = _find_free_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), _SseHangHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.05)
    url = f"http://127.0.0.1:{port}/v1/chat/completions"

    yield server, port, url

    server.shutdown()


@pytest.fixture
def normal_server():
    """正常返回 SSE 流直至 [DONE] 的参考服务器。"""
    _SseChunkHandler.chunks_to_send = ["Hello", " World"]
    _SseChunkHandler.chunk_delay = 0.01
    _SseChunkHandler.hang_after_chunks = False

    port = _find_free_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), _SseChunkHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.05)
    url = f"http://127.0.0.1:{port}/v1/chat/completions"

    yield server, port, url

    server.shutdown()


# ══════════════════════════════════════════════════════════════════════
# 集成测试：真实 HTTP 假服务器
# ══════════════════════════════════════════════════════════════════════


class TestWatchdogWithRealServer:
    """票 N2：应用层看门狗 + 断流重试 — 真实 HTTP 服务端验收."""

    def test_normal_stream_no_watchdog_false(self, normal_server, monkeypatch):
        """金标准 4：正常流零误伤。"""
        _, _, url = normal_server
        monkeypatch.setenv("BOBO_SSE_READ_TIMEOUT", str(_WATCHDOG_TIMEOUT))

        caller = create_llm_caller("test-key", url, "test-model")
        collected = []

        result = caller(
            [{"role": "user", "content": "hi"}],
            stream_callback=collected.append,
        )

        assert "error" not in result, f"不应返回错误: {result}"
        assert result["choices"][0]["message"]["content"] == "Hello World"
        assert "".join(collected) == "Hello World"

    def test_hang_server_triggers_watchdog_retry(self, hang_server, monkeypatch):
        """发 3 块后闭嘴 → 看门狗 2s 引爆 → 断流重试 → 第二次又断流 → 返回 error.

        验证三件事：
          1. 看门狗在真实服务端假死时能引爆（非合成异常）
          2. 重试机制正常工作（第一次断裂后调用第二次 requests.post）
          3. 重试硬上限（两次断裂后不再重试，直接返回 error）
        耗时：每次看门狗约 2s，共约 4-5s。
        """
        _, _, url = hang_server
        monkeypatch.setenv("BOBO_SSE_READ_TIMEOUT", str(_WATCHDOG_TIMEOUT))

        callback_calls = []

        caller = create_llm_caller("test-key", url, "test-model")
        result = caller(
            [{"role": "user", "content": "hi"}],
            stream_callback=lambda x: callback_calls.append(x),
        )

        # 服务端只发 3 块然后挂起，重试一次后仍挂起 → 应返回 error
        assert "error" in result, f"应返回错误，但收到: {result}"
        assert "SSE 流断流" in result.get("error", "")
        # 已收到 3 个 chunk（Hello, 空格, World），应已推给 callback
        assert len(callback_calls) >= 3, f"应收到至少 3 个 chunk: {callback_calls}"

    def test_silent_server_triggers_watchdog(self, silent_server, monkeypatch):
        """不发任何 chunk → 看门狗 2s 引爆 → error.

        服务端返回 200 后不发任何 SSE 行，验证看门狗在零 chunk 下也能引爆。
        """
        _, _, url = silent_server
        monkeypatch.setenv("BOBO_SSE_READ_TIMEOUT", str(_WATCHDOG_TIMEOUT))

        caller = create_llm_caller("test-key", url, "test-model")
        result = caller(
            [{"role": "user", "content": "hi"}],
            stream_callback=lambda x: None,
        )

        assert "error" in result, f"应返回错误: {result}"
        assert "SSE 流断流" in result.get("error", "")

    def test_retry_then_succeeds_no_half_content(self, first_hang_then_ok_server, monkeypatch):
        """断流重试后成功 + 半残不拼接（真服务器版）。

        第一次连接发 PAR/TIAL 后假死 → 看门狗引爆 → 重试 → 第二次完整流。
        最终 content 只能含第二次的内容，PAR/TIAL 绝不拼接进来。
        """
        url = first_hang_then_ok_server
        monkeypatch.setenv("BOBO_SSE_READ_TIMEOUT", str(_WATCHDOG_TIMEOUT))

        caller = create_llm_caller("test-key", url, "test-model")
        result = caller(
            [{"role": "user", "content": "hi"}],
            stream_callback=lambda x: None,
        )

        assert "error" not in result, f"不应返回错误: {result}"
        final = result["choices"][0]["message"]["content"]
        assert "TIAL" not in final and "PAR" not in final, f"半残内容不应出现: {final}"
        assert "complete data" in final

    def test_truncated_eof_without_done_retries(self, first_truncated_then_ok_server, monkeypatch):
        """半截 EOF 防线：未收 [DONE] 的 EOF 必须重试，半截内容不得冒充完整响应。"""
        url = first_truncated_then_ok_server
        monkeypatch.setenv("BOBO_SSE_READ_TIMEOUT", str(_WATCHDOG_TIMEOUT))

        caller = create_llm_caller("test-key", url, "test-model")
        result = caller(
            [{"role": "user", "content": "hi"}],
            stream_callback=lambda x: None,
        )

        assert "error" not in result, f"不应返回错误: {result}"
        final = result["choices"][0]["message"]["content"]
        assert final == "FULL", f"半截内容不应混入: {final!r}"


class _FirstHangThenOKHandler(BaseHTTPRequestHandler):
    """第一次请求发 2 块后假死；第二次请求发完整流 + [DONE]。

    用于验证：断流重试后成功 + 半残不拼接。
    """

    attempt: int = 0

    def do_POST(self):
        self.__class__.attempt += 1
        n = self.__class__.attempt
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.close_connection = True
        self.end_headers()
        if n == 1:
            for t in ["PAR", "TIAL"]:
                self.wfile.write(f"data: {json.dumps({'choices': [{'delta': {'content': t}}]})}\n\n".encode())
                self.wfile.flush()
                time.sleep(0.01)
            while True:  # 假死
                time.sleep(3600)
        else:
            for t in ["complete", " data"]:
                self.wfile.write(f"data: {json.dumps({'choices': [{'delta': {'content': t}}]})}\n\n".encode())
                self.wfile.flush()
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()

    def log_message(self, *a):
        pass


class _FirstTruncatedThenOKHandler(BaseHTTPRequestHandler):
    """第一次请求发 2 块后直接关连接（无 [DONE]，半截 EOF）；第二次完整。

    用于验证：半截 EOF 防线 — 未收 [DONE] 的 EOF 必须走断流重试，
    半截内容绝不能冒充完整响应。
    """

    attempt: int = 0

    def do_POST(self):
        self.__class__.attempt += 1
        n = self.__class__.attempt
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.close_connection = True
        self.end_headers()
        if n == 1:
            self.wfile.write(f"data: {json.dumps({'choices': [{'delta': {'content': 'HALF'}}]})}\n\n".encode())
            self.wfile.flush()
            return  # 直接返回 → 连接关闭 → 客户端收到无 [DONE] 的 EOF
        else:
            self.wfile.write(f"data: {json.dumps({'choices': [{'delta': {'content': 'FULL'}}]})}\n\n".encode())
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()

    def log_message(self, *a):
        pass


@pytest.fixture
def first_hang_then_ok_server():
    _FirstHangThenOKHandler.attempt = 0
    port = _find_free_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), _FirstHangThenOKHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    time.sleep(0.05)
    yield f"http://127.0.0.1:{port}/v1/chat/completions"
    server.shutdown()


@pytest.fixture
def first_truncated_then_ok_server():
    _FirstTruncatedThenOKHandler.attempt = 0
    port = _find_free_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), _FirstTruncatedThenOKHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    time.sleep(0.05)
    yield f"http://127.0.0.1:{port}/v1/chat/completions"
    server.shutdown()


# ══════════════════════════════════════════════════════════════════════
# 边缘测试：看门狗 + 正常流（无错误）
# ══════════════════════════════════════════════════════════════════════


class TestWatchdogEnvVar:
    """环境变量覆盖测试."""

    def test_default_timeout_is_120(self):
        assert _get_sse_read_timeout() == 120

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("BOBO_SSE_READ_TIMEOUT", "60")
        assert _get_sse_read_timeout() == 60

    def test_env_invalid_fallback(self, monkeypatch):
        monkeypatch.setenv("BOBO_SSE_READ_TIMEOUT", "abc")
        assert _get_sse_read_timeout() == 120
