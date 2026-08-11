"""TICKET-O4 · O4-3 测试：OFFICE MODE 上下文注入（office-context）。

票 O4（事故背景）：owner /office 后模型不知道自己处在 office 模式，把已合并的
阶段 0/G2 当成待办翻笔记考古。根因 = 模型上下文零 office 注入。

覆盖：
  1. office on（_office_state[sid].on=True）→ 注入存在且含四要素
     （模式名 / 身份 / 职责 / 边界）
  2. office off → 零注入（对照组铁律：连字段都不读）
  3. 普通模式（无记录）→ 零注入
  4. resume/activate 恢复路径（office_state 恢复后 get_office_on 返回 True）
  5. 注入段计入 prompt.budget 事件（sections.office.chars > 0）
  6. 读取失败静默降级（import 失败 → office_on=False → 零注入）
"""

import sys

import pytest

sys.path.insert(0, ".")

from core.injector import PromptInjector

# 四要素关键词（票 O4-2：模式名 / 身份 / 职责 / 边界）
_ELEMENTS = ["OFFICE MODE", "你是老板", "office_manager", "不是本模式职责"]


class MockTracker:
    _change_log: list = []
    _read_files: dict = {}


class MockProactive:
    def inject_context(self, messages):
        return messages


class MockSkillLoader:
    def load_standards(self):
        return []


class MockEngine:
    """Mock engine：只暴露 injector 需要的最小接口。"""

    def __init__(self, sid="test-o4-sid"):
        self.sid = sid
        self.history = [{"role": "user", "content": "hello"}]
        self.current_user_input = "hello"
        self._pending_diff = ""
        self._compressing = False
        self.tracker = MockTracker()
        self.proactive = MockProactive()
        self.skill_loader = MockSkillLoader()


@pytest.fixture(autouse=True)
def silence_event_bus(monkeypatch):
    """prompt.budget 事件不写真实 events.jsonl（测试日志隔离）。"""
    import core.event_bus as eb
    fired = []

    class _Bus:
        def write(self, t, d):
            fired.append((t, d))

    monkeypatch.setattr(eb, "event_bus", _Bus())
    return fired


@pytest.fixture
def office_state(monkeypatch):
    """注入可控的 _office_state 到 bobo_tui_gateway.server。"""
    import bobo_tui_gateway.server as srv
    st = {}
    monkeypatch.setattr(srv, "_office_state", st)
    return st


def _build(injector, session_id="s1"):
    return injector.build_messages(
        system_prompt="You are Bobo.",
        user_input="hello",
        tools_schema=[],
        extra_categories=set(),
        session_id=session_id,
    )


def _office_content(msgs):
    """从 messages 提取 OFFICE MODE 告示段内容（找不到返回 None）。"""
    for m in msgs:
        if m.get("role") == "system" and "【OFFICE MODE】" in m.get("content", ""):
            return m["content"]
    return None


class TestOfficeOn:
    def test_office_on_injects_notice_with_four_elements(self, office_state, silence_event_bus):
        """票 O4 验收 1：office on → 注入存在且含四要素。"""
        office_state["s1"] = {"on": True, "session": "stage-1"}
        inj = PromptInjector(MockEngine(sid="s1"))
        msgs = _build(inj, "s1")
        content = _office_content(msgs)
        assert content is not None, "office on 时必须注入 OFFICE 告示"
        for el in _ELEMENTS:
            assert el in content, f"告示缺四要素: {el}"

    def test_notice_within_300_chars(self, office_state, silence_event_bus):
        """票 O4-2：注入段 ≤300 字符。"""
        office_state["s1"] = {"on": True}
        inj = PromptInjector(MockEngine(sid="s1"))
        content = _office_content(_build(inj, "s1"))
        assert content is not None
        assert len(content) <= 300, f"告示 {len(content)} 字符 > 300"


class TestOfficeOffAndNormal:
    def test_office_off_zero_injection(self, office_state, silence_event_bus):
        """票 O4 验收 2：office off → 零注入（对照组铁律）。"""
        office_state["s1"] = {"on": False}
        inj = PromptInjector(MockEngine(sid="s1"))
        msgs = _build(inj, "s1")
        assert _office_content(msgs) is None, "office off 不得注入"

    def test_normal_mode_no_record_zero_injection(self, office_state, silence_event_bus):
        """票 O4 验收 3：普通模式（无记录）→ 零注入。"""
        # office_state 为空 dict —— 普通模式连字段都不读
        inj = PromptInjector(MockEngine(sid="s1"))
        msgs = _build(inj, "s1")
        assert _office_content(msgs) is None, "普通模式不得注入"

    def test_no_sid_zero_injection(self, office_state, silence_event_bus):
        """无 sid（engine.sid 为空）→ 零注入（不尝试 import 读取器）。"""
        office_state["s1"] = {"on": True}
        inj = PromptInjector(MockEngine(sid=""))
        msgs = _build(inj, "")
        assert _office_content(msgs) is None, "无 sid 不得注入"


class TestResumeActivate:
    def test_resume_path_restores_office_on(self, office_state, silence_event_bus):
        """票 O4 验收 resume：恢复路径 office_state 回填 → 注入恢复。"""
        # 模拟 resume：_office_state[sid] 已恢复 {on: True}
        office_state["s1"] = {"on": True, "session": "stage-1"}
        inj = PromptInjector(MockEngine(sid="s1"))
        assert _office_content(_build(inj, "s1")) is not None

    def test_activate_path_restores_office_on(self, office_state, silence_event_bus):
        """票 O4 验收 activate：切换会话回填 office_state → 注入恢复。"""
        office_state["s2"] = {"on": True}
        inj = PromptInjector(MockEngine(sid="s2"))
        assert _office_content(_build(inj, "s2")) is not None


class TestBudget:
    def test_office_section_in_budget(self, office_state, silence_event_bus):
        """票 O4 验收 4：注入段计入 prompt.budget 事件。"""
        office_state["s1"] = {"on": True}
        inj = PromptInjector(MockEngine(sid="s1"))
        _build(inj, "s1")
        budget_events = [d for t, d in silence_event_bus if t == "prompt.budget"]
        assert budget_events, "必须写 prompt.budget 事件"
        assert budget_events[-1]["sections"]["office"]["chars"] > 0

    def test_office_off_budget_zero(self, office_state, silence_event_bus):
        """office off → budget office 段 chars=0。"""
        office_state["s1"] = {"on": False}
        inj = PromptInjector(MockEngine(sid="s1"))
        _build(inj, "s1")
        budget_events = [d for t, d in silence_event_bus if t == "prompt.budget"]
        assert budget_events
        assert budget_events[-1]["sections"]["office"]["chars"] == 0


class TestDegrade:
    def test_import_failure_silent_degrade(self, office_state, monkeypatch, silence_event_bus):
        """读取器 import 失败 → 静默降级 office_on=False → 零注入。"""
        import builtins
        real_import = builtins.__import__

        def _broken(name, *a, **kw):
            if name == "bobo_tui_gateway.server":
                raise ImportError("boom")
            return real_import(name, *a, **kw)

        monkeypatch.setattr(builtins, "__import__", _broken)
        office_state["s1"] = {"on": True}
        inj = PromptInjector(MockEngine(sid="s1"))
        msgs = _build(inj, "s1")
        assert _office_content(msgs) is None, "import 失败必须零注入，不影响工具链"
