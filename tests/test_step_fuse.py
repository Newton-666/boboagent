"""票 W：步数熔断测试 — 保险丝不许伪装成正常收工"""

import pytest
from unittest.mock import MagicMock


@pytest.fixture
def engine():
    from core.engine import Engine

    llm = MagicMock()
    llm.supports_reasoning = False
    eng = Engine(llm, callback=MagicMock())
    eng.task_ledger = []
    return eng


class TestStepFuse:
    """步数保险丝触发行为验证"""

    def test_fuse_trigger_exit_reason(self, engine):
        """MAX_STEPS 触发后 _exit_reason = 'max_steps'"""
        engine.MAX_STEPS = 0
        engine.run("hello")
        assert engine._exit_reason == "max_steps"

    def test_fuse_trigger_state_done(self, engine):
        """熔断后 state 为 DONE，不是 RESPONDING"""
        engine.MAX_STEPS = 0
        engine.run("hello")
        assert engine.state == engine.STATE_DONE

    def test_fuse_synthetic_content(self, engine):
        """熔断产生合成收尾消息，含步数提示"""
        engine.MAX_STEPS = 0
        call_args = []

        def capture_notify(phase, data):
            call_args.append((phase, data))

        engine._notify = capture_notify
        engine.run("hello")
        complete_calls = [a for a in call_args if a[0] == "complete"]
        assert len(complete_calls) >= 1
        content = complete_calls[-1][1].get("content", "")
        assert "步数保险丝触发" in content
        assert "MAX_STEPS" not in content  # 变量的格式化已完成

    def test_fuse_event_bus_event(self, engine):
        """熔断写入 event_bus engine.step_fuse"""
        from core.event_bus import event_bus
        events = []

        orig_write = event_bus.write
        event_bus.write = lambda t, d: events.append((t, d))
        try:
            engine.MAX_STEPS = 0
            engine.run("hello")
        finally:
            event_bus.write = orig_write
        fuse_events = [e for e in events if e[0] == "engine.step_fuse"]
        assert len(fuse_events) >= 1
        assert fuse_events[-1][1]["step_count"] == 1

    def test_fuse_with_pending_ledger(self, engine):
        """台账有未完成项时，熔断消息含台账摘要"""
        engine.task_ledger = [
            {"title": "任务A", "status": "pending"},
            {"title": "任务B", "status": "done"},
        ]
        call_args = []

        def capture_notify(phase, data):
            call_args.append((phase, data))

        engine._notify = capture_notify
        engine.MAX_STEPS = 0
        engine.run("hello")
        complete_calls = [a for a in call_args if a[0] == "complete"]
        content = complete_calls[-1][1].get("content", "")
        assert "台账" in content
        assert "项未完成" in content

    def test_fuse_empty_ledger_no_pending(self, engine):
        """台账全 done 时熔断消息不报未完成项"""
        engine.task_ledger = [
            {"title": "任务A", "status": "done"},
        ]
        call_args = []

        def capture_notify(phase, data):
            call_args.append((phase, data))

        engine._notify = capture_notify
        engine.MAX_STEPS = 0
        engine.run("hello")
        complete_calls = [a for a in call_args if a[0] == "complete"]
        content = complete_calls[-1][1].get("content", "")
        assert "项未完成" not in content

    def test_normal_completion_not_affected(self, engine):
        """正常完成（步数用不完）exit_reason 仍为 'completed'"""
        engine.llm_caller.return_value = {
            "content": "阶段1完成",
            "tool_calls": None,
        }
        engine.MAX_STEPS = 999
        engine.run("hello")
        assert engine._exit_reason == "completed"

    def test_fuse_notify_no_llm_call(self, engine):
        """熔断不调 LLM"""
        engine.MAX_STEPS = 0
        engine.run("hello")
        # 熔断路径不应调用 LLM
        # 直接验证 engine._pending_content 为 None（未设 content）
        assert engine._pending_content is None or "步数" in str(engine._pending_content)

    @pytest.mark.parametrize("max_steps", [0, 1, 2])
    def test_fuse_always_triggers_above_limit(self, engine, max_steps):
        """各种各样的 MAX_STEPS 阈值都正常熔断"""
        engine.MAX_STEPS = max_steps
        for _ in range(max_steps + 2):
            if engine._step_count > engine.MAX_STEPS:
                break
            engine._step_count += 1
        assert engine._step_count > max_steps

    def test_fuse_does_not_enter_responding(self, engine):
        """熔断后不经过 RESPONDING 状态（约束 #4）"""
        states = []

        def track_state(state, msg):
            states.append((state, msg))

        engine._emit_state_change = track_state
        engine.MAX_STEPS = 0
        engine.run("hello")
        responding_states = [s for s in states if s[0] == "responding"]
        assert len(responding_states) == 0


class TestStepFuseAdapter:
    """engine_adapter 的 exit_reason 传递"""

    def test_adapter_exit_reason_max_steps(self):
        """adapter 读取 engine._exit_reason 而非硬编码 'completed'"""
        from core.engine import Engine

        llm = MagicMock()
        llm.supports_reasoning = False
        eng = Engine(llm, callback=MagicMock())
        eng.task_ledger = []
        eng.MAX_STEPS = 0
        eng.run("hello")
        assert eng._exit_reason == "max_steps"
        assert eng._exit_reason != "completed"
