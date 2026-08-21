"""TICKET-PROVIDER-CONTEXT-MODEL 专项测试 — 模型上下文窗口声明体系化（COST-3）。

覆盖（票验收）：
- ① kimi-k3 窗口=1000000（精确修正，官方 1M）
- ② deepseek-v4-future（模拟未精确声明新模型）前缀继承 → 1M
- ③ 未声明模型 → 该 provider 默认 + warn 告警（不再静默低估）
- ④ kimi-k2.* 家族继承 → 256K
- ⑤ 实弹：deepseek-v4-flash-vision-exp → 1M
"""

import logging

import pytest


def _set_backend(monkeypatch, provider_name, model):
    monkeypatch.setenv("BOBO_PROVIDER", provider_name)
    monkeypatch.setenv("API_MODEL_NAME", model)
    monkeypatch.delenv("BOBO_CONTEXT_LENGTH", raising=False)


def test_kimi_k3_window_1m(monkeypatch):
    """① kimi-k3 精确命中 model_context → 1M。"""
    _set_backend(monkeypatch, "moonshot", "kimi-k3")
    from core.provider import get_context_length
    assert get_context_length() == 1_000_000


def test_deepseek_v4_future_inherits_1m(monkeypatch):
    """② deepseek-v4-future（新模型未精确声明）→ 前缀继承 1M。"""
    _set_backend(monkeypatch, "deepseek", "deepseek-v4-future")
    from core.provider import get_context_length
    assert get_context_length() == 1_000_000


def test_undeclared_model_uses_provider_default_and_warns(monkeypatch, caplog):
    """③ deepseek-chat-unknown 未精确声明也不匹配前缀 → provider 默认 128K + warn。"""
    _set_backend(monkeypatch, "deepseek", "deepseek-chat-unknown")
    from core.provider import get_context_length
    with caplog.at_level(logging.WARNING, logger="core.provider"):
        assert get_context_length() == 128_000
        assert any("COST-3" in r.message for r in caplog.records), "应打 COST-3 warn 告警"


def test_kimi_k2_family_inherits_256k(monkeypatch):
    """④ kimi-k2.9（模拟未精确声明家族新模型）→ 家族继承 256K。"""
    _set_backend(monkeypatch, "moonshot", "kimi-k2.9")
    from core.provider import get_context_length
    assert get_context_length() == 262_144


def test_deepseek_v4_flash_vision_exp_1m(monkeypatch):
    """⑤ 实弹验收：deepseek-v4-flash-vision-exp → 1M。"""
    _set_backend(monkeypatch, "deepseek", "deepseek-v4-flash-vision-exp")
    from core.provider import get_context_length
    assert get_context_length() == 1_000_000
