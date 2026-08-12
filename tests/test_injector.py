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


class TestNowAnchor:
    """票 TICKET-P1：日期时间锚点（[NOW] 常驻行）测试。

    验收点：锚点存在、格式正确、随时间变化、计入 prompt.budget。
    """

    def _build(self, injector, session_id="s1"):
        return injector.build_messages(
            system_prompt="You are Bobo.",
            user_input="hello",
            tools_schema=[],
            extra_categories=set(),
            session_id=session_id,
        )

    def _find_anchor(self, msgs):
        for m in msgs:
            c = m.get("content", "")
            if isinstance(c, str) and c.startswith("[NOW] "):
                return c
        return None

    def test_anchor_injected(self, injector):
        """锚点存在：build_messages 输出含 [NOW] 段。"""
        msgs = self._build(injector)
        anchor = self._find_anchor(msgs)
        assert anchor is not None, "messages 中未找到 [NOW] 锚点"

    def test_anchor_format(self, injector):
        """格式正确：首行 `[NOW] YYYY-MM-DD HH:MM Weekday (Asia/Shanghai)` ≤60 字符。"""
        msgs = self._build(injector)
        anchor = self._find_anchor(msgs)
        assert anchor is not None
        first_line = anchor.splitlines()[0]
        assert len(first_line) <= 60, f"锚点行超长: {len(first_line)}"
        import re
        pat = (
            r"^\[NOW\] \d{4}-\d{2}-\d{2} \d{2}:\d{2} "
            r"(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday) "
            r"\(Asia/Shanghai\)$"
        )
        assert re.match(pat, first_line), f"格式不符: {first_line}"
        # 引导行：日期/星期/时间问题直接引用锚点，禁调工具（E1 硬指标）
        assert "引用上方 [NOW] 锚点" in anchor
        assert "禁止为此调用工具" in anchor

    def test_anchor_tracks_time(self, monkeypatch, injector):
        """随时间变化：固定不同时间点，锚点输出跟随变化。"""
        from datetime import datetime

        class _FakeNow:
            def __init__(self):
                self.current = datetime(2026, 8, 12, 18, 23)

            def now(self, tz=None):
                return self.current.replace(tzinfo=tz)

        fake = _FakeNow()
        monkeypatch.setattr("core.injector._datetime", fake)
        from core.injector import _build_now_anchor

        a1 = _build_now_anchor()
        fake.current = datetime(2026, 8, 13, 9, 5)
        a2 = _build_now_anchor()
        assert a1 != a2, "锚点未随时间变化"
        assert "2026-08-12" in a1 and "2026-08-13" in a2

    def test_anchor_in_budget(self, silence_event_bus, injector):
        """计入 budget：prompt.budget 事件 sections 含 now 键，chars 与锚点一致。"""
        msgs = self._build(injector)
        anchor = self._find_anchor(msgs)
        assert anchor is not None
        budget = [d for t, d in silence_event_bus if t == "prompt.budget"]
        assert budget, "未发出 prompt.budget 事件"
        sections = budget[0]["sections"]
        assert "now" in sections, "budget sections 缺少 now"
        assert sections["now"]["chars"] == len(anchor)

    def test_anchor_in_all_modes(self, injector):
        """全模式一致：普通/auto/office 无差别注入锚点（office 仅多一段告示）。"""
        for mode in ("normal", "auto", "office"):
            msgs = self._build(injector, session_id=f"{mode}-s1")
            assert self._find_anchor(msgs) is not None, f"模式 {mode} 缺锚点"
