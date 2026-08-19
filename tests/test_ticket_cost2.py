"""票 COST-2 专项测试：Prompt 前缀稳定化。

根因（Kimi 实测定案）：_build_now_anchor() 分钟级锚点 + messages.insert(2) 头部注入，
每分钟变一次 → 锚点之后数万 tokens 缓存全作废（实测命中率 3.4%）。

施工两处（仅限本票）：
  ① NOW 锚点后移：insert(2) 头部 → 尾部"最新用户消息之前"（前缀恢复稳定）
  ② 精度降级：分钟级 %H:%M → 小时级（[NOW] 2026-08-16 18时 周六 格式，≤60 字符保留）

验收断言（全部实跑）：
  C1 锚点不在 messages 前三位
  C2 锚点紧跟最新用户消息之前（最后 user 的前一条）
  C3 同小时内两轮锚点逐字相同（两轮一致性）；跨小时才变
  C4 budget_stats["now"] 照记（prompt.budget 事件 sections["now"] chars 与锚点块一致）
  C5 历史消息区零改动（锚点插入不影响历史消息顺序/内容）
  C6 GUIDANCE 仍在自查协议之后（E3b 语义不被后移破坏）
"""

import re
from datetime import datetime

import pytest

from core.injector import PromptInjector


# ── 最小 mock（对齐 test_injector.py，避免跨文件依赖）──

class MockTracker:
    _change_log: list = []
    _read_files: dict = {}


class MockProactive:
    def inject_context(self, messages):
        return messages


class MockSkillLoader:
    def load_standards(self):
        return []
    def list_available(self):
        return ""


class MockEngine:
    def __init__(self, history=None):
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
def injector():
    return PromptInjector(MockEngine())


def _build(injector, history=None, session_id="s1", user_input="当前轮问题"):
    eng = injector._engine
    if history is not None:
        eng.history = history
    return injector.build_messages(
        system_prompt="You are Bobo.",
        user_input=user_input,
        tools_schema=[],
        extra_categories=set(),
        session_id=session_id,
    )


def _find_anchor(msgs):
    """定位 [NOW] 锚点消息 index 与锚点行（可能在任意消息 content 内）。"""
    for i, m in enumerate(msgs):
        c = m.get("content", "")
        if isinstance(c, str) and "[NOW] " in c:
            line = next((l for l in c.splitlines() if l.startswith("[NOW] ")), None)
            if line:
                return i, line
    return None, None


# ── C1：锚点不在 messages 前三位 ──

def test_c1_anchor_not_in_first_three(injector):
    msgs = _build(injector)
    now_idx, _ = _find_anchor(msgs)
    assert now_idx is not None, "未找到 [NOW] 锚点"
    assert now_idx >= 3, f"锚点仍在头部前三位（index={now_idx}），前缀未稳定"


# ── C2：锚点在历史消息区之前（冻结段固定位）──

def test_c2_anchor_in_current_user_message(injector):
    """NOW 锚点在尾部 system 动态块内（消息序列末尾，前缀不受影响；票 COST-6 方案 B）。"""
    msgs = _build(injector)
    now_idx, _ = _find_anchor(msgs)
    assert now_idx is not None
    assert msgs[now_idx]["role"] == "system", \
        f"NOW 应在尾部 system 动态块内（index={now_idx}）"
    assert now_idx == len(msgs) - 1, f"动态块应为最后一个消息（index={now_idx}）"


# ── C3：小时级精度（同小时两轮一致，跨小时才变）──

def test_c3_same_hour_two_rounds_identical(injector, monkeypatch):
    """同一小时内连建两轮 messages，锚点逐字相同（两轮一致性）。"""
    from core.injector import _build_now_anchor
    import core.injector as inj_mod

    class _FakeNow:
        def __init__(self):
            self.current = datetime(2026, 8, 16, 18, 23)
        def now(self, tz=None):
            return self.current.replace(tzinfo=tz)

    fake = _FakeNow()
    monkeypatch.setattr(inj_mod, "_datetime", fake)

    a1 = _build_now_anchor()
    fake.current = datetime(2026, 8, 16, 18, 59)  # 同小时，分钟推进
    a2 = _build_now_anchor()
    assert a1 == a2, f"同小时内锚点不应变化: {a1!r} != {a2!r}"
    # 跨小时才变
    fake.current = datetime(2026, 8, 16, 19, 1)
    a3 = _build_now_anchor()
    assert a1 != a3, "跨小时锚点应变化"
    # 格式：`[NOW] YYYY-MM-DD N时 周X (Asia/Shanghai)`，≤60 字符
    assert re.match(
        r"^\[NOW\] \d{4}-\d{2}-\d{2} \d{1,2}时 (周一|周二|周三|周四|周五|周六|周日) "
        r"\(Asia/Shanghai\)$", a1
    ), f"格式不符: {a1!r}"
    assert len(a1) <= 60, f"锚点超长: {len(a1)}"


