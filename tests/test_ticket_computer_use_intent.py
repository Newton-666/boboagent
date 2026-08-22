"""TICKET-COMPUTER-USE-INTENT 专项测试 — 意图判断 GOAL/TARGET/MEANS 约束框架。

覆盖（票验收）：
1. 正确解析 GOAL/TARGET/MEANS（"用谷歌搜DeepSeek新闻"→goal=新闻, means=谷歌）。
2. 防手段当目的（不把"谷歌"当搜索目标）。
3. GOAL 必须可复述（不可复述 → 拒绝/要求澄清 → parse_intent 返回 None）。
4. 手段可换但 GOAL 不变（google→safari，goal 仍=找新闻）。
5. 意图注入 build_messages（GOAL 常驻上下文，工具轮仍可见）。

依据 docs/DISCUSSION-SELF-EVOLVING.md 第 36 节：意图是决策的根。
"""

from core.intent import parse_intent, format_intent_block
from core import engine as eng


def _fake_llm(content: str):
    """构造一个 llm_caller 桩：返回预设 JSON content 的 resp 结构。"""
    def _caller(*a, **k):
        return {"choices": [{"message": {"content": content}}]}
    return _caller


def test_parse_intent_goal_target_means():
    """正确解析 GOAL/TARGET/MEANS：'用谷歌搜DeepSeek新闻'→goal=新闻, means=谷歌。"""
    fake = _fake_llm(
        '{"goal": "DeepSeek视觉模型的最新新闻", "target": "浏览器/谷歌", '
        '"means": ["谷歌搜索", "safari"], "need_clarify": false}'
    )
    r = parse_intent("用谷歌搜DeepSeek视觉模型新闻", fake)
    assert r is not None
    assert "DeepSeek" in r["goal"] and "新闻" in r["goal"]
    assert "谷歌" in r["target"]
    assert "谷歌搜索" in r["means"]


def test_parse_intent_not_means_as_goal():
    """防手段当目的：不把'谷歌'当成搜索目标（MEANS/TARGET 区分）。"""
    fake = _fake_llm(
        '{"goal": "DeepSeek视觉模型的最新新闻", "target": "浏览器/谷歌", '
        '"means": ["谷歌"], "need_clarify": false}'
    )
    r = parse_intent("用谷歌搜DeepSeek视觉模型新闻", fake)
    assert r is not None
    # 谷歌是手段，不是目标：goal 里不能把谷歌当终点
    assert r["goal"].strip() != "谷歌"
    assert "谷歌" in r["means"]
    # GOAL 是找新闻，不是搜"谷歌"
    assert "新闻" in r["goal"]


def test_parse_intent_goal_required_clarify():
    """GOAL 必须可复述：不可复述/含糊 → 返回 None（机制强制拒绝，非文字提醒）。"""
    fake = _fake_llm(
        '{"goal": "", "target": "", "means": [], "need_clarify": true}'
    )
    r = parse_intent("帮我搞一下那个东西", fake)
    assert r is None  # 无 GOAL → 不注入，调用方静默
    # 纯聊天（无需要锚定的意图）也应返回 None
    fake2 = _fake_llm(
        '{"goal": "", "target": "", "means": [], "need_clarify": false}'
    )
    assert parse_intent("今天天气如何", fake2) is None
    # 空输入直接 None
    assert parse_intent("", fake) is None


def test_parse_intent_means_changeable_goal_stable():
    """手段可换但 GOAL 不变：google→safari，goal 仍=找新闻。"""
    fake_g = _fake_llm(
        '{"goal": "寻找DeepSeek视觉模型的新闻", "target": "浏览器", '
        '"means": ["谷歌搜索"], "need_clarify": false}'
    )
    fake_s = _fake_llm(
        '{"goal": "寻找DeepSeek视觉模型的新闻", "target": "浏览器", '
        '"means": ["safari"], "need_clarify": false}'
    )
    r1 = parse_intent("用谷歌搜DeepSeek新闻", fake_g)
    r2 = parse_intent("用谷歌搜DeepSeek新闻", fake_s)
    assert r1["goal"] == r2["goal"]  # GOAL 不变
    assert r1["means"] != r2["means"]  # 手段可变


def test_intent_injected_build_messages():
    """意图注入 build_messages：GOAL 常驻上下文，工具轮（再调）仍可见，防漂移。"""
    e = eng.Engine(lambda *a, **k: {}, tool_executor=lambda *a, **k: None)
    # 模拟 run() 已解析意图
    e._current_intent = {
        "goal": "DeepSeek视觉模型的最新新闻", "target": "浏览器/谷歌",
        "means": ["谷歌搜索"], "need_clarify": False,
    }
    msgs = e.injector.build_messages(
        system_prompt="base", user_input="用谷歌搜DeepSeek新闻",
        tools_schema=[], extra_categories=set(), session_id="t1",
    )
    joined = "\n".join(m.get("content", "") for m in msgs)
    assert "GOAL" in joined and "DeepSeek视觉模型的最新新闻" in joined
    assert "GOAL 永不丢" in joined
    # 工具轮（再次 build_messages）GOAL 仍在 → 常驻
    msgs2 = e.injector.build_messages(
        system_prompt="base", user_input="",
        tools_schema=[], extra_categories=set(), session_id="t1",
    )
    joined2 = "\n".join(m.get("content", "") for m in msgs2)
    assert "DeepSeek视觉模型的最新新闻" in joined2


def test_format_intent_block_empty_then_safe():
    """format_intent_block 对空/无 goal 输入返回空串（不注入炸）。"""
    assert format_intent_block({}) == ""
    assert format_intent_block({"goal": ""}) == ""
    assert format_intent_block({"goal": "g", "target": "t", "means": ["m"]})
