"""Tests for core/llm_caller.py — _classify_error function and SSE stream stall/retry.

Verifies that HTTP status codes and network exceptions are correctly
classified so the retry logic works properly.
Ticket N: SSE 流式读超时 + 断流重试 — 引擎假死治本。
"""

import os
import json
import time
import pytest
import requests
from unittest.mock import MagicMock, patch
from core.llm_caller import _classify_error, _get_sse_read_timeout, _emit_stream_stall


# ── _get_sse_read_timeout ─────────────────────────────────────────


class TestGetSseReadTimeout:
    """票 N：_get_sse_read_timeout 环境变量覆盖."""

    def test_default_120(self):
        assert _get_sse_read_timeout() == 120

    def test_env_var_override(self, monkeypatch):
        monkeypatch.setenv("BOBO_SSE_READ_TIMEOUT", "60")
        assert _get_sse_read_timeout() == 60

    def test_env_var_invalid_fallback(self, monkeypatch):
        monkeypatch.setenv("BOBO_SSE_READ_TIMEOUT", "abc")
        assert _get_sse_read_timeout() == 120


# ── _emit_stream_stall ────────────────────────────────────────────


class TestEmitStreamStall:
    """票 N：llm.stream_stall 事件落盘."""

    def test_writes_event_with_retry_action(self):
        bus = MagicMock()
        _emit_stream_stall(bus, "sid-1", 5, 12345, "retry")
        bus.write.assert_called_once_with("llm.stream_stall", {
            "session_id": "sid-1",
            "received_chunks": 5,
            "elapsed_ms": 12345,
            "action": "retry",
        })

    def test_writes_event_with_fail_action(self):
        bus = MagicMock()
        _emit_stream_stall(bus, "sid-2", 3, 67000, "fail")
        bus.write.assert_called_once_with("llm.stream_stall", {
            "session_id": "sid-2",
            "received_chunks": 3,
            "elapsed_ms": 67000,
            "action": "fail",
        })

    def test_none_bus_does_not_crash(self):
        _emit_stream_stall(None, "sid", 0, 0, "retry")

    def test_bus_write_exception_does_not_crash(self):
        bus = MagicMock()
        bus.write.side_effect = RuntimeError("bus full")
        _emit_stream_stall(bus, "sid", 0, 0, "retry")


# ── SSE 流式断流 + 重试（集成测试）─────────────────────────────


