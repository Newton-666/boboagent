"""DIAG-1 验收测试 — 调试纪律场景注入（说不清的 bug 五步排查）。

覆盖（票文 DIAG-1）：
1. 调试类信号（报错/不对/打不开/坏了/崩了/白屏/无响应/卡住/不工作/为什么不/怎么办/
   定位/排查/复现/取证/error/crash 等）命中 → 注入调试纪律段（scene=debug）
2. 闲聊零注入（对照组铁律：无触发词零注入）
3. 调试纪律段五要素齐全：先复现/先取证/假设必须验证/定位陈述/改后验证
4. 预算记账：prompt.budget 事件 discipline 段 scene=="debug"，chars>0，truncated 在场
5. 与 GOV-1 施工场景不互斥不串扰：work/wrapup 触发照旧；施工消息不含调试词时不注入
   调试段；优先级 wrapup > debug > work
6. 预算上限：调试纪律段 ≤ 1600 字符（并入 discipline 段共用预算）
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
    """零上下文新 clone 模拟：无记忆注入、无台账、无改动记录、无已读文件。"""

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


def _debug_msg(msgs):
    """返回含调试纪律段的消息内容；未注入返回 None。"""
    found = None
    for m in msgs:
        c = m.get("content", "")
        if "【调试纪律】" in c:
            found = c
    return found


# ── 1. 调试类信号命中 → 注入调试纪律段 ──

@pytest.mark.parametrize("ui", [
    "这里报错了，帮我看看",
    "这个功能怎么不对",
    "桌面端打不开了",
    "坏了，白屏了",
    "崩了，无响应",
    "卡住了不工作",
    "为什么不显示结果",
    "怎么办，一直转圈",
    "帮我定位一下这个问题",
    "排查一下为什么失败",
    "error: xxx not found",
    "它 crash 了，traceback 在哪",
])
def test_debug_signals_inject(ui):
    """各类调试信号命中 → 注入调试纪律段（scene=debug）。"""
    msgs = _build(MockEngine(), ui)
    disc = _debug_msg(msgs)
    assert disc is not None, f"{ui!r} 应注入调试纪律段"


# ── 2. 对照组铁律：普通聊天零注入 ──

@pytest.mark.parametrize("ui", [
    "今天天气不错，下午一起喝咖啡？",
    "帮我安排明天的会议",
    "写一首关于秋天的诗",
    "介绍一下你自己",
])
def test_plain_chat_zero_injection(ui):
    """无调试/施工/收工关键词的普通聊天：零纪律注入。"""
    msgs = _build(MockEngine(), ui)
    assert _debug_msg(msgs) is None, f"{ui!r} 不得注入调试纪律"
    # 对照组铁律：任何纪律段都不注入
    for m in msgs:
        c = m.get("content", "")
        assert "【" not in c or "【调试纪律】" not in c, f"{ui!r} 注入纪律段: {c[:40]}"


# ── 3. 调试纪律段五要素齐全 ──

def test_debug_discipline_five_elements():
    """调试纪律段五要素全在：先复现/先取证/假设必须验证/定位陈述/改后验证。"""
    msgs = _build(MockEngine(), "报错了，帮我排查")
    disc = _debug_msg(msgs)
    assert disc is not None
    for kw in (
        "先复现", "没亲眼看到症状不许动手", "Playwright CDP",
        "bobo.log", "events.jsonl", "stack_dump.log",
        "先取证", "硬证据", "写进台账",
        "假设必须验证", "grep 确认它真实存在",
        "定位陈述", "根因是 X 文件 Y 行，因为证据 Z",
        "改后验证", "症状在真实环境消失才算完",
    ):
        assert kw in disc, f"调试纪律缺要素: {kw}"


def test_debug_scene_keeps_l2_l14():
    """debug 场景保留 L2（真实可跑）与 L14（禁止虚构全局）块。"""
    msgs = _build(MockEngine(), "白屏了，帮我定位")
    disc = _debug_msg(msgs)
    assert disc is not None
    assert "### L2." in disc, "debug 场景缺 L2"
    assert "### L14." in disc, "debug 场景缺 L14"


# ── 4. 预算记账：scene=debug ──

def test_prompt_budget_records_debug_scene(silence_event_bus):
    """prompt.budget 事件 discipline 段 scene=='debug'，chars>0，truncated 在场。"""
    _build(MockEngine(), "这里报错了，帮我排查一下")
    events = [d for t, d in silence_event_bus if t == "prompt.budget"]
    assert events, "应发出 prompt.budget 事件"
    disc = events[0]["discipline"]
    assert disc["scene"] == "debug"
    assert disc["chars"] > 0
    assert "truncated" in disc
    # LN-4 口径：sections 不含 discipline
    assert "discipline" not in events[0]["sections"]


# ── 5. 与 GOV-1 施工/收工场景不互斥不串扰 ──

def test_work_scene_still_injects_without_debug_words():
    """施工消息不含调试词时只注入施工纪律，不注入调试纪律（不串扰）。"""
    msgs = _build(MockEngine(), "施工：帮我实现新功能并测试")
    assert _debug_msg(msgs) is None, "纯施工消息不得注入调试纪律"
    disc = None
    for m in msgs:
        c = m.get("content", "")
        if "【施工工作流纪律】" in c:
            disc = c
    assert disc is not None, "施工纪律应照常注入"


def test_wrapup_scene_still_injects():
    """收工消息照常注入收工自审纪律（不串扰）。"""
    msgs = _build(MockEngine(), "收工汇报")
    assert _debug_msg(msgs) is None, "收工消息不得注入调试纪律"
    found = None
    for m in msgs:
        c = m.get("content", "")
        if "【收工自审纪律】" in c:
            found = c
    assert found is not None, "收工自审纪律应照常注入"


def test_wrapup_priority_over_debug():
    """优先级 wrapup > debug：消息同时含收工与报错 → 注入收工纪律。"""
    msgs = _build(MockEngine(), "修完了，收工汇报一下之前报错的处理")
    assert _debug_msg(msgs) is None, "收工优先，不注入调试纪律"
    found = None
    for m in msgs:
        c = m.get("content", "")
        if "【收工自审纪律】" in c:
            found = c
    assert found is not None, "收工优先时应注入收工纪律"


def test_debug_priority_over_work():
    """优先级 debug > work：施工消息含调试词 → 注入调试纪律。"""
    msgs = _build(MockEngine(), "施工时这里报错了，帮我定位一下")
    disc = _debug_msg(msgs)
    assert disc is not None, "施工+报错 → 调试纪律优先"
    # 不注入施工纪律段（调试段已覆盖排查要素，避免双段冗余超预算）
    for m in msgs:
        c = m.get("content", "")
        assert "【施工工作流纪律】" not in c, "调试优先时不注入施工纪律"


def test_debug_detected_via_history():
    """调试信号出现在最近 3 轮 history 也触发（与 work/wrapup 同口径）。"""
    eng = MockEngine(history=[
        {"role": "user", "content": "帮我做个功能"},
        {"role": "assistant", "content": "好的"},
        {"role": "user", "content": "现在崩了白屏了"},
    ])
    msgs = _build(eng, "继续")
    assert _debug_msg(msgs) is not None, "history 含调试信号应注入"


# ── 6. 预算上限 ──

def test_debug_discipline_budget_cap():
    """调试纪律段 ≤ 1600 字符（并入 discipline 段共用预算）。"""
    cap = injector_mod._DISCIPLINE_BUDGET_CHARS
    msgs = _build(MockEngine(), "报错了，帮我排查一下")
    disc = _debug_msg(msgs)
    assert disc is not None
    assert len(disc) <= cap, f"调试纪律段超预算: {len(disc)} > {cap}"


# ── 7. 静态断言：调试纪律段本体 ≤1200 字符（票文硬性要求）──

def test_debug_discipline_text_under_1200():
    """_DEBUG_DISCIPLINE 常量本体 ≤1200 字符（票文要求）。"""
    text = injector_mod._DEBUG_DISCIPLINE
    assert len(text) <= 1200, f"调试纪律段本体 {len(text)} > 1200"


def test_debug_keywords_not_overlap_work():
    """调试关键词与施工关键词不重叠（不串扰的前提）。"""
    debug = set(injector_mod._DEBUG_KEYWORDS)
    work = set(injector_mod._WORK_KEYWORDS)
    overlap = debug & work
    assert not overlap, f"调试与施工关键词重叠: {overlap}"
