"""TICKET-GUI-F19b 集成验证 — reasoning.delta 事件链路闭环。

验证：engine._notify("reasoning.delta") → engine_adapter.on_event 转发 → emit 输出。
用 monkeypatch 捕获 emit，驱动 adapter 的 on_event，断言 reasoning.delta 被转发且带 text/session_id。
"""

import pytest


def test_reasoning_delta_forwarded(monkeypatch):
    """adapter 的 on_event 应转发 reasoning.delta（此前缺失分支）。"""
    from core import engine_adapter

    # on_event 是 run_engine 内部闭包，emit 是注入参数——静态断言分支存在 + 字段透传
    import inspect
    src = inspect.getsource(engine_adapter)
    assert 'event_type == "reasoning.delta"' in src, "adapter 缺 reasoning.delta 分支"
    assert 'emit("reasoning.delta", sid, {' in src, "adapter 缺 reasoning.delta emit"
    assert '"text": data.get("text", "")' in src, "adapter 缺 text 字段透传"
    assert '"session_id": sid' in src, "adapter 缺 session_id"


def test_reasoning_delta_engine_source(monkeypatch):
    """engine 侧 _on_reasoning 发 reasoning.delta（源头存在）。"""
    from core import engine

    src = _read_engine_src()
    assert '_notify("reasoning.delta", {"text": token})' in src, \
        "engine 缺 reasoning.delta 通知"


def _read_engine_src():
    from pathlib import Path
    p = Path(__file__).resolve().parent.parent / "core" / "engine.py"
    return p.read_text(encoding="utf-8")


def test_reasoning_delta_frontend_listener():
    """前端 dist/index.html 有 reasoning.delta 监听（闭环最后一环）。"""
    from pathlib import Path
    p = Path(__file__).resolve().parent.parent / "apps" / "desktop" / "dist" / "index.html"
    src = p.read_text(encoding="utf-8")
    assert "on('reasoning.delta'" in src, "前端缺 reasoning.delta 监听"
    assert "reasoningText += t" in src, "前端缺推理缓冲累积"
