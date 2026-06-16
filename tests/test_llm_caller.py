"""Tests for core/llm_caller.py — _classify_error function.

Verifies that HTTP status codes and network exceptions are correctly
classified so the retry logic works properly.
"""

import pytest
import requests
import json
from core.llm_caller import _classify_error


class TestHTTPStatusCodeClassification:
    """Classification based on HTTP response status codes."""

    def test_200_is_not_an_error(self):
        # _classify_error with status_code=None would return unknown;
        # the function is only called when there IS an error (status != 200)
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
