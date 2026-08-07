"""Tests for Engine core state machine — states, checkpoints, teaching mode, undo."""

import os
import sys
import json
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.engine import Engine
from core.tool_executor import execute_tool
from tests.mock_llm import MockLLMCaller, text_response, tool_response


class TestEngineBasicFlow:
    """Test the basic conversation flow through the state machine."""

    def test_simple_text_response(self):
        caller = MockLLMCaller([text_response("Hello! I am Bobo.")])
        engine = Engine(caller, execute_tool, test_mode=True)
        engine.run("say hi")
        assert engine.state == Engine.STATE_DONE
        assert len(engine.history) >= 2  # user + assistant
        assert any("Hello" in str(m) for m in engine.history)

    def test_tool_call_then_text(self):
        """Engine should execute a tool call, then respond with text."""
        caller = MockLLMCaller([
            tool_response("get_current_time"),
            text_response("现在是下午3点。"),
        ])
        engine = Engine(caller, execute_tool, test_mode=True)
        engine.run("现在几点了")
        assert engine.state == Engine.STATE_DONE
        # Should have: user -> assistant(tc) -> tool_result -> assistant(text)
        assert len(engine.history) >= 3

    def test_max_steps_termination(self):
        """Engine should stop with ERROR state after exceeding MAX_STEPS."""
        tool_calls = []
        for _ in range(Engine.MAX_STEPS + 5):
            tool_calls.append(tool_response("get_current_time"))
        caller = MockLLMCaller(tool_calls)
        engine = Engine(caller, execute_tool, test_mode=True)
        engine.run("loop forever")
        # 2026-07-29: 票 W 步数熔断 — MAX_STEPS 耗尽后引擎直接 STATE_DONE，不经过 RESPONDING（约束 #4）
        assert engine.state == Engine.STATE_DONE

    def test_history_preserved_across_multiple_runs(self):
        caller = MockLLMCaller([
            text_response("First response."),
            text_response("Second response."),
        ])
        engine = Engine(caller, execute_tool, test_mode=True)
        engine.run("first question")
        engine.run("second question")
        # Should have 5 messages: plan_reminder, user1, assistant1, user2, assistant2
        assert len(engine.history) == 5

    def test_reset_clears_history(self):
        caller = MockLLMCaller([text_response("ok")])
        engine = Engine(caller, execute_tool, test_mode=True)
        engine.run("test")
        assert len(engine.history) > 0
        engine.reset()
        assert len(engine.history) == 0


class TestTeachingMode:
    """Tests for the teaching/skill recording mode."""

    def test_enter_teaching_mode(self, engine):
        result = engine._handle_teaching_mode("开始教学")
        assert "教学模式" in result
        assert engine.teaching_mode is True
        assert engine.recorded_messages == []

    def test_cancel_teaching_mode(self, engine):
        engine.teaching_mode = True
        engine.recorded_messages = [{"role": "user", "content": "test"}]
        result = engine._handle_teaching_mode("取消教学")
        assert engine.teaching_mode is False
        assert engine.recorded_messages == []
        assert "已取消" in result

    def test_save_skill_without_name(self, engine):
        engine.teaching_mode = True
        engine.recorded_messages = [{"role": "user", "content": "test"}]
        result = engine._handle_teaching_mode("保存为 skill")
        assert "请指定" in result
        assert engine.teaching_mode is True  # Still in teaching mode

    def test_save_skill_with_name(self, engine, tmp_path, monkeypatch):
        # TICKET-E3a：新版 SkillManager 落盘到 _standards_dir()/name/standard.md，
        # 测试 patch 静态方法指向 tmp_path，避免写入真实 data/skill-standards/
        from core.skill_manager import SkillManager
        monkeypatch.setattr(
            SkillManager, "_standards_dir", staticmethod(lambda: tmp_path)
        )

        engine.teaching_mode = True
        engine.recorded_messages = [
            {"role": "user", "content": "帮我搜索"},
            {"role": "assistant", "content": "好的"},
        ]
        result = engine._handle_teaching_mode("保存为 skill search_test")
        assert "已保存" in result
        assert engine.teaching_mode is False

        # 录制保存到 data/skill-standards/（tmp_path）而非 skills/*.yaml
        std_path = tmp_path / "search_test" / "standard.md"
        assert std_path.is_file(), f"standard.md not found at {std_path}"


