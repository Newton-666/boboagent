"""票 E4a：living_notes 自动管道失语诊断与修复 — 测试套件

验收金标准：
- C6 裸 except 留痕：write_living_notes 抛异常 → WARNING + notes.error(stage=ln_hook) 且引擎不炸
- C6 提取 LLM error 留痕：→ notes.error(stage=takeaway_extract)
- C6 提取异常留痕：llm_caller 抛异常 → notes.error(stage=takeaway_extract)
- C7 闸门回归：多步骤工具任务完成 → takeaway.extracted + write_living_notes 触发 + notes.written（禁止静默轮）
- B4 根因回归：收工时 history 末尾无 user（多轮工具交替）→ 回溯取到 user，不再静默 return []
- B5 事件链：history 完全无 user → takeaway.skipped 带 reason（不静默）
"""

import pytest

from core.event_bus import event_bus
from tests.test_engine_e2e import (
    FakeLLMCaller,
    FakeToolExecutor,
    _make_test_engine,
    _make_tool_call,
)


@pytest.fixture
def event_recorder(monkeypatch):
    """捕获 event_bus.write 调用（type + data），同时放行真实写入。"""
    recorded = []
    orig_write = event_bus.write

    def _recorder(etype, data):
        recorded.append((etype, data))
        return orig_write(etype, data)

    monkeypatch.setattr(event_bus, "write", _recorder)
    return recorded


def _enable_proactive(engine, mode: str = "subtle"):
    engine.proactive.mode = mode


class _BoomOnSecondCall:
    """第 1 次正常返回，第 2 次（takeaway 提取）抛异常。"""

    def __init__(self):
        self.n = 0

    def __call__(self, messages, **kw):
        self.n += 1
        if self.n >= 2:
            raise RuntimeError("boom in extract")
        return {"choices": [{"message": {"content": "好的，已记住。"}}], "usage": {}}


class TestC6BareExcept:
    """B3：裸 except → WARNING + notes.error（含 sid），引擎不炸"""

    def test_ln_hook_exception_emits_error_event(self, monkeypatch, event_recorder, caplog):
        """write_living_notes 抛异常 → notes.error(stage=ln_hook) + WARNING + 引擎不炸"""
        import tools.living_notes as ln_mod

        def _boom(*a, **kw):
            raise RuntimeError("simulated write failure")

        monkeypatch.setattr(ln_mod, "write_living_notes", _boom)

        fake_llm = FakeLLMCaller([
            (None, [_make_tool_call("c1", "echo", {"msg": "ping"})]),  # 主回合：工具调用
            ("任务完成：echo 执行成功。", None),                        # 工具后：最终文本
            ("用 echo 完成 ping\n工具结果 pong", None),                # 提取回合：takeaways
        ])
        fake_tools = FakeToolExecutor({"echo": "pong"})
        engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)
        _enable_proactive(engine)

        with caplog.at_level("WARNING", logger="core.engine"):
            engine.run(user_input="帮我执行一个命令")

        assert engine.state == engine.STATE_DONE, "引擎不应被笔记失败炸掉"
        types = [t for t, _ in event_recorder]
        assert "notes.error" in types, f"应发 notes.error 事件，实际 {types}"
        err_data = [d for t, d in event_recorder if t == "notes.error"][0]
        assert err_data.get("stage") == "ln_hook"
        assert err_data.get("session_id") == engine.sid
        assert "simulated write failure" in err_data.get("error", "")
        assert any("living notes hook failed" in r.message for r in caplog.records), \
            "应留下 WARNING 日志"

    def test_takeaway_extract_llm_error_emits_error_event(self, monkeypatch, event_recorder, caplog):
        """提取 LLM 返回 error → notes.error(stage=takeaway_extract) + WARNING"""
        fake_llm = FakeLLMCaller([
            ("好的，已记住。", None),
            {"error": "upstream timeout", "error_type": "timeout", "retryable": False},
        ])
        fake_tools = FakeToolExecutor()
        engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)
        _enable_proactive(engine)

        with caplog.at_level("WARNING", logger="core.engine"):
            engine.run(user_input="我决定用 PostgreSQL")

        assert engine.state == engine.STATE_DONE
        types = [t for t, _ in event_recorder]
        assert "notes.error" in types, f"应发 notes.error 事件，实际 {types}"
        err_data = [d for t, d in event_recorder if t == "notes.error"][0]
        assert err_data.get("stage") == "takeaway_extract"
        assert "upstream timeout" in err_data.get("error", "")
        assert any("takeaway extract llm error" in r.message for r in caplog.records)

    def test_takeaway_extract_exception_emits_error_event(self, monkeypatch, event_recorder, caplog):
        """提取阶段 llm_caller 抛异常 → notes.error(stage=takeaway_extract) + WARNING"""
        engine = _make_test_engine(_BoomOnSecondCall(), FakeToolExecutor(), monkeypatch)
        _enable_proactive(engine)

        with caplog.at_level("WARNING", logger="core.engine"):
            engine.run(user_input="我决定用 PostgreSQL")

        assert engine.state == engine.STATE_DONE, "提取异常不应炸引擎"
        types = [t for t, _ in event_recorder]
        assert "notes.error" in types, f"应发 notes.error 事件，实际 {types}"
        err_data = [d for t, d in event_recorder if t == "notes.error"][0]
        assert err_data.get("stage") == "takeaway_extract"
        assert "boom in extract" in err_data.get("error", "")
        assert any("takeaway extract failed" in r.message for r in caplog.records)


