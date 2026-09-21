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
from core.llm_caller import (
    HeadersStallError,
    MAX_RETRIES,
    RETRY_DELAY_BASE,
    _classify_error,
    _get_sse_read_timeout,
    _emit_stream_stall,
    create_llm_caller,
)


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

    def test_429_insufficient_quota_is_fatal_not_retryable(self):
        """票 U：balance error 含 insufficient_quota → fatal，不重试."""
        error_type, retryable, message = _classify_error(
            status_code=429,
            response_body='{"error": {"message": "Insufficient quota", "type": "insufficient_quota"}}'
        )
        assert error_type == "fatal_insufficient_quota"
        assert retryable is False
        assert "余额" in message or "quota" in message.lower()

    def test_429_deepseek_insufficient_balance_is_fatal(self):
        """票 U：DeepSeek 格式 429 + Insufficient Balance → fatal，不重试."""
        error_type, retryable, message = _classify_error(
            status_code=429,
            response_body='{"error": {"message": "Insufficient Balance"}}'
        )
        assert error_type == "fatal_insufficient_quota"
        assert retryable is False

    def test_429_without_insufficient_quota_still_retryable(self):
        """票 U：纯限流 429 不含 insufficient_quota → 仍然是 rate_limit 可重试."""
        error_type, retryable, message = _classify_error(
            status_code=429,
            response_body='{"error": {"message": "Rate limit exceeded", "type": "requests"}}'
        )
        assert error_type == "rate_limit"
        assert retryable is True


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

    def test_headers_stall_is_retryable(self):
        """issue #10: 内层看门狗耗尽后 HeadersStallError 不得一次判死。"""
        exc = HeadersStallError("headers 阶段总预算 90s 耗尽，已重试仍失败")
        error_type, retryable, message = _classify_error(exception=exc)
        assert error_type == "headers_stall"
        assert retryable is True
        assert "已重试仍失败" in message


class TestHeadersStallOuterRetry:
    """issue #10: 外层 call_llm 对 headers_stall 走 MAX_RETRIES + 指数退避。

    内层 `_post_with_headers_watchdog` 的即时 1 次重试由 live 测试覆盖；
    这里 mock 掉内层，只验证外层：慢厂商/冷启动不再一次判死，致命错误仍不可重试。
    """

    def _ok_response(self, content="warmed up"):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "choices": [{"message": {"role": "assistant", "content": content}}]
        }
        resp.text = json.dumps(resp.json.return_value)
        return resp

    def test_cold_start_recovers_on_outer_retry(self, monkeypatch):
        """复现：内层已抛 HeadersStallError（看门狗即时重试耗尽），外层再试一次成功。

        模拟慢厂商/冷启动：第一次 headers 周期装死，退避后第二次出头。
        若 retryable=False，call_llm 会在第一次 stall 后直接返回 error，不会再 POST。
        """
        import core.llm_caller as llm_mod

        calls = {"n": 0}

        def fake_post(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise HeadersStallError("headers 阶段总预算 90s 耗尽，已重试仍失败")
            return self._ok_response()

        monkeypatch.setattr(llm_mod, "_post_with_headers_watchdog", fake_post)
        monkeypatch.setattr(llm_mod.time, "sleep", lambda _d: None)

        caller = create_llm_caller("k", "http://vendor.test/v1/chat/completions", "m")
        result = caller([{"role": "user", "content": "hi"}], use_tools=False)

        assert calls["n"] == 2, f"外层应再试一次，实际 POST 次数 {calls['n']}"
        assert "error" not in result, f"冷启动恢复后不应返回 error: {result}"
        assert result["choices"][0]["message"]["content"] == "warmed up"

    def test_outer_retries_use_max_retries_and_backoff(self, monkeypatch):
        """外层次数/退避对齐既有 MAX_RETRIES + RETRY_DELAY_BASE，不另起 stall 计数器。"""
        import core.llm_caller as llm_mod

        posts = {"n": 0}
        sleeps = []

        def fake_post(*args, **kwargs):
            posts["n"] += 1
            raise HeadersStallError("headers stall")

        monkeypatch.setattr(llm_mod, "_post_with_headers_watchdog", fake_post)
        monkeypatch.setattr(llm_mod.time, "sleep", lambda d: sleeps.append(d))

        caller = create_llm_caller("k", "http://vendor.test/v1/chat/completions", "m")
        result = caller([{"role": "user", "content": "hi"}], use_tools=False)

        assert posts["n"] == MAX_RETRIES + 1
        assert sleeps == [RETRY_DELAY_BASE * (2 ** i) for i in range(MAX_RETRIES)]
        assert result.get("error_type") == "headers_stall"
        # 耗尽后仍标 retryable，engine 不走 STATE_ERROR 一次判死
        assert result.get("retryable") is True

    def test_fatal_errors_still_not_retryable(self):
        """安全/资源面：auth / 余额不足 / bad_request 不得被 headers_stall 策略带偏。"""
        cases = [
            _classify_error(status_code=401),
            _classify_error(status_code=403),
            _classify_error(
                status_code=429,
                response_body='{"error": {"message": "Insufficient quota", "type": "insufficient_quota"}}',
            ),
            _classify_error(status_code=400),
        ]
        types_and_retry = [(t, r) for t, r, _ in cases]
        assert types_and_retry[0] == ("auth_error", False)
        assert types_and_retry[1] == ("auth_error", False)
        assert types_and_retry[2] == ("fatal_insufficient_quota", False)
        assert types_and_retry[3] == ("bad_request", False)

        # 对照：headers_stall 可重试，且不改写上述分类
        stall_type, stall_retry, _ = _classify_error(
            exception=HeadersStallError("stall")
        )
        assert stall_type == "headers_stall"
        assert stall_retry is True


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