class TestSseStreamStallRetry:
    """票 N：SSE 流式断流 → 重试 1 次 → 半残不拼接."""

    def _make_sse_chunk(self, content: str) -> bytes:
        data = json.dumps({"choices": [{"delta": {"content": content}}]})
        return f"data: {data}\n\n".encode()

    def _make_done_chunk(self) -> bytes:
        return b"data: [DONE]\n\n"

    def test_normal_stream_completes(self):
        """金标准 4：正常流零误伤。"""
        from core.llm_caller import create_llm_caller
        chunks = [self._make_sse_chunk("Hello"), self._make_sse_chunk(" World"), self._make_done_chunk()]
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.iter_lines.return_value = chunks

        collected = []
        caller = create_llm_caller("test-key", "http://fake/api", "test-model")
        with patch("requests.post", return_value=mock_response):
            result = caller([{"role": "user", "content": "hi"}], stream_callback=collected.append)

        assert "error" not in result
        assert result["choices"][0]["message"]["content"] == "Hello World"
        assert "".join(collected) == "Hello World"

    def test_stall_triggers_retry_and_succeeds(self):
        """金标准 1+2+3：假死复活 + 断流留证 + 半残不拼接."""
        from core.llm_caller import create_llm_caller

        events = []

        def stall_iter_lines():
            yield self._make_sse_chunk("par")
            yield self._make_sse_chunk("tial")
            raise requests.exceptions.ReadTimeout("模拟断流")

        mock1 = MagicMock()
        mock1.status_code = 200
        mock1.iter_lines = stall_iter_lines

        mock2 = MagicMock()
        mock2.status_code = 200
        mock2.iter_lines.return_value = [
            self._make_sse_chunk("complete"), self._make_sse_chunk(" data"), self._make_done_chunk()
        ]

        call_n = [0]
        def mock_post(url, **kw):
            call_n[0] += 1
            return mock1 if call_n[0] == 1 else mock2

        # 替换 _emit_stream_stall 以捕获事件
        import core.llm_caller as lc
        orig_emit = lc._emit_stream_stall
        def tracking_emit(bus, sid, rc, em, act):
            events.append(("llm.stream_stall", {
                "session_id": sid, "received_chunks": rc, "elapsed_ms": em, "action": act,
            }))
        lc._emit_stream_stall = tracking_emit

        try:
            collected = []
            caller = create_llm_caller("test-key", "http://fake/api", "test-model")
            with patch("requests.post", side_effect=mock_post):
                result = caller(
                    [{"role": "user", "content": "hi"}],
                    stream_callback=collected.append,
                    session_id="test-sid",
                )
        finally:
            lc._emit_stream_stall = orig_emit

        # 金标准 1：成功返回
        assert "error" not in result, f"不应返回错误: {result}"
        # 金标准 3：半残不拼接
        final = result["choices"][0]["message"]["content"]
        assert "tial" not in final, f"半残内容不应出现: {final}"
        assert "complete data" in final
        # 金标准 2：断流留证
        assert len(events) == 1
        assert events[0][1]["action"] == "retry"
        assert events[0][1]["session_id"] == "test-sid"
        assert events[0][1]["received_chunks"] == 2

    def test_stall_twice_returns_error(self):
        """两次断流 → 返回错误，不再重试."""
        from core.llm_caller import create_llm_caller

        events = []

        def always_stall():
            raise requests.exceptions.ReadTimeout("always stalls")

        mock = MagicMock()
        mock.status_code = 200
        mock.iter_lines = always_stall

        import core.llm_caller as lc
        orig_emit = lc._emit_stream_stall
        def tracking_emit(bus, sid, rc, em, act):
            events.append(("llm.stream_stall", {
                "session_id": sid, "received_chunks": rc, "elapsed_ms": em, "action": act,
            }))
        lc._emit_stream_stall = tracking_emit

        try:
            caller = create_llm_caller("test-key", "http://fake/api", "test-model")
            with patch("requests.post", return_value=mock):
                result = caller(
                    [{"role": "user", "content": "hi"}],
                    stream_callback=lambda x: None,
                )
        finally:
            lc._emit_stream_stall = orig_emit

        assert "error" in result
        assert "SSE 流断流" in result["error"]
        assert len([e for e in events if e[1]["action"] == "retry"]) == 1
        assert len([e for e in events if e[1]["action"] == "fail"]) == 1

    def test_chunked_encoding_error_triggers_retry(self):
        """ChunkedEncodingError 同样触发断流重试."""
        from core.llm_caller import create_llm_caller

        def stall_iter():
            yield self._make_sse_chunk("a")
            raise requests.exceptions.ChunkedEncodingError("chunk broken")

        mock1 = MagicMock()
        mock1.status_code = 200
        mock1.iter_lines = stall_iter

        mock2 = MagicMock()
        mock2.status_code = 200
        mock2.iter_lines.return_value = [self._make_sse_chunk("ok"), self._make_done_chunk()]

        call_n = [0]
        def mock_post(url, **kw):
            call_n[0] += 1
            return mock1 if call_n[0] == 1 else mock2

        caller = create_llm_caller("test-key", "http://fake/api", "test-model")
        with patch("requests.post", side_effect=mock_post):
            result = caller([{"role": "user", "content": "hi"}], stream_callback=lambda x: None)

        assert "error" not in result
        assert result["choices"][0]["message"]["content"] == "ok"

    def test_connection_error_triggers_retry(self):
        """ConnectionError 同样触发断流重试."""
        from core.llm_caller import create_llm_caller

        def stall_iter():
            raise requests.exceptions.ConnectionError("connection lost mid-stream")

        mock1 = MagicMock()
        mock1.status_code = 200
        mock1.iter_lines = stall_iter

        mock2 = MagicMock()
        mock2.status_code = 200
        mock2.iter_lines.return_value = [self._make_sse_chunk("recovered"), self._make_done_chunk()]

        call_n = [0]
        def mock_post(url, **kw):
            call_n[0] += 1
            return mock1 if call_n[0] == 1 else mock2

        caller = create_llm_caller("test-key", "http://fake/api", "test-model")
        with patch("requests.post", side_effect=mock_post):
            result = caller([{"role": "user", "content": "hi"}], stream_callback=lambda x: None)

        assert "error" not in result
        assert result["choices"][0]["message"]["content"] == "recovered"


