"""TICKET-COMPUTER-USE-ROUTE 专项测试 — computer use 路由模式开关。

覆盖（票验收）：
1. engine computer_use_mode_getter 接线（_cu_active）。
2. computer use 模式开 → system prompt 注入路由偏好（_cu_system_prompt）；关 → 原样。
3. /computer-use slash 翻转 computer_use_mode[sid] + emit session.computer_use_state。
4. run_engine 签名含 computer_use_mode 参数（链路接通）。
5. server ctx 暴露 computer_use_mode（state 宿主）。
"""

import inspect

import core.engine as eng


def _make_engine(cu_getter=None):
    return eng.Engine(lambda *a, **k: {}, tool_executor=lambda *a, **k: None,
                      computer_use_mode_getter=cu_getter)


def test_engine_cu_off_by_default():
    e = _make_engine()
    assert e._cu_active() is False
    assert e._cu_system_prompt("base") == "base"  # 无注入，零影响


def test_engine_cu_on_injects_route_prompt():
    e = _make_engine(cu_getter=lambda: True)
    assert e._cu_active() is True
    sp = e._cu_system_prompt("本文")
    assert "computer use 模式" in sp
    assert "computer_use" in sp
    assert "快速直接" in sp


def test_engine_cu_llm_kw_tool_round_thinking():
    # 开 + 工具轮 → thinking_disabled=True
    e = _make_engine(cu_getter=lambda: True)
    assert e._cu_llm_kw(True) == {"thinking_disabled": True}
    # 开 + 非工具轮 → 无注入（首次决策轮正常 thinking）
    assert e._cu_llm_kw(False) == {}
    # 关 → 任何情况都恢复默认（无 thinking_disabled）
    e2 = _make_engine(cu_getter=lambda: False)
    assert e2._cu_llm_kw(True) == {}


def test_run_engine_has_computer_use_mode_param():
    from core.engine_adapter import run_engine
    assert "computer_use_mode" in inspect.signature(run_engine).parameters


def test_server_ctx_exposes_computer_use_mode():
    from bobo_tui_gateway.server import _ServerContext
    ctx = _ServerContext()
    assert hasattr(ctx, "computer_use_mode")
    assert ctx.computer_use_mode.get("s1") is None


def test_slash_computer_use_toggle(monkeypatch):
    from bobo_tui_gateway.handlers import prompts
    emitted = []

    class FakeCtx:
        pass

    ctx = FakeCtx()
    ctx.computer_use_mode = {}
    monkeypatch.setattr(prompts, "emit", lambda ev, sid, d: emitted.append((ev, sid, d)))

    # 翻转（无参）→ True
    r = prompts.handle_slash_exec({"command": "computer-use", "session_id": "sx"}, "rid", ctx)
    assert ctx.computer_use_mode.get("sx") is True
    assert emitted and emitted[-1][0] == "session.computer_use_state" and emitted[-1][2]["on"] is True
    # on → 保持 True
    prompts.handle_slash_exec({"command": "computer-use on", "session_id": "sx"}, "rid", ctx)
    assert ctx.computer_use_mode.get("sx") is True
    # off → False
    r2 = prompts.handle_slash_exec({"command": "computer-use off", "session_id": "sx"}, "rid", ctx)
    assert ctx.computer_use_mode.get("sx") is False
    assert emitted[-1][2]["on"] is False
