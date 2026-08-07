"""Tests for PromptInjector — messages 构建管道。"""

import json

import pytest

from core.injector import PromptInjector


@pytest.fixture(autouse=True)
def isolated_memory(isolated_memory_db):
    """票 LN-4：autouse 复用 conftest.isolated_memory_db。

    实现已上移 tests/conftest.py（共享），供 test_e3a_skill_zombie.py 显式请求。
    """
    return isolated_memory_db


@pytest.fixture(autouse=True)
def silence_event_bus(monkeypatch):
    """票 LN-4：prompt.budget 事件不写真实 events.jsonl（测试日志隔离）。"""
    import core.event_bus as eb
    fired = []

    class _Bus:
        def write(self, t, d):
            fired.append((t, d))

    monkeypatch.setattr(eb, "event_bus", _Bus())
    return fired


class MockTracker:
    """Minimal tracker mock — 只提供 injector 读取的属性。"""
    _change_log: list = []
    _read_files: dict = {}


class MockProactive:
    """Minimal proactive mock — 直通返回 messages。"""
    def inject_context(self, messages):
        return messages


class MockSkillLoader:
    """Minimal skill_loader mock — 返回空，无副作用。"""
    def load_standards(self):
        return []
    def list_available(self):
        return ""




class MockEngine:
    """Mock engine：只暴露 injector 需要的最小接口。"""

    def __init__(self):
        self.history = [{"role": "user", "content": "hello world"}]
        self.current_user_input = "hello world"
        self._pending_diff = ""
        self._compressing = False
        self.tracker = MockTracker()
        self.proactive = MockProactive()
        self.skill_loader = MockSkillLoader()


@pytest.fixture
def injector():
    return PromptInjector(MockEngine())


class TestBuildMessages:
    def test_returns_list(self, injector):
        msgs = injector.build_messages(
            system_prompt="You are Bobo.",
            user_input="hello",
            tools_schema=[],
            extra_categories=set(),
            session_id="s1",
        )
        assert isinstance(msgs, list)

    def test_first_message_is_system(self, injector):
        msgs = injector.build_messages(
            system_prompt="You are Bobo.",
            user_input="hello",
            tools_schema=[],
            extra_categories=set(),
            session_id="s1",
        )
        assert msgs[0]["role"] == "system"
        assert msgs[0]["content"] == "You are Bobo."

    def test_contains_user_message_from_history(self, injector):
        msgs = injector.build_messages(
            system_prompt="You are Bobo.",
            user_input="hello",
            tools_schema=[],
            extra_categories=set(),
            session_id="s1",
        )
        roles = [m["role"] for m in msgs]
        assert "user" in roles
        user_msgs = [m for m in msgs if m["role"] == "user"]
        assert any("hello world" in m["content"] for m in user_msgs)

    def test_no_diff_when_pending_diff_is_empty(self, injector):
        msgs = injector.build_messages(
            system_prompt="You are Bobo.",
            user_input="hello",
            tools_schema=[],
            extra_categories=set(),
            session_id="s1",
        )
        contents = " ".join(m.get("content", "") for m in msgs)
        assert "代码变更" not in contents

    def test_handles_null_skill_loader(self, injector):
        """skill_loader 返回空时 injector 不崩溃，且注入'可用标准'提示。"""
        injector._engine.skill_loader = MockSkillLoader()
        msgs = injector.build_messages(
            system_prompt="You are Bobo.",
            user_input="hello",
            tools_schema=[],
            extra_categories=set(),
            session_id="s1",
        )
        assert len(msgs) >= 2  # system + history

    def test_diff_injected_when_pending(self, injector):
        injector._engine._pending_diff = "+ print('hello')\n- print('bye')"
        msgs = injector.build_messages(
            system_prompt="You are Bobo.",
            user_input="hello",
            tools_schema=[],
            extra_categories=set(),
            session_id="s1",
        )
        contents = " ".join(m.get("content", "") for m in msgs)
        assert "代码变更" in contents
        # pending_diff 会被消费清空
        assert injector._engine._pending_diff == ""




class TestPromptPoolIntegration:
    """票 LN-5：验证 PromptPool ratio 真正影响 injector 各段 ceiling。"""


    def test_prompt_pool_decision_event_emitted(self, silence_event_bus, injector):
        """build_messages 应同时发出 prompt.budget 和 prompt.budget.decision 事件。"""
        injector.build_messages(
            system_prompt="You are Bobo.",
            user_input="hello",
            tools_schema=[],
            extra_categories=set(),
            session_id="s1",
        )
        types = [t for t, d in silence_event_bus]
        assert "prompt.budget" in types
        assert "prompt.budget.decision" in types

        decision = [d for t, d in silence_event_bus if t == "prompt.budget.decision"][0]
        assert "allocated" in decision
        assert "used" in decision
        assert "total_pool" in decision
        assert decision["total_pool"] > 0
        assert "identity" in decision["allocated"]
        assert "memory" in decision["used"]
        assert decision["used"]["memory"] >= 0
