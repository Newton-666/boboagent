"""GOV-1 验收测试 — EV-2 新人开箱：纪律内化 + 收工自审 + 零上下文注入。

覆盖（票文 GOV-1）：
1. 施工类回合注入施工纪律：六步工作流（建账/读码/施工/专项/全量/汇报）全在
2. 收工类回合注入收工自审纪律：git diff 逐 hunk 自审 + F12 实证 + L8/L11/L12 要点
3. 普通聊天零注入（对照组铁律：不命中关键词绝不注入）
4. 零上下文新 clone 模拟（清记忆/清台账/无改动记录）下纪律照常注入——不依赖记忆与台账
5. 预算上限：两场景纪律段 ≤ 1600 字符（≈800 tokens）；L 块摘要保留全部场景 L 块
6. 事件流证据：prompt.budget 事件含 discipline 段（scene/truncated/chars）；真实 EventBus 落盘可查
7. GUI-LESSONS.md 缺失：固定纪律段照常注入（静默降级），仅缺 L 块
"""

import json

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
    """零上下文新 clone 模拟：无记忆注入、无台账、无改动记录、无已读文件。

    history 仅一条初始 user 消息（等价刚 clone 后首轮）；tracker 全空。
    纪律注入若依赖记忆/台账/改动记录，本桩将无法注入——测试即证伪。
    """

    def __init__(self, history=None):
        self.history = history or [{"role": "user", "content": "你好"}]
        self.current_user_input = ""
        self._pending_diff = ""
        self._compressing = False
        self._just_compressed = False
        self.tracker = type("T", (), {"_change_log": [], "_read_files": {}})()
        self.proactive = type(
            "P", (), {"inject_context": lambda self, msgs: msgs}
        )()
        self.skill_loader = type(
            "S", (), {"load_standards": lambda self: []}
        )()


def _build(engine, user_input):
    return PromptInjector(engine).build_messages(
        system_prompt="You are Bobo.",
        user_input=user_input,
        tools_schema=[],
        extra_categories=set(),
        session_id="s1",
    )


def _discipline_msg(msgs):
    """返回纪律段消息内容（取最后一处=当前轮，历史轮次可能残留旧纪律）；未注入返回 None。"""
    found = None
    for m in msgs:
        c = m.get("content", "")
        if "【施工工作流纪律】" in c or "【收工自审纪律】" in c:
            found = c
    return found


# ── 1. 施工类回合注入施工纪律 ──

def test_work_scene_injects_six_step_workflow():
    """施工类输入注入纪律段，六步工作流关键词全在。"""
    msgs = _build(MockEngine(), "请施工：修 bug，改 core/engine.py 的字段闸")
    disc = _discipline_msg(msgs)
    assert disc is not None, "施工类回合必须注入纪律段"
    for kw in ("先建台账", "读码定位", "施工", "专项测试", "全量回归", "五查汇报"):
        assert kw in disc, f"工作流缺关键步: {kw}"


def test_work_scene_keeps_all_l1_l10():
    """work 场景 L 块摘要保留 L1-L10 全十条标题。"""
    msgs = _build(MockEngine(), "施工：帮我实现新功能并测试")
    disc = _discipline_msg(msgs)
    assert disc is not None
    for i in range(1, 11):
        assert f"### L{i}." in disc, f"work 场景缺 L{i}"


# ── 2. 收工类回合注入收工自审纪律 ──

def test_wrapup_scene_injects_git_diff_self_review():
    """收工类输入注入收工自审纪律：git diff 逐 hunk 自审 + F12 实证。"""
    msgs = _build(MockEngine(), "收工汇报")
    disc = _discipline_msg(msgs)
    assert disc is not None, "收工类回合必须注入收工纪律段"
    assert "git diff" in disc and "逐 hunk" in disc, "缺 git diff 逐 hunk 自审动作"
    assert "F12 自审自抓 4 个 bug" in disc, "缺 F12 实证"
    assert "先修再汇报" in disc, "缺'先修再汇报'"
    for kw in ("数字必须可复现", "正文给人看", "证据落盘"):
        assert kw in disc, f"缺汇报纪律: {kw}"


def test_wrapup_scene_keeps_l8_l11_l12():
    """wrapup 场景保留 L8/L11/L12 块。"""
    msgs = _build(MockEngine(), "总结并终审")
    disc = _discipline_msg(msgs)
    assert disc is not None
    for lnum in ("L8", "L11", "L12"):
        assert f"### {lnum}." in disc, f"wrapup 场景缺 {lnum}"


