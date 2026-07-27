"""Unit tests for tools/_url_safety.py — is_url_safe function."""

import pytest
from tools._url_safety import is_url_safe


def test_blocks_127_0_0_1():
    """Loopback address 127.0.0.1 is blocked."""
    safe, reason = is_url_safe("http://127.0.0.1:6379")
    assert safe is False
    assert isinstance(reason, str) and len(reason) > 0


def test_blocks_10_0_0_1():
    """Private Class A address 10.0.0.1 is blocked."""
    safe, reason = is_url_safe("http://10.0.0.1:8080")
    assert safe is False
    assert isinstance(reason, str) and len(reason) > 0


def test_blocks_192_168():
    """Private Class C address 192.168.1.1 is blocked."""
    safe, reason = is_url_safe("http://192.168.1.1")
    assert safe is False
    assert isinstance(reason, str) and len(reason) > 0


def test_allows_public_domain():
    """A public domain name is allowed."""
    safe, reason = is_url_safe("https://example.com")
    assert safe is True
    assert reason == ""


def test_allows_public_ip():
    """A public IP address is allowed."""
    safe, reason = is_url_safe("http://8.8.8.8")
    assert safe is True
    assert reason == ""


def test_rejects_empty():
    """An empty string is rejected (URL 为空)."""
    safe, reason = is_url_safe("")
    assert safe is False
    assert isinstance(reason, str) and len(reason) > 0


def test_blocks_ipv6_localhost():
    """IPv6 loopback ::1 is blocked."""
    safe, reason = is_url_safe("http://[::1]:8080")
    assert safe is False
    assert isinstance(reason, str) and len(reason) > 0
