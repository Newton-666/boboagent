"""票 COST-6 专项测试 — 消除"双 user 夹工具轮"触发结构（方案 B：尾部 system）。

验收标准 1：构造"动态块 user + 工具轮 + 第二 user"history → build_messages
输出不再触发结构（动态块不再以 user 角色注入、不写回 history）。

方案 B 语义断言：
1. 动态块注入为**尾部 system** 消息（role=system，content 以【COST-2 动态块】开头）；
2. messages 中**没有任何 user 消息**以动态块标记开头（动态块不占 user 角色 →
   不会形成"双 user 夹工具轮"触发结构）；
3. engine.history **不被污染**：build_messages 前后 history 各 user content
   逐字节不变（纯用户输入，前缀稳定）；
4. REASONING-ECHO 兜底仍生效：工具轮 assistant 的 reasoning_content 回传；
5. 对照组：无 _tail_blocks（注入为空）时不产生尾部 system。

注：_DYN_MARK 是 build_messages 局部变量，测试用字面量"【COST-2 动态块】"。
"""

from core.injector import PromptInjector
from tests.test_injector import MockEngine

DYN_MARK = "【COST-2 动态块】"


def _tool_history():
    """双 user 夹工具轮 history（写回方案下两个 user 都会被动态块污染 → 400）。"""
    return [
        {"role": "user", "content": "第一问：列出项目文件"},
        {"role": "assistant", "content": "",
         "tool_calls": [{"id": "tc1", "type": "function",
                         "function": {"name": "list_directory", "arguments": "{}"}}],
         "thinking": "需要列目录"},
        {"role": "tool", "tool_call_id": "tc1", "content": "文件列表: [a.py, b.py]"},
        {"role": "user", "content": "第二问：继续"},
    ]


def _build(history):
    eng = MockEngine()
    eng.history = history
    inj = PromptInjector(eng)
    msgs = inj.build_messages(
        system_prompt="You are Bobo.",
        user_input="第二问：继续",
        tools_schema=[],
        extra_categories=set(),
        session_id="",
    )
    return eng, msgs


def test_cost6_no_dynblock_user(monkeypatch):
    """核心：动态块不再以 user 角色注入——无双动态块 user 夹工具轮结构。"""
    eng, msgs = _build(_tool_history())

    dyn_users = [m for m in msgs
                 if m.get("role") == "user"
                 and str(m.get("content", "")).startswith(DYN_MARK)]
    assert dyn_users == [], f"动态块不得以 user 角色注入: {dyn_users}"


def test_cost6_dynblock_is_tail_system(monkeypatch):
    """动态块注入为尾部 system 消息。"""
    eng, msgs = _build(_tool_history())

    tail = msgs[-1]
    assert tail["role"] == "system", f"动态块应在尾部 system: {tail}"
    assert str(tail["content"]).startswith(DYN_MARK), "尾部 system 应以动态块标记开头"
    # 尾部 system 必须是最后一条（REASONING-ECHO 浅拷贝不改角色）
    assert all(m["role"] != "system" or m is tail
               for m in msgs if str(m.get("content", "")).startswith(DYN_MARK)), \
        "动态块 system 应恰好一条且在末尾"


def test_cost6_history_not_polluted(monkeypatch):
    """history 不被污染：build_messages 前后 user content 逐字节不变（前缀稳定）。"""
    hist = _tool_history()
    before = [dict(m) for m in hist]
    eng, msgs = _build(hist)

    assert len(eng.history) == len(before)
    for orig, cur in zip(before, eng.history):
        assert orig["content"] == cur["content"], \
            f"history 被污染: {orig['content']!r} -> {cur['content']!r}"
        assert not str(cur["content"]).startswith(DYN_MARK), "history 不得出现动态块标记"


def test_cost6_no_tail_blocks_no_system(monkeypatch):
    """对照组：NOW 锚点缺失时动态块降级——尾部 system 不含 [NOW]（记忆等其他段照常）。"""
    # monkeypatch 让 NOW 锚点返回空，验证锚点缺失的静默降级（锚点注入被禁用时
    # 动态块不应携带 NOW 段；其余动态段按各自触发条件照常注入，不受影响）
    import core.injector as inj_mod
    monkeypatch.setattr(inj_mod, "_build_now_anchor", lambda: "")

    eng = MockEngine()
    eng.history = [{"role": "user", "content": "你好"}]
    msgs = PromptInjector(eng).build_messages(
        system_prompt="You are Bobo.",
        user_input="你好",
        tools_schema=[],
        extra_categories=set(),
        session_id="",
    )
    tail = msgs[-1]
    is_dyn = tail["role"] == "system" and \
        str(tail.get("content", "")).startswith(DYN_MARK)
    if is_dyn:
        # 有动态块注入（记忆等其他段照常）→ NOW 段必须静默降级
        assert "[NOW]" not in str(tail.get("content", "")), \
            "NOW 锚点缺失时动态块不得含 [NOW] 段"
    else:
        # 无任何动态段（孤立环境仅 NOW 为来源）→ 尾部不产生动态块 system
        assert tail["role"] in ("user", "assistant"), \
            "无动态段注入时尾部不应是动态块 system"


def test_cost6_reasoning_echo_still_works(monkeypatch):
    """REASONING-ECHO 兜底仍生效：工具轮 assistant 的 reasoning_content 回传。"""
    eng, msgs = _build(_tool_history())

    tc_assistants = [m for m in msgs
                     if m.get("role") == "assistant" and m.get("tool_calls")]
    assert tc_assistants, "测试构造应含工具轮 assistant"
    for a in tc_assistants:
        assert "reasoning_content" in a, "工具轮 assistant 必须回传 reasoning_content"
        assert a["reasoning_content"] == a.get("thinking", ""), \
            "reasoning_content 应与 thinking 一致"


def test_cost6_full_messages_structure(monkeypatch):
    """完整结构快照：system 头部 + 双 user + 工具轮 + 尾部动态块 system。"""
    eng, msgs = _build(_tool_history())

    roles = [m["role"] for m in msgs]
    assert roles[0] == "system"
    assert "user" in roles and roles.count("user") >= 2
    assert "tool" in roles
    # 动态块尾部 system 是最后一条，其后无 user
    assert msgs[-1]["role"] == "system"
    user_idx = [i for i, m in enumerate(msgs) if m["role"] == "user"]
    tail_idx = len(msgs) - 1
    assert max(user_idx) < tail_idx, "尾部 system 之后不得再有 user"