# ── 3. 对照组铁律：普通聊天零注入 ──

def test_plain_chat_zero_injection():
    """无施工/收工关键词的普通聊天：零纪律注入。"""
    msgs = _build(MockEngine(), "今天天气不错，下午一起喝咖啡？")
    assert _discipline_msg(msgs) is None, "普通聊天不得注入纪律"


# ── 4. 零上下文新 clone：纪律照常注入 ──

def test_zero_context_clone_still_injects():
    """零上下文（空历史/空台账/空改动记录）下两场景照常注入，不依赖任何会话状态。"""
    eng = MockEngine()  # history 仅初始消息、tracker 全空 = 新 clone
    for ui, marker in (("施工：修 bug", "【施工工作流纪律】"),
                       ("收工汇报", "【收工自审纪律】")):
        # 模拟真实引擎流程：每轮先 append 当前 user 消息再 build
        eng.history.append({"role": "user", "content": ui})
        msgs = _build(eng, ui)
        disc = _discipline_msg(msgs)
        assert disc is not None and marker in disc, f"零上下文下 {ui!r} 应注入 {marker}"


# ── 5. 预算上限 ──

def test_discipline_budget_cap():
    """两场景纪律段均 ≤1600 字符（≈800 tokens），超限压缩生效。"""
    cap = injector_mod._DISCIPLINE_BUDGET_CHARS
    for ui in ("施工：修 bug", "收工汇报"):
        msgs = _build(MockEngine(), ui)
        disc = _discipline_msg(msgs)
        assert disc is not None
        assert len(disc) <= cap, f"{ui!r} 纪律段超预算: {len(disc)} > {cap}"


# ── 6. 事件流证据：prompt.budget 记账 + 真实落盘 ──

def test_prompt_budget_records_discipline(silence_event_bus):
    """prompt.budget 事件顶层含 discipline 字段（scene/chars/truncated）。

    注：discipline 记账在事件顶层而非 sections——LN-4 验收口径 sections 精确九段，
    且 sections 多 key 会把 payload 推过 _SINGLE_EVENT_MAX_CHARS 导致整条事件被丢弃。
    """
    _build(MockEngine(), "施工：修 bug")
    events = [d for t, d in silence_event_bus if t == "prompt.budget"]
    assert events, "应发出 prompt.budget 事件"
    disc = events[0]["discipline"]
    assert disc["scene"] == "work"
    assert disc["chars"] > 0
    assert "truncated" in disc
    # LN-4 口径：sections 不含 discipline
    assert "discipline" not in events[0]["sections"]


def test_real_event_bus_audit_trail(tmp_path, monkeypatch):
    """真实 EventBus 落盘可查：events.jsonl 含 prompt.budget.discipline 事件（事件流证据）。"""
    import core.event_bus as eb

    bus = eb.EventBus(log_dir=str(tmp_path))
    monkeypatch.setattr(eb, "event_bus", bus)

    _build(MockEngine(), "收工汇报")

    path = tmp_path / "events.jsonl"
    assert path.is_file(), "事件流应落盘"
    lines = path.read_text(encoding="utf-8").splitlines()
    hits = [
        json.loads(ln) for ln in lines
        if json.loads(ln).get("type") == "prompt.budget"
    ]
    assert hits, "events.jsonl 应含 prompt.budget 事件"
    disc = hits[0]["discipline"]
    assert disc["scene"] == "wrapup"
    assert disc["chars"] > 0
    assert "discipline" not in hits[0]["sections"]


# ── 7. GUI-LESSONS.md 缺失：静默降级 ──

def test_lessons_missing_silent_degrades(monkeypatch):
    """docs/GUI-LESSONS.md 缺失：固定纪律段照常注入，无 L 块，不炸。"""
    monkeypatch.setattr(
        injector_mod, "_GUI_LESSONS_PATH",
        "/nonexistent/docs/GUI-LESSONS.md",
    )
    msgs = _build(MockEngine(), "施工：修 bug")
    disc = _discipline_msg(msgs)
    assert disc is not None, "lessons 缺失时固定纪律段仍须注入"
    assert "### L1." not in disc, "lessons 缺失时不应有 L 块"
    assert "先建台账" in disc
