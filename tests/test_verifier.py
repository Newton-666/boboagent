"""Unit tests for core/verifier.py — Verifier class."""

import pytest
from core.verifier import Verifier


def test_detects_completion():
    """needs_verification returns True when a completion marker is present."""
    v = Verifier()
    assert v.needs_verification("已完成修复") is True


def test_ignores_non_completion():
    """needs_verification returns False for a non-completion response."""
    v = Verifier()
    assert v.needs_verification("让我看看") is False


def test_injects_hint():
    """check_and_inject appends two entries to history and returns True."""
    v = Verifier()
    history = []
    result = v.check_and_inject(history, "已完成")
    assert result is True
    assert len(history) == 2
    assert history[0]["role"] == "assistant"
    assert history[1]["role"] == "system"


def test_no_double():
    """Second call to check_and_inject returns False after first succeeded."""
    v = Verifier()
    history = []
    # First call — should inject
    assert v.check_and_inject(history, "已完成") is True
    # Second call — attempted is already True, should not inject
    assert v.check_and_inject(history, "已完成") is False
