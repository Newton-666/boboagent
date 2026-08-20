"""TICKET-SKILL-ACTIVE-1 专项测试 — skill 主动使用指令。

覆盖（票验收）：
- S1 静态：injector.py 的 skill 注入块含"[主动使用]"指令，且在
  "## 项目标准"标题之后、标准内容之前
- S2 静态：指令措辞满足 owner 红线——约束执行（匹配 → 严格按标准执行）、
  不约束表达（不匹配 → 正常执行），显式"无需声明"防机械化
- S3 行为（桩跑 build_messages）：有 skill 标准 → 注入块含指令 + 标准全文
- S4 行为：无标准 → skill 块整体不注入（指令段也不出现，零残留）
- S5 防机械化措辞：指令不含"每轮/每回合都必须声明/汇报未匹配"等强制声明词
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
INJECTOR_PY = ROOT / "core" / "injector.py"

ACTIVE_MARK = "[主动使用]"


# ── 桩（复用 COST-2 测试的 MockEngine 模式）──────────────────────────

class MockTracker:
    _change_log: list = []
    _read_files: dict = {}


class MockProactive:
    def inject_context(self, messages):
        return messages


class _Loader:
    def __init__(self, standards):
        self._standards = standards

    def load_standards(self):
        return self._standards

    def list_available(self):
        return ""


class MockEngine:
    def __init__(self, standards=None, history=None):
        self.history = history or [
            {"role": "user", "content": "第一轮问题"},
            {"role": "assistant", "content": "第一轮回答"},
            {"role": "user", "content": "当前轮问题"},
        ]
        self.current_user_input = "当前轮问题"
        self._pending_diff = ""
        self._compressing = False
        self.tracker = MockTracker()
        self.proactive = MockProactive()
        self.skill_loader = _Loader(standards or [])


@pytest.fixture(autouse=True)
def silence_event_bus(monkeypatch):
    """prompt.budget 事件不写真实 events.jsonl（测试日志隔离）。"""
    import core.event_bus as eb

    class _Bus:
        def write(self, t, d):
            pass

    monkeypatch.setattr(eb, "event_bus", _Bus())


@pytest.fixture
def inj():
    from core.injector import PromptInjector
    return PromptInjector(MockEngine())


def _build(inj, standards=None, user_input="当前轮问题"):
    if standards is not None:
        inj._engine.skill_loader = _Loader(standards)
    return inj.build_messages(
        system_prompt="You are Bobo.",
        user_input=user_input,
        tools_schema=[],
        extra_categories=set(),
        session_id="s1",
    )


def _all_content(msgs):
    return "\n".join(
        m.get("content", "") for m in msgs if isinstance(m.get("content"), str)
    )


# ── S1：静态 — 注入块含主动使用指令，位置在标题之后 ─────────────────

def test_s1_static_active_instruction_present():
    src = INJECTOR_PY.read_text(encoding="utf-8")
    assert ACTIVE_MARK in src, "skill 注入块应含 [主动使用] 指令"
    assert "TICKET-SKILL-ACTIVE-1" in src, "注入块应带票标记"
    # 顺序：标题 → 指令 → 标准内容
    title = src.index("## 项目标准")
    mark = src.index(ACTIVE_MARK)
    combined = src.index("_skill_combined,")
    assert title < mark < combined, (
        f"指令位置错误：标题@{title} 指令@{mark} 标准拼接@{combined}"
    )


def _active_segment(src):
    """指令段源码：从 [主动使用] 到标准拼接处（_skill_combined,）的完整片段。"""
    start = src.index(ACTIVE_MARK)
    end = src.index("_skill_combined,")
    return src[start:end]


# ── S2：静态 — owner 红线（约束执行、不约束表达）────────────────────

def test_s2_static_red_line_wording():
    src = INJECTOR_PY.read_text(encoding="utf-8")
    segment = _active_segment(src)
    # 约束执行：匹配 → 严格按标准执行
    assert "匹配 → 严格按标准执行" in segment, "指令必须约束执行（命中标准必须执行）"
    # 不约束表达：不匹配 → 正常执行（无需声明）
    assert "不匹配 → 正常执行" in segment, "指令不得约束不命中时的表达"
    assert "无需声明" in segment, "必须显式豁免声明（防机械化）"


# ── S3：行为 — 有标准 → 注入指令 + 标准 ─────────────────────────────

def test_s3_behavior_with_standards_injects(inj):
    std = "git 提交前先 git diff --stat 自审，再 git status 对账"
    msgs = _build(inj, standards=[std])
    content = _all_content(msgs)
    assert ACTIVE_MARK in content, "有标准时注入块应含主动使用指令"
    assert "## 项目标准" in content
    assert std in content, "标准全文应注入"
    # 指令位于标题与标准之间（同消息内顺序）
    block = content[content.index("## 项目标准"):]
    assert block.index(ACTIVE_MARK) < block.index(std), "指令应在标准内容之前"


# ── S4：行为 — 无标准 → 不注入（零残留）─────────────────────────────

def test_s4_behavior_without_standards_no_inject(inj):
    msgs = _build(inj, standards=[])
    content = _all_content(msgs)
    assert ACTIVE_MARK not in content, "无标准时不得注入指令段"
    assert "## 项目标准" not in content, "无标准时 skill 块整体不注入"


# ── S5：防机械化措辞 ────────────────────────────────────────────────

def test_s5_no_forced_declaration_wording():
    src = INJECTOR_PY.read_text(encoding="utf-8")
    segment = _active_segment(src)
    # 禁止强制声明措辞：不得要求每轮汇报"未匹配"
    for bad in ("每轮", "每回合", "每次都要", "必须说明", "必须声明", "汇报未匹配"):
        assert bad not in segment, f"指令含机械化措辞: {bad!r}"
    # 指令应短（一句话级，防过度占 token；含源码引号/换行/缩进的上限）
    assert len(segment) < 200, f"指令过长（{len(segment)} 字符），应一句话级"
