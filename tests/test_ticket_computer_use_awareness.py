"""TICKET-COMPUTER-USE-AWARENESS 专项测试 — 自我认知锚点 + 工具配合逻辑。

覆盖（票验收）：
1. 自我认知锚点注入：computer use 模式开启 → system prompt 含完整模式自述（非一句弱提示）。
2. bobo 决策时能看到"自己处于 computer use 模式 + 有能力 + 应优先 + 其他工具辅助 + 落点铁律"。
3. 工具配合：web_search/writefiles/code 等不屏蔽、降为"辅助"，不是"降级"拦截。
4. 落点铁律：操作发生在目标系统（不跳出到文件层）。
5. 意图 goal 在配合工具时仍常驻（防手段漂移）。

依据 docs/DISCUSSION-SELF-EVOLVING.md 第 34/35/36 节 + owner 定稿：
"Agent 决策正确性上游 = 对自己有足够了解；所有现有工具降为辅助，computer use 为主。"
"""

from core import engine as eng


def _make_engine(cu=True, auto=False, test_mode=True):
    return eng.Engine(
        lambda *a, **k: {}, tool_executor=lambda *a, **k: None,
        computer_use_mode_getter=(lambda: cu),
        auto_mode_getter=(lambda: auto),
        test_mode=test_mode,
    )


# ── 任务 A：自我认知锚点 ────────────────────────────────────────────────
def test_awareness_anchor_injected():
    """computer use 模式开启 → 完整模式自述（非一句弱提示）。"""
    e = _make_engine(cu=True)
    sp = e._cu_system_prompt("BASE")
    assert "自我认知锚点" in sp
    assert "处于 computer use 模式" in sp          # ① 知道自己处于该模式
    assert "computer_use 工具" in sp               # ② 知道自己有能力（capture/click/type/key/open_app/scroll）
    assert "优先用 computer_use" in sp             # ③ 知道自己应优先用它
    assert "辅助/配合" in sp                       # ④ 知道其他工具是辅助
    assert "落点铁律" in sp and "目标系统" in sp    # ⑤ 知道落点在目标系统
    # 完整自述（6 条结构化条目），非"一句话弱提示"
    assert "\n1." in sp and "\n6." in sp


def test_awareness_anchor_off_when_cu_off():
    """computer use 模式关闭 → 不注入锚点（返回原 prompt）。"""
    e = _make_engine(cu=False)
    assert e._cu_system_prompt("BASE") == "BASE"


def test_awareness_anchor_mentions_abilities():
    """锚点里列出 computer_use 的完整原子能力（自述有资格用）。"""
    e = _make_engine(cu=True)
    sp = e._cu_system_prompt("BASE")
    for ability in ("capture", "click", "type", "key", "open_app", "scroll"):
        assert ability in sp


# ── 任务 B：工具配合逻辑（非降级）──────────────────────────────────────
def test_cooperation_tools_not_blocked():
    """配合工具（web_search/writefiles/code 等）在 computer use 模式放行（配合，非降级拦截）。"""
    e = _make_engine(cu=True)
    for t in ("web_search", "web_fetch", "writefiles", "code_execution",
              "grep_code", "read_local_file", "write_obsidian", "run_tests"):
        assert e._degrade_decide(t, {}, "x") == "allow", f"{t} 应作为配合放行"


def test_shell_bypass_still_degrade_checked():
    """仅绕过 computer_use 主操作的 shell/网络原语（execute_terminal 等）仍走降级排查。"""
    e = _make_engine(cu=True)
    # execute_terminal 不在配合白名单，且未试 computer_use → deny（先排查）
    assert e._degrade_decide("execute_terminal", {}, "x") == "deny"


def test_goal_resident_when_cooperating():
    """意图（goal）在配合工具时仍常驻（防手段漂移：配合换手段不丢 GOAL）。"""
    e = _make_engine(cu=True)
    e._current_intent = {"goal": "搜Claude code模型更新", "target": "谷歌",
                          "means": ["谷歌搜索"]}
    # 配合工具放行（bobo 判断更优就用）
    assert e._degrade_decide("web_search", {}, "x") == "allow"
    # goal 常驻防漂移
    assert e._current_intent["goal"] == "搜Claude code模型更新"
