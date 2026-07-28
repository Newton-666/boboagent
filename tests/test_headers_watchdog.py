"""tests/test_headers_watchdog.py — 票 R：headers 阶段总预算看门狗集成测试

验收铁规：
  - 必须起真实 HTTP 假服务器（收请求后永远不回响应头）测 headers 超时
  - 必须起滴漏服务器（每 <1s 滴漏一个字节）验证总预算不被 read 超时绕过
  - 禁止合成异常（Mock/MagicMock/手动 raise）

环境变量：TEST_HEADERS_TIMEOUT=1 控制看门狗超时（默认 1s，避免集成测试耗时 90s）。
"""

import os
import json
import time
import socket
import threading
import pytest
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    """多线程版 HTTPServer：hang 服务器不阻塞后续请求。"""
    allow_reuse_address = True
    daemon_threads = True


# macOS 系统代理（ClashX 等）会拦截 localhost 请求
os.environ.setdefault("NO_PROXY", "127.0.0.1,localhost")
os.environ.setdefault("no_proxy", "127.0.0.1,localhost")

# 集成测试 headers 看门狗超时（环境变量可覆盖）
_WATCHDOG_TIMEOUT = int(os.environ.get("TEST_HEADERS_TIMEOUT", "1"))


class _HeadersHangHandler(BaseHTTPRequestHandler):
    """收请求后永远不回响应头。"""

    def do_POST(self):
        # 读取并丢弃请求体，否则客户端发不完请求
        _ = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        while True:
            time.sleep(3600)


class _HeadersLeakyHandler(BaseHTTPRequestHandler):
    """滴漏服务器：每隔 0.3s 写 1 字节，永远不发完响应头。

    这会重置 requests 的 READ_TIMEOUT，但不应重置票 R 的 headers 总预算。
    """

    def do_POST(self):
        _ = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        try:
            while True:
                self.wfile.write(b" ")
                self.wfile.flush()
                time.sleep(0.3)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass


class _HeadersOkHandler(BaseHTTPRequestHandler):
    """正常服务器：立即返回 JSON。"""

    def do_POST(self):
        _ = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        body = json.dumps({"choices": [{"message": {"content": "ok"}}]})
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body.encode())
        self.wfile.flush()


