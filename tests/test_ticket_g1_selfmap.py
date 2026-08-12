"""TICKET-G1（v2 母子结构）验收测试 — SELF.md 同源注入 + 章节触发 + 同步锁。

覆盖票 G1-1/G1-2/G1-3/G1-4 全部验收：
- G1-1 同源注入：L0 常驻注入 = docs/SELF.md 顶部 [SELF] 代码块原文（逐字节，不许改写）
- G1-2 章节触发展开：§2 架构/§4 边界/§5 自救，关键词命中才注入 + 无触发零注入对照
- G1-3 GUIDANCE.md 顶部指针（宪章 + SELF L0 已常驻）
- G1-4 同步锁：注入 L0 与母文档逐字节一致（漂移即红）；L0 声明可追溯到章节
"""

import re

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
    def __init__(self, history=None, user_input="测试"):
        self.history = history if history is not None else [
            {"role": "user", "content": "hello world"}]
        self.current_user_input = user_input
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
            {"load_standards": lambda self, _r=None: []},
        )()


def _build(engine, tools_schema=None):
    return PromptInjector(engine).build_messages(
        system_prompt="You are Bobo.",
        user_input=engine.current_user_input,
        tools_schema=tools_schema if tools_schema is not None else [],
        extra_categories=set(),
        session_id="s1",
    )


def _mother_l0() -> str:
    """直接从 SELF.md 提取顶部 [SELF] 代码块原文（测试侧的母文档参照）。"""
    text = open(injector_mod._SELF_PATH, encoding="utf-8").read()
    m = re.search(r"```\n(\[SELF\].*?)\n```", text, re.S)
    assert m, "SELF.md 顶部 [SELF] 代码块缺失"
    return m.group(1)


def _selfmap_text(msgs):
    """提取 L0 常驻注入段文本（含 [SELF] 前缀）；不存在返回 ''。"""
    for m in msgs:
        c = m.get("content", "")
        if c.startswith("[SELF]"):
            return c
    return ""


def _chapter_texts(msgs):
    """提取所有 [SELF <章标题>] 触发展开段。"""
    return [m.get("content", "") for m in msgs if "[SELF " in m.get("content", "")]


# ── G1-4 同步锁（关键）──

class TestSyncLock:
    def test_l0_byte_identical_to_mother(self):
        """同步锁：注入 L0 与 SELF.md 顶部块逐字节一致（改一边不改另一边 → 红）"""
        injected = _selfmap_text(_build(MockEngine()))
        assert injected, "L0 常驻注入缺失"
        assert injected == _mother_l0(), (
            "L0 注入与母文档漂移：injector 必须逐字节使用 SELF.md 顶部 [SELF] 块"
        )

    def test_extractor_matches_mother(self):
        """提取器本身与母文档逐字节一致（机制层同步锁）"""
        assert injector_mod._extract_selfmap_l0() == _mother_l0()

    def test_l0_claims_trace_to_chapters(self):
        """L0 每个声明可追溯到 SELF.md 章节（claim → 章节 + 章内支撑关键词）"""
        claims = [
            # (L0 声明, 目标章节, 章内支撑关键词)
            ("engine (decisions + gates", "2. Architecture map", "engine"),
            ("gateway (sessions/rpc", "2. Architecture map", "gateway"),
            ("TUI (ui-tui)", "2. Architecture map", "TUI"),
            ("describe_tool if unsure", "3. Capabilities", "describe_tool"),
            ("decision chain", "4. Boundaries and enforcement", "decision chain"),
            ("protected_paths read-only", "4. Boundaries and enforcement", "protected_paths"),
            ("without a ticket", "4. Boundaries and enforcement", "ticket"),
            ("Mode is told by injected notices", "4. Boundaries and enforcement", "BOBO_ROLE"),
            ("report honestly", "6. Honest limits", "Honest"),
        ]
        for claim, chapter_marker, keyword in claims:
            assert claim in _mother_l0(), f"L0 缺少声明: {claim}"
            chap = injector_mod._extract_self_chapter(chapter_marker)
            assert chap and keyword in chap, (
                f"L0 声明 '{claim}' 的支撑关键词 '{keyword}' 不在 {chapter_marker} 章"
            )


# ── G1-1 常驻注入（同源）──

