"""core/cu_policy.py — computer use 政策（E4：从 engine 搬出，骨干通信"政策部"雏形）。

纯函数 + 参数化决策：不持有 engine 引用，所需状态全部经参数传入。
engine 侧保留薄壳委托（行为逐字节一致）。
票：TICKET-COMPUTER-USE-ACTION / AWARENESS（COST-3）。
"""

# 票 AWARENESS（COST-3）：computer use 模式下，现有"读/查/写/代码"工具是"辅助/配合"，
# 不屏蔽、不作降级拦截——bobo 依意图判断哪个更优就配合用。仅真正绕过 computer_use
# 主操作的 shell/网络原语（execute_terminal/bash/curl 等）才走降级排查。
CU_COOPERATION_TOOLS = {
    "web_search", "web_fetch", "writefiles", "write_obsidian", "append_obsidian",
    "file_operation", "file_writer", "code_execution", "read_local_file",
    "grep_code", "list_directory", "read_obsidian", "search_obsidian",
    "cross_search", "run_tests", "load_result",
}

# 降级判定返回常量
ALLOW = "allow"
DENY = "deny"
ASK = "ask"


def cu_active(getter) -> bool:
    """computer use 模式是否开（只读 getter 注入，不持有 engine）。"""
    return bool(getter is not None and getter())


def cu_error(raw) -> bool:
    """computer_use 返回是否含错误信号。"""
    if not raw:
        return False
    r = str(raw)
    return r.startswith("错误") or r.startswith("⛔") or "失败" in r


def cu_error_is_tool_bug(raw) -> bool:
    """排查：computer_use 报错是"工具 bug"还是"网络/环境"。

    工具 bug（权限未授权/AX 不支持/元素越界/截屏失败/打开失败）→ True（不降级糊弄）；
    网络/环境（连接失败/超时/不可达）→ False（可降级）；未知错误保守视为工具 bug。
    """
    if not raw:
        return False
    r = str(raw)
    # 工具 bug 特征
    if any(k in r for k in ("权限", "未授权", "不支持", "越界", "未识别",
                            "请先授权", "Accessibility", "Screen Recording",
                            "截屏失败", "打开应用", "驱动", "元素")):
        return True
    # 网络/环境特征
    if any(k in r for k in ("网络", "连接失败", "超时", "无法连接", "timed out",
                            "connection", "unreachable", "SSE", "服务不可用")):
        return False
    # 未知错误 → 保守视为工具 bug
    if r.startswith("错误") or r.startswith("⛔"):
        return True
    return False


def degrade_decide(*, cu_on: bool, tool_name: str, last_result,
                   auto_active: bool) -> str:
    """computer use 降级判定（不"试一下不行就降级"）。

    返回 'allow'/'deny'/'ask'：
    - deny：还没用 computer_use 就想绕过硬操作 / computer_use 工具自身 bug → 拦。
            工具 bug 说清"这是工具问题"，不靠降级糊弄。
    - allow：computer_use 正常（灵活配合，34节：bash/writefiles 是辅助可配合）。
            或网络/环境问题 + auto 模式（自动降级）。
    - ask：网络/环境问题 + normal 模式 → 降级前先问用户（confirm_callback 弹窗）。
    """
    if not cu_on or tool_name == "computer_use":
        return ALLOW
    # 票 AWARENESS（COST-3）：配合工具在 computer use 模式下放行（配合，不拦截）
    if tool_name in CU_COOPERATION_TOOLS:
        return ALLOW
    if last_result is None:
        return DENY  # 未试 computer_use 就换工具 → 拦，让 bobo 先试 computer_use
    if not cu_error(last_result):
        return ALLOW  # computer_use 成功 → 换其他工具是"灵活配合"（34节），放行
    if cu_error_is_tool_bug(last_result):
        return DENY  # 工具 bug，说清不糊弄
    # 网络/环境问题 → 可降级
    if auto_active:
        return ALLOW  # auto 自动降级
    return ASK  # normal 降级 → 问用户


_CU_SELF_ANCHOR = (
    "\n\n### 自我认知锚点（本会话模式自述，任何决策前必读）\n"
    "1. 你当前**处于 computer use 模式**——本会话被指定为在真实电脑上操作。\n"
    "2. 你有 **computer_use 工具**：capture（看屏+AX树索引）/ click（点击）/ type（输入）/ "
    "key（组合键）/ open_app（打开应用）/ scroll（滚动）——你能直接操作电脑的**任何界面**"
    "（Safari/Pages/Finder/系统设置等）。\n"
    "3. 做界面/搜索/操作类任务，**应优先用 computer_use**（打字/滑动/点击/打开应用都走它），"
    "一次定位就操作，快而精准；不要一上来就写脚本/applescript 造轮子。\n"
    "4. 现有其他工具（web_search/writefiles/code 等）**降为辅助/配合**——不屏蔽、可用，"
    "但由你判断：若某工具配合比纯 computer_use 更高效，就选它配合；**computer_use 始终是主操作**。\n"
    "5. **落点铁律**：无论用 computer_use 还是配合工具，操作都发生在**目标系统"
    "（用户指定的那个系统/APP）上**（34节），不要跳出到文件/文本抽象层。\n"
    "6. 意图（goal）是决策的根：所有手段围绕 GOAL 展开，换手段不漂移目标。"
)


def cu_system_prompt(sys_prompt: str, cu_on: bool) -> str:
    """computer use 模式 → 注入"自我认知锚点"（工程化注入，非弱提示）。"""
    if not cu_on:
        return sys_prompt
    return sys_prompt + _CU_SELF_ANCHOR


def cu_llm_kw(llm_has_tool_calls: bool, cu_on: bool) -> dict:
    """computer use 模式 + 工具轮 → thinking_disabled=True（快速直接操作，不深度推理）。"""
    if cu_on and llm_has_tool_calls:
        return {"thinking_disabled": True}
    return {}