def _find_free_port() -> int:
    """找可用端口。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def hang_server():
    """启动永远不回响应头的 HTTP 服务器。"""
    port = _find_free_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), _HeadersHangHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield port
    server.shutdown()
    server.server_close()


@pytest.fixture
def leaky_server():
    """启动滴漏 HTTP 服务器。"""
    port = _find_free_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), _HeadersLeakyHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield port
    server.shutdown()
    server.server_close()


@pytest.fixture
def ok_server():
    """启动正常 HTTP 服务器。"""
    port = _find_free_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), _HeadersOkHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield port
    server.shutdown()
    server.server_close()


class _EventRecorder:
    """记录事件总线写入的事件。"""

    def __init__(self):
        self.events = []

    def write(self, event_type: str, data: dict):
        self.events.append((event_type, data))


class TestHeadersWatchdog:
    """headers 阶段看门狗真实服务器集成测试。"""

    def test_headers_stall_on_hang_server(self, hang_server, monkeypatch):
        """永远不回响应头的服务器应在总预算内触发 headers_stall 并重试 1 次。"""
        from core.llm_caller import (
            _post_with_headers_watchdog,
            HeadersStallError,
        )

        recorder = _EventRecorder()
        monkeypatch.setattr("core.event_bus.event_bus.write", recorder.write)

        start = time.time()
        with pytest.raises(HeadersStallError) as excinfo:
            _post_with_headers_watchdog(
                f"http://127.0.0.1:{hang_server}/v1/chat/completions",
                json={"model": "test"},
                headers={"Content-Type": "application/json"},
                timeout=(5, 30),
                stream=False,
                headers_timeout=_WATCHDOG_TIMEOUT,
                event_bus=recorder,
                session_id="test-hang",
            )
        elapsed = time.time() - start

        assert "headers 阶段总预算" in str(excinfo.value)
        # 硬上限 1 次重试：初始 1s + 重试 1s，允许误差
        assert elapsed >= 1.8 * _WATCHDOG_TIMEOUT, f"应至少重试 1 次，实际 {elapsed:.2f}s"
        assert elapsed < 4 * _WATCHDOG_TIMEOUT, f"总耗时异常长 {elapsed:.2f}s"

        headers_events = [e for e in recorder.events if e[0] == "llm.headers_stall"]
        assert len(headers_events) == 2, f"应产生 retry + fail 共 2 个事件，实际 {len(headers_events)}"
        actions = [e[1]["action"] for e in headers_events]
        assert actions == ["retry", "fail"], f"事件顺序应为 retry, fail，实际 {actions}"
        for _, data in headers_events:
            assert data["session_id"] == "test-hang"
            assert data["elapsed_ms"] >= _WATCHDOG_TIMEOUT * 1000

    def test_headers_stall_on_leaky_server(self, leaky_server, monkeypatch):
        """滴漏服务器（每 0.3s 1 字节）不应骗过 headers 总预算。"""
        from core.llm_caller import (
            _post_with_headers_watchdog,
            HeadersStallError,
        )

        recorder = _EventRecorder()
        monkeypatch.setattr("core.event_bus.event_bus.write", recorder.write)

        start = time.time()
        with pytest.raises(HeadersStallError):
            _post_with_headers_watchdog(
                f"http://127.0.0.1:{leaky_server}/v1/chat/completions",
                json={"model": "test"},
                headers={"Content-Type": "application/json"},
                timeout=(5, 30),
                stream=False,
                headers_timeout=_WATCHDOG_TIMEOUT,
                event_bus=recorder,
                session_id="test-leaky",
            )
        elapsed = time.time() - start

        # 总预算只计 wall-clock，滴漏无法重置
        assert elapsed < 4 * _WATCHDOG_TIMEOUT, f"滴漏不应拖过总预算，实际 {elapsed:.2f}s"
        headers_events = [e for e in recorder.events if e[0] == "llm.headers_stall"]
        assert len(headers_events) == 2

    def test_headers_ok_server_returns_normally(self, ok_server):
        """正常服务器应立即返回，不看门狗触发。"""
        from core.llm_caller import _post_with_headers_watchdog

        recorder = _EventRecorder()
        start = time.time()
        response = _post_with_headers_watchdog(
            f"http://127.0.0.1:{ok_server}/v1/chat/completions",
            json={"model": "test"},
            headers={"Content-Type": "application/json"},
            timeout=(5, 30),
            stream=False,
            headers_timeout=_WATCHDOG_TIMEOUT,
            event_bus=recorder,
            session_id="test-ok",
        )
        elapsed = time.time() - start

        assert response.status_code == 200
        assert response.json()["choices"][0]["message"]["content"] == "ok"
        assert elapsed < _WATCHDOG_TIMEOUT, f"正常请求不应被看门狗延迟，实际 {elapsed:.2f}s"

    def test_env_headers_timeout_overrides_default(self, monkeypatch):
        """BOBO_HEADERS_TIMEOUT 环境变量可覆盖默认 90s。"""
        from core.llm_caller import _get_headers_timeout

        monkeypatch.setenv("BOBO_HEADERS_TIMEOUT", "42")
        assert _get_headers_timeout() == 42

    def test_invalid_env_headers_timeout_falls_back(self, monkeypatch):
        """BOBO_HEADERS_TIMEOUT 非法值回退默认值。"""
        from core.llm_caller import _get_headers_timeout, _HEADERS_TIMEOUT_DEFAULT

        monkeypatch.setenv("BOBO_HEADERS_TIMEOUT", "not-a-number")
        assert _get_headers_timeout() == _HEADERS_TIMEOUT_DEFAULT
