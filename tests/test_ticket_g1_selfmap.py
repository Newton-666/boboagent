"""TICKET-G1 验收测试 — L0 自我地图常驻注入（F 卷雏形）。

覆盖票 G1-1/G1-2/G1-3 全部验收：
1. L0 段存在：build_messages 产物含 "L0 SELF-MAP"
2. 五要素齐全：身份/架构/闸位置/边界/模式 关键词都在
3. 硬预算：段文本 ≤300 字符（超出即失败）
4. 计入 budget：prompt.budget 事件 sections.selfmap.chars 正确
5. 闭卷模拟：tools_schema=[]（无 describe_tool/读文件工具）上下文里，
   注入段文本直接包含闸位置/边界/模式的答案要点（模型凭 L0 段可答，不翻文件）
6. 常驻性：office on / auto on / 普通模式一律注入（无模式条件）
7. GUIDANCE.md 顶部两行指针（宪章 + L0 分层说明）
"""

import pytest

import core.injector as injector_mod
from core.injector import PromptInjector


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


class MockEngine:
    def __init__(self, load_standards_result=None):
        self.history = [{"role": "user", "content": "hello world"}]
        self.current_user_input = "测试"
        self._pending_diff = ""
        self._compressing = False
        self._just_compressed = False
        self.tracker = type("T", (), {"_change_log": [], "_read_files": {}})()
        self.proactive = type(
            "P", (), {"inject_context": lambda self, msgs: msgs}
        )()
        self.skill_loader = type(
            "S",
            (),
            {"load_standards": lambda self, _r=load_standards_result: _r or []},
        )()


def _build(engine, tools_schema=None):
    return PromptInjector(engine).build_messages(
        system_prompt="You are Bobo.",
        user_input="测试",
        tools_schema=tools_schema if tools_schema is not None else [],
        extra_categories=set(),
        session_id="s1",
    )


def _selfmap_text(msgs):
    """从 build_messages 产物中提取 L0 段文本；不存在返回 ''。"""
    for m in msgs:
        c = m.get("content", "")
        if "L0 SELF-MAP" in c:
            return c
    return ""


# ── G1-1：L0 段存在 + 五要素 + 硬预算 ──

class TestSelfmapSegment:
    def test_selfmap_injected(self):
        """L0 段存在：build_messages 产物含 'L0 SELF-MAP'"""
        msgs = _build(MockEngine())
        assert "L0 SELF-MAP" in _selfmap_text(msgs)

    def test_five_elements_present(self):
        """五要素齐全：身份/架构/闸位置/边界/模式"""
        text = _selfmap_text(_build(MockEngine()))
        # 1 身份
        assert "bobo harness" in text
        # 2 架构一句话
        assert "engine" in text and "gateway" in text and "TUI" in text
        assert "->" in text
        # 3 闸位置：engine decision chain + tickets authorize paths
        assert "engine decision chain" in text
        assert "tickets authorize paths" in text
        # 4 绝对边界：protected_paths read-only
        assert "protected_paths read-only" in text
        # 5 模式指针：banner announces auto/office; none = normal
        assert "auto/office" in text
        assert "none = normal" in text

    def test_hard_budget_300_chars(self):
        """硬预算：L0 段 ≤300 字符（预算即宪法原则一对上下文的态度）"""
        text = _selfmap_text(_build(MockEngine()))
        assert len(text) <= 300, f"L0 段 {len(text)} 字符超出 300 硬预算"

    def test_always_injected_any_mode(self):
        """常驻性：无模式条件——普通/office/auto 一律注入（本注入段无分支）"""
        msgs = _build(MockEngine())
        assert "L0 SELF-MAP" in _selfmap_text(msgs)

    def test_budget_event_counts_selfmap(self, silence_event_bus):
        """计入 budget：prompt.budget 事件 sections.selfmap.chars == 段文本长度"""
        _build(MockEngine())
        budget_events = [d for t, d in silence_event_bus if t == "prompt.budget"]
        assert budget_events, "应写 prompt.budget 事件"
        sections = budget_events[0]["sections"]
        assert "selfmap" in sections
        assert sections["selfmap"]["chars"] == len(
            _selfmap_text(_build(MockEngine()))
        )


# ── G1-3：闭卷模拟（F 卷雏形） ──

class TestClosedBookSimulation:
    def test_closed_book_answers_gate_location(self):
        """闭卷：无工具上下文，模型凭 L0 段可直接答闸位置（断言注入文本含要点）"""
        msgs = _build(MockEngine(), tools_schema=[])  # 不挂任何工具
        text = _selfmap_text(msgs)
        assert "engine decision chain" in text
        assert "tickets authorize paths" in text

    def test_closed_book_answers_boundary(self):
        """闭卷：绝对边界答案在 L0 段内（protected_paths read-only）"""
        msgs = _build(MockEngine(), tools_schema=[])
        assert "protected_paths read-only" in _selfmap_text(msgs)

    def test_closed_book_answers_mode(self):
        """闭卷：模式指针答案在 L0 段内（banner auto/office; none = normal）"""
        msgs = _build(MockEngine(), tools_schema=[])
        text = _selfmap_text(msgs)
        assert "auto/office" in text and "none = normal" in text


# ── G1-2：GUIDANCE.md 顶部指针 ──

class TestGuidancePointer:
    def test_guidance_top_has_constitution_and_l0_note(self):
        """GUIDANCE.md 顶部两行：宪章指针 + L0 已常驻分层说明"""
        guidance = injector_mod._load_guidance()
        assert guidance is not None
        head = guidance.splitlines()[:3]
        assert any("HARCHITECTURE" in line for line in head), "宪章指针缺失"
        assert any("L0 self-map is always injected" in line for line in head), (
            "L0 已常驻分层说明缺失"
        )

    def test_guidance_still_injected(self):
        """回归：GUIDANCE 段仍注入（E3b 语义不变）"""
        msgs = _build(MockEngine())
        contents = " ".join(m.get("content", "") for m in msgs)
        assert "[CAPABILITY MAP]" in contents
