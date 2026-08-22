"""TICKET-VISION-CHAT-UPLOAD 后端专项测试 — prompt.submit 图片转多模态。

覆盖（票验收）：
1. 带图 → 把 text+image 合成 content list（text + image_url）注入 session 历史。
2. 非 vision 模型发图 → 明确报错（不静默），不动 session 历史。
3. 无图纯文字 → 绝对兼容（不注入 content list，引擎收原文 text）。
"""

import threading

import pytest

import bobo_tui_gateway.handlers.prompts as prompts
from core import provider as prov


class _FakeCtx:
    def __init__(self):
        self.sessions = {"s1": {"id": "s1", "messages": []}}
        self.sessions_lock = threading.Lock()
        self.engine_cache = {}
        self.pending_confirm = {}
        self.pending_confirm_result = {}
        self.confirm_lock = threading.Lock()
        self.auto_mode = {}
        self.computer_use_mode = {}  # TICKET-COMPUTER-USE-ROUTE：migration 后 handle_prompt_submit 需访问
        self.current_engines = {}
        self.current_engines_lock = threading.Lock()
        self.active_engine_threads = {}
        self.engine_threads_lock = threading.Lock()
        self.session_usage = {}
        self.session_usage_lock = threading.Lock()
        self.save_session_to_disk = lambda s: None


class _FakeThread:
    def __init__(self, target=None, args=None, name=None, daemon=None):
        self.target = target
        self.args = args
        self.name = name
        self.daemon = daemon

    def start(self):
        pass


def _patch_common(monkeypatch, model="deepseek-v4-flash-vision-exp", vision=True):
    monkeypatch.setattr(prompts, "_cancel_engine_and_wait", lambda sid, **k: True)
    monkeypatch.setattr(prompts, "register_engine_thread", lambda *a, **k: None)
    monkeypatch.setattr(prompts.threading, "Thread", _FakeThread)
    monkeypatch.setattr(prov, "resolve_provider", lambda *a, **k: {
        "name": "deepseek", "model": model,
        "api_key": "k", "base_url": "https://api.deepseek.com/v1/chat/completions"})
    monkeypatch.setattr(prov, "supports_vision", lambda n, m: vision)


def _relay_off(monkeypatch):
    import tools.relay_hooks as rh
    monkeypatch.setattr(rh, "is_active", lambda sid: False)


def test_prompt_submit_image_injects_multimodal(monkeypatch):
    """带图 → 注入 content list（text + image_url）到 session 历史，返回 ok。"""
    _patch_common(monkeypatch)
    _relay_off(monkeypatch)
    ctx = _FakeCtx()
    img = "data:image/png;base64,AAAA"
    r = prompts.handle_prompt_submit(
        {"session_id": "s1", "text": "这是什么图片", "image": img}, "rid", ctx)
    assert r["result"]["ok"] is True, r
    msgs = ctx.sessions["s1"]["messages"]
    assert len(msgs) == 1
    m = msgs[0]
    assert m["role"] == "user"
    assert isinstance(m["content"], list)
    assert m["content"][0] == {"type": "text", "text": "这是什么图片"}
    assert m["content"][1] == {"type": "image_url", "image_url": {"url": img}}


def test_prompt_submit_non_vision_reports(monkeypatch):
    """非 vision 模型发图 → 明确报错，不动 session 历史。"""
    _patch_common(monkeypatch, model="deepseek-v4-flash", vision=False)
    _relay_off(monkeypatch)
    ctx = _FakeCtx()
    r = prompts.handle_prompt_submit(
        {"session_id": "s1", "text": "这是什么", "image": "data:image/png;base64,AA"},
        "rid", ctx)
    assert "error" in r, r
    assert "不支持看图" in str(r), r
    # 非 vision 不注入多模态历史
    assert ctx.sessions["s1"]["messages"] == []


def test_prompt_submit_no_image_compatible(monkeypatch):
    """无图纯文字 → 绝对兼容：不注入 content list，引擎收原文 text。"""
    _patch_common(monkeypatch)
    _relay_off(monkeypatch)
    ctx = _FakeCtx()
    r = prompts.handle_prompt_submit({"session_id": "s1", "text": "你好"}, "rid", ctx)
    assert r["result"]["ok"] is True, r
    # 不注入任何多模态历史
    assert ctx.sessions["s1"]["messages"] == []