class TestUndoCheckpoint:
    """Tests for conversation undo/checkpoint system (delegates to CheckpointManager)."""

    def test_save_checkpoint_adds_to_list(self, engine):
        initial_count = len(engine.checkpoint_mgr.checkpoints)
        engine.checkpoint_mgr.save(label="test_step")
        assert len(engine.checkpoint_mgr.checkpoints) == initial_count + 1

    def test_checkpoint_stores_history(self, engine):
        engine.history = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]
        engine.checkpoint_mgr.save(label="my_checkpoint")
        cp = engine.checkpoint_mgr.checkpoints[-1]
        assert cp["label"] == "my_checkpoint"
        assert cp["history"] == engine.history
        assert cp["depth"] == engine.current_depth

    def test_max_checkpoints_limit(self, engine):
        for i in range(engine.checkpoint_mgr.MAX_CHECKPOINTS + 5):
            engine.checkpoint_mgr.save(label=f"step_{i}")
        assert len(engine.checkpoint_mgr.checkpoints) <= engine.checkpoint_mgr.MAX_CHECKPOINTS

    def test_find_checkpoint_by_label(self, engine):
        engine.checkpoint_mgr.save(label="important_step")
        idx = engine.checkpoint_mgr.find("important")
        assert idx is not None

    def test_find_checkpoint_by_number(self, engine):
        engine.checkpoint_mgr.save(label="step_1")
        engine.checkpoint_mgr.save(label="step_2")
        engine.checkpoint_mgr.save(label="step_3")
        # Go back 1 step
        idx = engine.checkpoint_mgr.find("1")
        assert idx == len(engine.checkpoint_mgr.checkpoints) - 2

    def test_find_checkpoint_not_found(self, engine):
        idx = engine.checkpoint_mgr.find("nonexistent_target_string")
        assert idx is None

    def test_do_undo_restores_history(self, engine):
        original_history = [
            {"role": "user", "content": "step 1"},
            {"role": "assistant", "content": "reply 1"},
        ]
        engine.history = list(original_history)
        engine.checkpoint_mgr.save(label="before_bad_change")

        # Simulate a bad change
        engine.history.append({"role": "user", "content": "bad step"})
        engine.history.append({"role": "assistant", "content": "bad reply"})

        success, msg, history, depth, tool_round, label = engine.checkpoint_mgr.undo()
        assert success
        assert "已回退" in msg
        assert history == original_history

    def test_do_undo_with_no_checkpoints(self, engine):
        engine.checkpoint_mgr.clear()
        success, msg, history, depth, tool_round, label = engine.checkpoint_mgr.undo()
        assert not success
        assert "没有可回退" in msg


class TestMessageRecording:
    """Tests for _record_message during teaching mode."""

    def test_record_user_message(self, engine):
        engine.teaching_mode = True
        engine._record_message("user", content="test message")
        assert len(engine.recorded_messages) == 1
        assert engine.recorded_messages[0]["role"] == "user"
        assert engine.recorded_messages[0]["content"] == "test message"

    def test_record_tool_call(self, engine):
        engine.teaching_mode = True
        engine._record_message("tool_call", tool_name="web_search", args={"query": "test"})
        msg = engine.recorded_messages[0]
        assert msg["name"] == "web_search"
        assert msg["args"] == {"query": "test"}

    def test_no_recording_when_not_teaching(self, engine):
        engine.teaching_mode = False
        engine._record_message("user", content="test")
        assert len(engine.recorded_messages) == 0


class TestHandlers:
    """Tests for inline tool handlers."""

    def test_restore_checkpoint_list_empty(self, engine):
        result = engine._restore_checkpoint()
        assert "没有可回滚" in result


class TestStateTransitions:
    """Verify that the state machine transitions correctly."""

    def test_initial_state_is_idle(self, engine):
        assert engine.state == Engine.STATE_IDLE

    def test_after_reset_state_is_idle(self, engine):
        engine.state = Engine.STATE_ERROR
        engine.reset()
        assert engine.state == Engine.STATE_IDLE

    def test_run_sets_to_done(self, engine):
        caller = MockLLMCaller([text_response("ok")])
        eng = Engine(caller, execute_tool, test_mode=True)
        eng.run("hi")
        assert eng.state == Engine.STATE_DONE