# ── _classify_error ───────────────────────────────────────────────


class TestHTTPStatusCodeClassification:
    """Classification based on HTTP response status codes."""

    def test_200_is_not_an_error(self):
        pass

    def test_401_auth_error_not_retryable(self):
        error_type, retryable, message = _classify_error(status_code=401)
        assert error_type == "auth_error"
        assert retryable is False
        assert "API Key" in message or "认证" in message

    def test_403_permission_error_not_retryable(self):
        error_type, retryable, message = _classify_error(status_code=403)
        assert error_type == "auth_error"
        assert retryable is False

    def test_429_rate_limit_is_retryable(self):
        error_type, retryable, message = _classify_error(status_code=429)
        assert error_type == "rate_limit"
        assert retryable is True

    def test_500_server_error_is_retryable(self):
        error_type, retryable, message = _classify_error(status_code=500)
        assert error_type == "server_error"
        assert retryable is True

    def test_502_bad_gateway_is_retryable(self):
        error_type, retryable, message = _classify_error(status_code=502)
        assert error_type == "server_error"
        assert retryable is True

    def test_503_service_unavailable_is_retryable(self):
        error_type, retryable, message = _classify_error(status_code=503)
        assert error_type == "server_error"
        assert retryable is True

    def test_504_gateway_timeout_is_retryable(self):
        error_type, retryable, message = _classify_error(status_code=504)
        assert error_type == "server_error"
        assert retryable is True

    def test_400_bad_request_not_retryable(self):
        error_type, retryable, message = _classify_error(status_code=400)
        assert error_type == "bad_request"
        assert retryable is False

    def test_404_not_found_not_retryable(self):
        error_type, retryable, message = _classify_error(status_code=404)
        assert error_type == "bad_request"
        assert retryable is False

    def test_422_unprocessable_not_retryable(self):
        error_type, retryable, message = _classify_error(status_code=422)
        assert error_type == "bad_request"
        assert retryable is False


class TestExceptionClassification:
    """Classification based on Python exception objects."""

    def test_timeout_is_retryable(self):
        exc = requests.exceptions.Timeout("Connection timed out")
        error_type, retryable, message = _classify_error(exception=exc)
        assert error_type == "timeout"
        assert retryable is True

    def test_connection_error_is_retryable(self):
        exc = requests.exceptions.ConnectionError("Connection refused")
        error_type, retryable, message = _classify_error(exception=exc)
        assert error_type == "network_error"
        assert retryable is True

    def test_http_error_is_retryable(self):
        exc = requests.exceptions.HTTPError("500 Server Error")
        error_type, retryable, message = _classify_error(exception=exc)
        assert error_type == "server_error"
        assert retryable is True

    def test_json_decode_error_not_retryable(self):
        exc = json.JSONDecodeError("Invalid JSON", "{bad", 0)
        error_type, retryable, message = _classify_error(exception=exc)
        assert error_type == "bad_request"
        assert retryable is False

    def test_value_error_not_retryable(self):
        exc = ValueError("Invalid value")
        error_type, retryable, message = _classify_error(exception=exc)
        assert error_type == "bad_request"
        assert retryable is False

    def test_generic_exception_not_retryable(self):
        exc = RuntimeError("Something unexpected")
        error_type, retryable, message = _classify_error(exception=exc)
        assert error_type == "unknown"
        assert retryable is False


class TestPriorityOrder:
    """When both exception and status_code are provided, exception takes priority."""

    def test_exception_wins_over_status(self):
        exc = requests.exceptions.Timeout("...")
        error_type, retryable, message = _classify_error(exception=exc, status_code=500)
        assert error_type == "timeout"


class TestMessageContent:
    """Verify human-readable messages are meaningful."""

    def test_all_messages_are_non_empty(self):
        for code in [401, 403, 429, 500, 502, 503, 504, 400, 404]:
            _, _, msg = _classify_error(status_code=code)
            assert len(msg) > 0

    def test_all_exception_messages_are_non_empty(self):
        exceptions = [
            requests.exceptions.Timeout(),
            requests.exceptions.ConnectionError(),
            requests.exceptions.HTTPError(),
            ValueError("test"),
            json.JSONDecodeError("test", "{}", 0),
        ]
        for exc in exceptions:
            _, _, msg = _classify_error(exception=exc)
            assert len(msg) > 0
