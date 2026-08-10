"""票 AUTO-G3：prompt.submit 中断等待窗口修复测试。

E-1 中断保进度让引擎退出从"立即 return"变为"先落盘再退出"（1-2s），
原 cancel 后 0.3s 单次检查窗口配不上新退出时长 → 改为 100ms 轮询、最长 3 秒。
验证（终审口径逐条）：
  1. 引擎退出耗时 1.5s → submit 成功无报错（等待窗口放大后放行）
  2. 引擎永不退出 → 3 秒后报原错误（兜底钉死）
  3. 引擎未运行 → 不进入等待，立即受理（零回归路径）
  4. /duo 商讨路径同逻辑一并修复
"""

import threading
import time

import core.duo_orchestrator as duo_orch
import core.engine_adapter as engine_adapter
from bobo_tui_gateway.handlers import prompts as prompts_mod


class _FakeCtx:
    """handle_prompt_submit / handle_slash_exec 所需 ctx 的最小替身。"""

    def __init__(self):
        self.sessions_lock = threading.Lock()
        self.sessions = {"s1": {"messages": []}}
        self.active_engine_threads = []
        self.engine_threads_lock = threading.Lock()
        self.pending_confirm = {}
        self.pending_confirm_result = {}
        self.confirm_lock = threading.Lock()
        self.auto_mode = {}
        self.current_engines = {}
        self.current_engines_lock = threading.Lock()
        self.session_usage = {}
        self.session_usage_lock = threading.Lock()
        self.save_session_to_disk = lambda sid: None
        self.engine_cache = {}


def _patch_engine_state(monkeypatch, running_sids, exit_delay=0.0, never_exit=False):
    """桩住 engine_adapter.is_running / cancel，模拟引擎退出窗口。

    exit_delay>0 时：cancel 后经过 exit_delay 秒，sid 才从 running 消失
    （模拟 E-1 落盘退出 1-2s）；never_exit=True 时永不消失。
    """
    state = {"running": set(running_sids), "cancel_called": [], "_cancelled_at": {}}

    def fake_is_running(sid):
        if sid not in state["running"]:
            return False
        if not never_exit and sid in state["_cancelled_at"]:
            if time.monotonic() - state["_cancelled_at"][sid] >= exit_delay:
                state["running"].discard(sid)
                return False
        return True

    def fake_cancel(sid):
        state["cancel_called"].append(sid)
        state["_cancelled_at"][sid] = time.monotonic()

    monkeypatch.setattr(engine_adapter, "is_running", fake_is_running)
    monkeypatch.setattr(engine_adapter, "cancel", fake_cancel)
    return state


def _patch_run_engine(monkeypatch):
    """桩住 run_engine，避免 submit 真实启动引擎线程。"""
    calls = []

    def fake_run_engine(*args, **kwargs):
        calls.append(args)

    monkeypatch.setattr(engine_adapter, "run_engine", fake_run_engine)
    return calls


class TestSubmitWaitWindow:
    def test_slow_engine_exit_1_5s_submit_succeeds(self, monkeypatch):
        """验收 1：引擎退出耗时 1.5s → submit 成功，无报错。"""
        state = _patch_engine_state(monkeypatch, running_sids={"s1"}, exit_delay=1.5)
        _patch_run_engine(monkeypatch)
        ctx = _FakeCtx()

        start = time.monotonic()
        result = prompts_mod.handle_prompt_submit(
            {"session_id": "s1", "text": "继续"}, "rid-1", ctx
        )
        elapsed = time.monotonic() - start

        assert state["cancel_called"] == ["s1"], "引擎在跑必须先 cancel"
        assert result["result"].get("ok") is True, "等待窗口内退出 → 必须受理，不报错"
        assert "无法取消" not in str(result), "不得报中断失败错误"
        assert elapsed >= 1.4, "确实等了引擎退出（1.5s 窗口），而非立即放行"

    def test_never_exiting_engine_hits_original_error(self, monkeypatch):
        """验收 2：引擎永不退出 → 3 秒后报原错误（兜底钉死）。"""
        state = _patch_engine_state(monkeypatch, running_sids={"s1"}, never_exit=True)
        _patch_run_engine(monkeypatch)
        ctx = _FakeCtx()

        start = time.monotonic()
        result = prompts_mod.handle_prompt_submit(
            {"session_id": "s1", "text": "继续"}, "rid-2", ctx
        )
        elapsed = time.monotonic() - start

        assert state["cancel_called"] == ["s1"]
        assert result.get("error", {}).get("message") == "无法取消上一个请求，请稍后重试"
        assert elapsed >= 2.9, f"兜底必须等满 3 秒窗口（实际 {elapsed:.2f}s）"

    def test_engine_not_running_skips_wait(self, monkeypatch):
        """验收 3：引擎未运行 → 不进入等待，立即受理（零回归路径）。"""
        state = _patch_engine_state(monkeypatch, running_sids=set())
        run_calls = _patch_run_engine(monkeypatch)
        ctx = _FakeCtx()

        start = time.monotonic()
        result = prompts_mod.handle_prompt_submit(
            {"session_id": "s1", "text": "新消息"}, "rid-3", ctx
        )
        elapsed = time.monotonic() - start

        assert state["cancel_called"] == [], "未运行不得调 cancel"
        assert result["result"].get("ok") is True
        assert len(run_calls) == 1, "引擎线程照常启动"
        assert elapsed < 0.5, f"未运行必须零等待（实际 {elapsed:.3f}s）"

    def test_cancel_and_wait_helper_direct(self, monkeypatch):
        """辅助函数直测：100ms 轮询、引擎消失立即放行（不等到 3s 上限）。"""
        state = _patch_engine_state(monkeypatch, running_sids={"s1"}, exit_delay=0.4)

        start = time.monotonic()
        ok_flag = prompts_mod._cancel_engine_and_wait("s1")
        elapsed = time.monotonic() - start

        assert ok_flag is True
        assert state["cancel_called"] == ["s1"]
        assert 0.3 <= elapsed < 2.5, f"应随引擎消失立即放行，而非死等 3s（实际 {elapsed:.2f}s）"


class TestSlashDuoWaitWindow:
    def test_duo_slow_exit_submits_ok(self, monkeypatch):
        """验收 4：/duo 商讨路径——引擎退出耗时 1.5s → 无报错，商讨照常启动。"""
        state = _patch_engine_state(monkeypatch, running_sids={"s1"}, exit_delay=1.5)
        duo_calls = []

        def fake_run_deliberation(question, emit, sid):
            duo_calls.append((question, sid))

        monkeypatch.setattr(duo_orch, "run_deliberation", fake_run_deliberation)
        ctx = _FakeCtx()

        result = prompts_mod.handle_slash_exec(
            {"command": "duo 商讨：如何提升测试覆盖率", "session_id": "s1"}, "rid-4", ctx
        )

        assert state["cancel_called"] == ["s1"]
        assert "双员商讨已启动" in result["result"]["output"]
        assert len(duo_calls) == 1
        assert "无法取消" not in str(result)

    def test_duo_never_exit_hits_error(self, monkeypatch):
        """验收 4 兜底：/duo 商讨路径引擎永不退出 → 3 秒后报原错误。"""
        state = _patch_engine_state(monkeypatch, running_sids={"s1"}, never_exit=True)
        ctx = _FakeCtx()

        result = prompts_mod.handle_slash_exec(
            {"command": "duo 商讨：如何提升测试覆盖率", "session_id": "s1"}, "rid-5", ctx
        )

        assert state["cancel_called"] == ["s1"]
        assert result.get("error", {}).get("message") == "无法取消上一个请求，请稍后重试"