class TestResidentInjection:
    def test_selfmap_injected_any_mode(self):
        """常驻：无模式条件，普通模式也注入 L0"""
        msgs = _build(MockEngine())
        assert _selfmap_text(msgs).startswith("[SELF]")

    @pytest.mark.skipif(
        len(_mother_l0()) > 300,
        reason="L0 段当前超 300 硬线，待 Kimi 修订 docs/SELF.md 至 ≤300 后自动解锁（硬线不松）"
    )
    def test_budget_event_counts_selfmap(self, silence_event_bus):
        """预算双断言：≤300 硬线 + 与母文档逐字节一致（同步锁）

        硬线不松（Kimi 终审裁决 2026-08-12）：SELF.md 是母文档，但 L0 段超线属
        定稿时未量好，由 Kimi 负责修订母文档（不由施工方动手）。本测试在超线期间
        skip（标注待解锁），Kimi 修订至 ≤300 后自动恢复硬线校验。
        """
        _build(MockEngine())
        budget_events = [d for t, d in silence_event_bus if t == "prompt.budget"]
        assert budget_events, "应写 prompt.budget 事件"
        chars = budget_events[0]["sections"]["selfmap"]["chars"]
        # 双断言一：与母文档逐字节一致（母子同源，漂移即红）
        assert chars == len(_mother_l0())
        # 双断言二：≤300 硬线（Kimi 修订母文档后生效）
        assert chars <= 300, f"L0 段 {chars} 字符超出 300 硬线"

    def test_missing_self_file_silent(self, monkeypatch):
        """SELF.md 缺失：静默不注入也不炸（保守降级）"""
        monkeypatch.setattr(injector_mod, "_SELF_PATH", "/nonexistent/SELF.md")
        msgs = _build(MockEngine())
        assert _selfmap_text(msgs) == ""


# ── G1-2 章节触发展开 ──

class TestChapterTriggers:
    def test_arch_chapter_triggered_by_engine(self):
        """§2 架构：user_input 含 'engine 闸' → 架构章全文注入"""
        msgs = _build(MockEngine(user_input="engine 的闸在哪、decision chain 怎么走"))
        chapters = " ".join(_chapter_texts(msgs))
        assert "Architecture map" in chapters
        assert "engine.py" in chapters

    def test_boundary_chapter_triggered_by_ticket(self):
        """§4 边界：user_input 含 'ticket authorized_paths' → 边界章注入"""
        msgs = _build(MockEngine(user_input="ticket authorized_paths 怎么豁免 protected"))
        chapters = " ".join(_chapter_texts(msgs))
        assert "Boundaries and enforcement" in chapters
        assert "authorized_paths" in chapters

    def test_rescue_chapter_triggered_by_crash(self):
        """§5 自救：user_input 含 '崩溃排查 log' → 自救章注入"""
        msgs = _build(MockEngine(user_input="崩溃了怎么排查，看 log 吗"))
        chapters = " ".join(_chapter_texts(msgs))
        assert "Failure self-rescue" in chapters
        assert "bobo.log" in chapters

    def test_trigger_from_history(self):
        """触发源含最近 history：上轮谈 engine 闸，本轮展开架构章"""
        hist = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "engine 的闸在 decision chain"},
        ]
        msgs = _build(MockEngine(history=hist, user_input="继续"))
        chapters = " ".join(_chapter_texts(msgs))
        assert "Architecture map" in chapters

    def test_no_trigger_no_chapter(self):
        """对照组：无关键词 → 零章节注入（L0 仍在，章节绝不展开）"""
        msgs = _build(MockEngine(user_input="今天天气不错"))
        assert _chapter_texts(msgs) == [], "无触发不应展开任何章节"
        assert _selfmap_text(msgs).startswith("[SELF]"), "L0 常驻不受影响"

    def test_budget_counts_chapters(self, silence_event_bus):
        """触发时 budget 记账：selfmap_chapters.chapters 含命中章"""
        _build(MockEngine(user_input="engine 闸 + ticket 豁免 + 崩溃排查 log"))
        budget_events = [d for t, d in silence_event_bus if t == "prompt.budget"]
        sec = budget_events[0]["sections"]["selfmap_chapters"]
        assert set(sec["chapters"]) >= {"arch", "boundary", "rescue"}
        assert sec["chars"] > 0


# ── G1-3 GUIDANCE.md 指针 ──

class TestGuidancePointer:
    def test_guidance_top_has_constitution_and_self_note(self):
        """GUIDANCE.md 顶部两行：宪章指针 + SELF L0 已常驻说明"""
        guidance = injector_mod._load_guidance()
        assert guidance is not None
        head = guidance.splitlines()[:3]
        assert any("HARCHITECTURE" in line for line in head), "宪章指针缺失"
        assert any("SELF L0 is always resident" in line for line in head), (
            "SELF L0 已常驻说明缺失"
        )

    def test_guidance_still_injected(self):
        """回归：GUIDANCE 段仍注入（E3b 语义不变）"""
        msgs = _build(MockEngine())
        contents = " ".join(m.get("content", "") for m in msgs)
        assert "[CAPABILITY MAP]" in contents