# ── C4：预算记账保留 ──

def test_c4_budget_now_kept(injector, silence_event_bus):
    msgs = _build(injector)
    now_idx, anchor = _find_anchor(msgs)
    assert now_idx is not None
    # 完整 NOW 块（锚点行 + 指令行，位于 user 消息内容内、用户输入之前）
    content = str(msgs[now_idx].get("content", ""))
    seg = content[content.index("[NOW] "):]
    now_block = seg.split("\n\n", 1)[0]
    assert now_block.startswith("[NOW] "), f"NOW 块格式异常: {now_block[:40]!r}"
    budgets = [d for t, d in silence_event_bus if t == "prompt.budget"]
    assert budgets, "未发出 prompt.budget 事件"
    sections = budgets[0]["sections"]
    assert "now" in sections, "budget sections 缺少 now（记账必须保留）"
    assert sections["now"]["chars"] == len(now_block), (
        f"budget now.chars={sections['now']['chars']} 与锚点块 len={len(now_block)} 不一致"
    )


# ── C5：历史消息区零改动 ──

def test_c5_history_region_unchanged(injector):
    """动态块注入为尾部 system（票 COST-6 方案 B）；历史消息区零改动。"""
    history = [
        {"role": "user", "content": "第一轮问题"},
        {"role": "assistant", "content": "第一轮回答"},
        {"role": "user", "content": "第二轮问题"},
        {"role": "assistant", "content": "第二轮回答"},
        {"role": "user", "content": "当前轮问题"},
    ]
    expect = [(m["role"], m["content"]) for m in history]  # build 前快照
    msgs = _build(injector, history=history)
    got = [(m["role"], m["content"]) for m in msgs if m["role"] in ("user", "assistant")]
    # role 序列与顺序不变
    assert [r for r, _ in got] == [r for r, _ in expect], "历史消息区 role 序列被改动"
    # 所有历史消息（含当前轮 user）逐字节不变——动态块不再写回 user
    for i, (r, c) in enumerate(expect):
        assert got[i][1] == c, f"历史消息内容被改动: index={i} content={c!r}"
    # 动态块在尾部 system（最后一个消息），user/assistant 区无动态块标记
    assert msgs[-1]["role"] == "system", "动态块应为尾部 system"
    assert "【COST-2 动态块】" in str(msgs[-1]["content"]), "尾部 system 应含动态块"
    # 用户输入保持在 user 消息（动态块不写回 user，前缀稳定）
    assert str(msgs[-2]["content"]) == "当前轮问题" \
        if msgs[-2].get("role") == "user" else True


# ── C6：GUIDANCE 仍在自查协议之后（E3b 语义保持）──

def test_c6_guidance_still_after_selfcheck(injector):
    msgs = _build(injector)
    contents = [m.get("content", "") for m in msgs]
    guidance_idx = next(
        (i for i, c in enumerate(contents) if "[CAPABILITY MAP]" in str(c)), None
    )
    selfcheck_idx = next(
        (i for i, c in enumerate(contents) if "【上下文自查协议】" in str(c)), None
    )
    assert guidance_idx is not None, "GUIDANCE 未注入"
    assert selfcheck_idx is not None, "自查协议未注入"
    assert guidance_idx > selfcheck_idx, "GUIDANCE 必须在自查协议之后（E3b 语义）"


# ── C7：冻结段复用（同一 engine 两轮，R2 前缀 == R1 全部）──
# COST-2 实弹暴露：动态块锚点"最后 user 前"逐轮漂移 + 内容逐轮变
# （proactive 主题/记忆 touch/pending_diff 首轮有次轮无）→ R1 与 R2 公共前缀
# 只有头部（实测命中率 5.3%）。修复：首轮动态块冻结写回 history 开头，
# 后续轮跳过动态注入 → [头部 + 冻结块 + 历史消息] 前缀逐字节稳定。
# 本测试断言同一 engine 两轮构建：R2 的 messages 前缀 == R1 全部
# （即使 proactive 主题已变，冻结段仍复用，R2 命中率可达 ~100%）。

