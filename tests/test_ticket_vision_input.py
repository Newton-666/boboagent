"""TICKET-VISION-INPUT 专项测试 — 图片视觉输入管道。

覆盖（票验收）：
1. read_local_file 读图片 → 走视觉分支（真实构造多模态 content），返回"[视觉描述] ..."。
2. 非 vision 模型读图 → 明确报错"不支持图像输入 vision"（不静默）。
3. llm_caller multimodal content 透传：content 为 list 时 payload["messages"] 原样发（流式/非流式共用）。
4. supports_vision 判定（DeepSeek vision-exp=True，普通模型=False，gpt-4o=True）。
"""

import pytest

from core import llm_caller as lc
from core import provider as prov
import tools.read_local_file as rlf

# 最小 PNG 头（_describe_image 只需要能 base64 读 + mime 判定，无需真合法图片）
_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


def test_describe_image_returns_vision(monkeypatch, tmp_path):
    """读图片 → 视觉模型描述（mock LLM），返回视觉描述而非二进制报错。"""
    img = tmp_path / "t.png"
    img.write_bytes(_PNG)
    monkeypatch.setattr(prov, "resolve_provider", lambda *a, **k: {
        "name": "deepseek", "model": "deepseek-v4-flash-vision-exp",
        "api_key": "k", "base_url": "https://api.deepseek.com/v1/chat/completions"})
    monkeypatch.setattr(prov, "supports_vision", lambda n, m: True)

    captured = {}

    def _fake_create_llm(api_key, api_url, model_name, tools_schema=None, provider_proto=None):
        def _llm(messages, **kw):
            captured["messages"] = messages
            # 多模态 content：第二个元素是 image_url + base64 data URL
            assert messages[0]["content"][0]["type"] == "text"
            assert messages[0]["content"][1]["type"] == "image_url"
            assert messages[0]["content"][1]["image_url"]["url"].startswith("data:image/png;base64,")
            return {"choices": [{"message": {"content": "这是一张红色图片"}}]}
        return _llm

    monkeypatch.setattr(lc, "create_llm_caller", _fake_create_llm)
    out = rlf.execute(str(img))
    assert "[视觉描述]" in out and "红色图片" in out, out
    # 断言确实构造了多模态 content（base64 data URL + text）
    assert len(captured["messages"][0]["content"]) == 2


def test_non_vision_model_reports_error(monkeypatch, tmp_path):
    """非 vision 模型读图 → 明确报错（不静默）。"""
    img = tmp_path / "t.png"
    img.write_bytes(_PNG)
    monkeypatch.setattr(prov, "resolve_provider", lambda *a, **k: {
        "name": "deepseek", "model": "deepseek-v4-flash",
        "api_key": "k", "base_url": "u"})
    monkeypatch.setattr(prov, "supports_vision", lambda n, m: False)
    out = rlf.execute(str(img))
    assert "不支持图像输入 vision" in out and "deepseek-v4-flash" in out, out


def test_supports_vision_rules():
    """supports_vision 判定：DeepSeek vision-exp=True，普通=False，gpt-4o=True。"""
    assert prov.supports_vision("deepseek", "deepseek-v4-flash-vision-exp") is True
    assert prov.supports_vision("deepseek", "deepseek-v4-flash") is False
    assert prov.supports_vision("openai", "gpt-4o") is True
    assert prov.supports_vision("openai", "gpt-3.5-turbo") is False
    assert prov.supports_vision("moonshot", "kimi-k3") is False
    assert prov.supports_vision("unknown", "x") is False


def test_multimodal_content_passthrough(monkeypatch):
    """llm_caller 透传：content 为 list（text + image_url）时 payload 原样发。"""
    captured = {}

    class _Resp:
        status_code = 200
        text = ""

        def json(self):
            return {"choices": [{"message": {"content": "ok"}}]}

    def _fake_post(url, json=None, headers=None, timeout=None, stream=False,
                   headers_timeout=None, event_bus=None, session_id=None, _interrupt_event=None):
        captured["messages"] = json.get("messages")
        return _Resp()

    monkeypatch.setattr(lc, "_post_with_headers_watchdog", _fake_post)
    caller = lc.create_llm_caller("k", "http://api", "deepseek-v4-flash-vision-exp")
    msgs = [{"role": "user", "content": [
        {"type": "text", "text": "描述"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
    ]}]
    caller(msgs, use_tools=False)
    assert captured["messages"] == msgs, "multimodal content 应原样透传"