class TestC7GateRegression:
    """闸门回归：多步骤任务完成 → 笔记事件链完整（禁止静默轮）"""

    def test_multi_tool_round_emits_notes_written(self, monkeypatch, event_recorder):
        """多步骤工具任务完成 → takeaway.extracted + LN-2 钩子触发 + notes.written"""
        import tools.living_notes as ln_mod

        def _fake_write(takeaways, user_msg, sid, llm_caller, full_reply=""):
            event_bus.write("notes.written", {
                "session_id": sid,
                "path": "library/test/note.md",
                "takeaways": takeaways,
                "source": (user_msg or "")[:20],
            })
            return {"status": "written", "path": "library/test/note.md"}

        monkeypatch.setattr(ln_mod, "write_living_notes", _fake_write)

        fake_llm = FakeLLMCaller([
            (None, [_make_tool_call("c1", "echo", {"msg": "ping"})]),
            ("任务完成：echo 执行成功。", None),
            ("用 echo 完成 ping\n任务已交付", None),
        ])
        fake_tools = FakeToolExecutor({"echo": "pong"})
        engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)
        _enable_proactive(engine)

        engine.run(user_input="帮我执行一个命令")

        assert engine.state == engine.STATE_DONE
        types = [t for t, _ in event_recorder]
        # 事件链：提取成功 → 笔记写入，全程无静默轮
        assert "takeaway.extracted" in types, f"应有 takeaway.extracted，实际 {types}"
        assert "notes.written" in types, f"LN-2 钩子应触发写笔记，实际 {types}"
        wr = [d for t, d in event_recorder if t == "notes.written"][0]
        assert wr.get("session_id") == engine.sid


class TestB4RootCause:
    """B4 根因回归：user 消息窗口回溯，禁止静默短路"""

    def test_history_tail_no_user_backtracks(self, monkeypatch, event_recorder):
        """收工时 history[-4:] 无 user（多轮工具交替）→ 回溯 20 条取到 user，产出 takeaways"""
        fake_llm = FakeLLMCaller([
            ("用 echo 完成 ping\n工具结果 pong", None),  # 直接调 _extract_takeaways：第一次调用即提取
        ])
        fake_tools = FakeToolExecutor({"echo": "pong"})
        engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)
        _enable_proactive(engine)

        # 收工形态：末尾 4 条全为 assistant(tool_calls)/tool（无 user）
        engine.history = [
            {"role": "user", "content": "帮我跑一个命令"},
            {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "echo"}}]},
            {"role": "tool", "content": "pong"},
            {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "echo"}}]},
            {"role": "tool", "content": "pong2"},
        ]
        engine.current_tool_round = 2

        takeaways = engine._extract_takeaways(fallback_content="收工总结：任务完成")

        assert takeaways, "修复后应回溯取到 user 消息并产出 takeaways（修复前为静默 []）"
        types = [t for t, _ in event_recorder]
        assert "takeaway.extracted" in types
        # 不应出现静默短路的特征事件（无 reason 的跳过）
        assert not any(t == "takeaway.skipped" for t in types), "不应走到 skipped 分支"

    def test_no_user_at_all_emits_skipped_reason(self, monkeypatch, event_recorder):
        """history 完全无 user 且无 fallback → takeaway.skipped(no_user_msg_in_window) 不静默"""
        fake_llm = FakeLLMCaller([("好的。", None)])
        fake_tools = FakeToolExecutor()
        engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)
        _enable_proactive(engine)

        engine.history = [
            {"role": "assistant", "content": "开场白"},
            {"role": "tool", "content": "结果"},
            {"role": "assistant", "content": "更多"},
        ]

        takeaways = engine._extract_takeaways(fallback_content="")

        assert takeaways == []
        types = [t for t, _ in event_recorder]
        assert "takeaway.skipped" in types, f"应留 skipped 原因事件，实际 {types}"
        data = [d for t, d in event_recorder if t == "takeaway.skipped"][0]
        assert data.get("reason") == "no_user_msg_in_window", \
            f"reason 应为 no_user_msg_in_window，实际 {data.get('reason')}"

    def test_empty_history_emits_skipped_reason(self, monkeypatch, event_recorder):
        """history 全空且无 fallback → takeaway.skipped(no_history_content) 不静默"""
        fake_llm = FakeLLMCaller([("好的。", None)])
        fake_tools = FakeToolExecutor()
        engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)
        _enable_proactive(engine)
        engine.history = []

        takeaways = engine._extract_takeaways(fallback_content="")

        assert takeaways == []
        types = [t for t, _ in event_recorder]
        assert "takeaway.skipped" in types, f"应留 skipped 原因事件，实际 {types}"
        data = [d for t, d in event_recorder if t == "takeaway.skipped"][0]
        assert data.get("reason") == "no_history_content"