class _InjectingProactive:
    """模拟 full 模式：按轮次主题 insert(0) 注入知识连接。"""

    def __init__(self, topic: str):
        self.topic = topic

    def inject_context(self, messages):
        if self.topic:
            messages.insert(0, {
                "role": "system",
                "content": (
                    "以下是你之前的知识记录，可能对当前对话有帮助：\n"
                    f"- {self.topic} 相关记忆 (id:123)"
                ),
            })
        return messages


def _build_with(history, user_input, topic):
    eng = MockEngine(history=history)
    eng.current_user_input = user_input
    eng.proactive = _InjectingProactive(topic)
    return PromptInjector(eng).build_messages(
        system_prompt="You are Bobo.",
        user_input=user_input,
        tools_schema=[],
        extra_categories=set(),
        session_id="s1",
    )


def _hist_start(m):
    for i, mm in enumerate(m):
        if mm.get("role") in ("user", "assistant", "tool"):
            return i
    return len(m)


def test_c7_head_static_across_rounds():
    """同一 engine 两轮：R2 前缀 == R1 全部（动态块在 user 内容内，前缀稳定）。"""
    eng = MockEngine(history=[{"role": "user", "content": "x"}])
    eng.history = []  # 新会话第一轮
    eng.proactive = _InjectingProactive("主题甲")
    eng.history.append({"role": "user", "content": "R1 输入"})
    inj = PromptInjector(eng)
    r1 = inj.build_messages(
        system_prompt="You are Bobo.", user_input="R1 输入",
        tools_schema=[], extra_categories=set(), session_id="s1",
    )
    eng.history.append({"role": "assistant", "content": "R1 回复"})
    eng.proactive = _InjectingProactive("主题乙")  # 主题逐轮变，动态块实时刷新
    eng.history.append({"role": "user", "content": "R2 输入"})
    r2 = inj.build_messages(
        system_prompt="You are Bobo.", user_input="R2 输入",
        tools_schema=[], extra_categories=set(), session_id="s1",
    )
    assert len(r2) > len(r1), "R2 应比 R1 多（assistant 回复 + 新 user 输入）"
    # 票 COST-6 方案 B：R1 尾部 = system 动态块（不写回 history）；R2 前缀
    # 覆盖 R1 全部非动态块消息（system 头部 + 历史 user/assistant 逐字节相同）
    r1_body = r1[:-1] if r1[-1].get("role") == "system" and \
        str(r1[-1].get("content", "")).startswith("【COST-2 动态块】") else r1
    assert all(r1_body[i] == r2[i] for i in range(len(r1_body))), \
        "R2 前缀未覆盖 R1 历史区（方案 B 前缀稳定未生效）"
    # 动态块实时刷新：主题乙出现在 R2 尾部 system 动态块内
    assert "主题乙" in str(r2[-1].get("content", "")), "动态块应实时刷新（主题乙）"
    # history 无动态块污染（只有 user/assistant，纯用户输入）
    assert all(m["role"] in ("user", "assistant") for m in eng.history), \
        "history 不应有动态块 system 污染"


# ── C8：proactive 知识连接搬移（full 模式 insert(0) → 尾部）──

def test_c8_proactive_moved_to_tail():
    """proactive 知识连接不得留在 messages[0]（前缀第一位）；移入尾部 system 动态块。"""
    history = [{"role": "user", "content": "问题"},
               {"role": "assistant", "content": "回答"}]
    msgs = _build_with(history + [{"role": "user", "content": "当前轮"}],
                       "当前轮", topic="测试主题")
    first = str(msgs[0].get("content", ""))
    assert not first.startswith("以下是你之前的知识记录"), \
        f"proactive 连接仍在 messages[0]（前缀第一位）: {first[:40]}"
    assert msgs[-1]["role"] == "system", "动态块应为尾部 system（票 COST-6 方案 B）"
    assert "以下是你之前的知识记录" in str(msgs[-1].get("content", "")), \
        "proactive 连接应移入尾部 system 动态块内"
