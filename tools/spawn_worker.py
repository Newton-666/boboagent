"""spawn_worker — 将子任务派给独立 Worker Agent 执行

Worker 有独立上下文，不会污染主 Engine 的对话。
完成任务后返回轻量标记，完整摘要可通过 read_worker_result 获取。
禁止嵌套 spawn（代码层拦截）。
"""

import hashlib
import os
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError

TOOL_NAME = "spawn_worker"
_WORKER_TIMEOUT = 110  # 首次超时，低于 tool_executor 的 120s 上限
_WORKER_RETRY_TIMEOUT = 300  # 超时重试时给更长时间

# 代码修改关键词——用于轻量检测缺少前置分析
_MODIFY_KEYWORDS = ["修改", "重构", "编辑", "改写", "重写", "添加功能",
                     "implement", "refactor", "modify", "edit", "rewrite"]


def _build_worker_prompt(instruction: str, name: str) -> str:
    """构建 Worker 的 system prompt。"""
    role_line = f"你的 role：{name}" if name else "你的 role：由主 Engine 的指令指定"
    return (
        f"你是 Bobo 派出的 Worker Agent。\n\n"
        f"## 身份\n"
        f"{role_line}\n\n"
        f"## 任务\n"
        f"完成主 Engine 交给你的指令。完成之前不要停。\n"
        f"完成之后返回结果摘要。主 Engine 只看你的摘要来做出下一步判断。\n\n"
        f"## 你必须遵守\n"
        f"- **禁止嵌套**：不要 spawn 子 Worker。你做的所有事自己完成。\n"
        f"- **纯文字 = 任务结束**：如果你还有工作要做，回复必须同时携带工具调用。\n"
        f"  只说下一步而不调工具，主 Engine 会认为你完成了。\n"
        f"- **诚实**：工具失败了换方法试，实在不行就如实报告失败原因。\n"
        f"- **安全**：不要执行 rm -rf、sudo、chmod 777 等危险命令。\n\n"
        f"## 输出要求\n"
        f"任务完成后，输出一段简洁的摘要：\n"
        f"- 做了什么\n"
        f"- 结果是什么\n"
        f"- 有什么需要注意的\n"
        f"不要输出过程汇报。\n"
    )

# 线程局部变量：标记当前是否在 Worker 中运行
_worker_depth = threading.local()
_worker_depth.depth = 0

# 存储 Worker 完成的结果摘要（name → 摘要全文），供 read_worker_result 查询
# 有意为进程级共享：Worker 在线程中写入，主 Engine 通过 read_worker_result 工具跨调用读取
_WORKER_RESULTS: dict[str, str] = {}
_WORKER_RESULTS_LOCK = threading.Lock()

# LLM caller 缓存（会话内 provider 和 schema 不变，无需重复创建）
# 缓存 key 为 (provider, model, api_key 哈希)，切换 provider/model/key 后自动 miss
_llm_caller_cache = None
_llm_caller_cache_key = None

# ── Worker 实时事件回调 ──
# 被 engine_adapter.run_engine 注入，用于向 TUI 发送 Worker 进度
_worker_event_emitter = None
_worker_sid = None


def set_worker_event_emitter(emitter, sid: str = None):
    """设置 Worker 事件发射器 + 当前会话 ID。"""
    global _worker_event_emitter, _worker_sid
    _worker_event_emitter = emitter
    _worker_sid = sid


def _make_worker_callback(name: str):
    """Worker 的回调：每调一个工具就发 thinking 事件到 TUI。"""
    def _cb(event_type: str, data: dict):
        if event_type != "tool_call":
            return
        tool = data.get("tool_name", "")
        args = data.get("tool_args", {})
        # 生成简短的工具调用描述
        desc = tool
        if isinstance(args, dict):
            for key, preview_key in [("query", "query"), ("command", "command"), ("filepath", "filepath"),
                                       ("url", "url"), ("instruction", "instruction")]:
                val = args.get(key, "")
                if val:
                    desc = f'{tool}("{str(val)[:40]}")'
                    break
        emitter = _worker_event_emitter
        if emitter:
            emitter("thinking", _worker_sid or "", {"message": f"[Worker {name}] {desc}"})
    return _cb


def _get_llm_caller():
    """获取缓存的 LLM caller，配置变化时重新创建。"""
    global _llm_caller_cache, _llm_caller_cache_key
    from core.llm_caller import create_llm_caller
    from core.provider import resolve_provider
    from tools import TOOLS_SCHEMA
    config = resolve_provider()
    # api_key 只存短哈希，避免明文驻留缓存 key
    key_hash = hashlib.md5((config["api_key"] or "").encode()).hexdigest()[:12]
    cache_key = (config["name"], config["model"], key_hash)
    if _llm_caller_cache is not None and _llm_caller_cache_key == cache_key:
        return _llm_caller_cache
    _llm_caller_cache = create_llm_caller(
        api_key=config["api_key"],
        api_url=config["base_url"],
        model_name=config["model"],
        tools_schema=TOOLS_SCHEMA,
    )
    _llm_caller_cache_key = cache_key
    return _llm_caller_cache


def _run_worker_with_timeout(worker, worker_input: str, timeout: int) -> tuple[str, bool]:
    """在独立线程中运行 Worker，返回 (result, timed_out)。"""
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as _FutTimeout
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(worker.run, worker_input)
        try:
            future.result(timeout=timeout)
            return ("", False)  # 正常完成，result 由调用方通过 _extract_worker_result 获取
        except _FutTimeout:
            if hasattr(worker, "_interrupt_event") and worker._interrupt_event:
                worker._interrupt_event.set()
            return ("", True)


def _extract_worker_result(history: list) -> str:
    """从 Worker 的 history 中提取最终回复作为结果摘要。"""
    for msg in reversed(history):
        role = msg.get("role", "")
        if role == "assistant":
            content = msg.get("content", "")
            if content and content.strip():
                return content.strip()
    return "(Worker 没有产生回复)"


def _extract_tool_log(history: list) -> str:
    """从 Worker 的 history 中提取工具调用记录。"""
    entries = []
    pending_names = {}  # tool_call_id → tool_name
    for msg in history:
        role = msg.get("role", "")
        if role == "assistant":
            for tc in msg.get("tool_calls") or []:
                tid = tc.get("id", "")
                fn = tc.get("function", {})
                if fn.get("name"):
                    pending_names[tid] = fn["name"]
        elif role == "tool":
            content = msg.get("content", "") or ""
            # 从 tool result 中提取耗时
            duration = ""
            import re as _re
            m = _re.search(r"（耗时: ([\d.]+)s）", content)
            if m:
                duration = m.group(1) + "s"
            entries.append((pending_names.get(msg.get("tool_call_id", ""), "?"), duration))
    if not entries:
        return ""
    lines = ["━━ 执行记录 ━━"]
    for name, dur in entries:
        d = f" → {dur}" if dur else ""
        lines.append(f"  ✓ {name}{d}")
    return "\n".join(lines)


def execute(instruction: str = "", name: str = "", context: str = "", task: str = "") -> str:
    # task 是 instruction 的别名——LLM 常常猜 task 而不知道参数名是 instruction
    instruction = instruction or task
    """执行子任务并返回轻量标记，完整结果可通过 read_worker_result 获取。"""
    # ── 禁止嵌套 spawn ──
    if getattr(_worker_depth, "depth", 0) > 0:
        return (
            "[ERROR] 嵌套 spawn 被禁止：Worker 不能 spawn 子 Worker。\n"
            "请将子任务合并到当前 Worker 的指令中，或返回主 Agent 重新调度。"
        )

    try:
        # ── 加载依赖（确保在 tool context 内延迟导入） ──
        # ── 解析/获取缓存的 LLM caller ──
        llm_caller = _get_llm_caller()

        from core.engine import Engine
        from core.tool_executor import execute_tool

        # ── 构建 Worker 的 system prompt ──
        worker_prompt = _build_worker_prompt(instruction, name)

        # ── 构建 Worker 的输入 ──
        worker_input = instruction
        if name:
            worker_input = f"[你的角色: {name}]\n{instruction}"
        if context:
            worker_input += f"\n[背景信息]\n{context}"

        # ── 创建 Worker Engine ──
        worker = Engine(
            llm_caller=llm_caller,
            tool_executor=execute_tool,
            test_mode=False,
            callback=_make_worker_callback(name or instruction[:20]),
        )
        worker.system_prompt = worker_prompt

        # ── 设置嵌套检测标志 ──
        _worker_depth.depth = getattr(_worker_depth, "depth", 0) + 1

        # ── 在独立线程中运行 Worker，超时后自动重试一次 ──
        result, timed_out = _run_worker_with_timeout(worker, worker_input, _WORKER_TIMEOUT)

        if timed_out:
            partial = _extract_worker_result(worker.history)
            if partial and partial != "(Worker 没有产生回复)":
                # 有进度且超时 → 重试一次，给更长时间
                worker2 = Engine(
                    llm_caller=llm_caller,
                    tool_executor=execute_tool,
                    test_mode=False,
                )
                worker2.system_prompt = worker_prompt
                _worker_depth.depth = getattr(_worker_depth, "depth", 0) + 1
                result2, _ = _run_worker_with_timeout(worker2, worker_input, _WORKER_RETRY_TIMEOUT)
                _worker_depth.depth = max(0, getattr(_worker_depth, "depth", 0) - 1)
                return result2
            else:
                # 没进度 → 直接返回超时错误
                return (
                    f"[WORKER_TIMEOUT] Worker 执行超过 {_WORKER_TIMEOUT}s，无有效输出。\n"
                )

        # ── 提取结果 ──
        result = _extract_worker_result(worker.history)
        tool_log = _extract_tool_log(worker.history)
        if tool_log:
            result = f"{tool_log}\n\n━━ 结果摘要 ━━\n{result}"
        state = getattr(worker, "state", "")
        if state == worker.STATE_ERROR if hasattr(worker, "STATE_ERROR") else False:
            return f"[WORKER_ERROR]\n{result}"

        # 轻量检测：代码修改任务缺少前置分析 context
        if not context and any(kw in instruction.lower() for kw in _MODIFY_KEYWORDS):
            result = (
                f"[NOTE] 该 Worker 的执行指令包含代码修改关键词，"
                f"但未提供前置分析的 context。\n"
                f"如果结果不符合预期，建议先 spawn 大局分析 Worker 进行代码理解。\n\n"
                f"{result}"
            )

        # 存储完整摘要，供 read_worker_result 查询
        # 有 name 则存储（重名会覆盖），无 name 不存
        if name:
            with _WORKER_RESULTS_LOCK:
                _WORKER_RESULTS[name] = result

        # 返回轻量标记：有 name 时只带状态摘要，无 name 时返回全文
        if name:
            tool_count = result.count("✓")
            summary = result.split("━━ 结果摘要 ━━")[-1].strip()[:100].replace('\n', ' ').strip()
            if tool_count:
                return f"[WORKER_COMPLETE:{name}] 调用 {tool_count} 个工具，{summary}"
            return f"[WORKER_COMPLETE:{name}] {summary}"
        return result

    except Exception as e:
        return f"[WORKER_ERROR] Worker 执行失败: {str(e)}"
    finally:
        _worker_depth.depth = max(0, getattr(_worker_depth, "depth", 0) - 1)


# ── spawn_worker 工具 ──

TOOL_FUNC = execute
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": (
            "将一个子任务派给独立的 Worker Agent 执行，完成后返回轻量标记。\n"
            "完整结果可通过 read_worker_result 获取。\n"
            "Worker 有独立的对话上下文，不会污染当前对话。\n"
            "Worker 专注单一模块或子任务，产出代码质量更好。\n"
            "适用场景：多文件代码项目、独立研究、需要长时间运行的任务。\n"
            "多个独立子任务可以在同一轮回复中并行 spawn。\n"
            "不适用于：单步简单操作（直接调工具即可）。\n"
            "**代码修改任务必须经过三个步骤：**\n"
            "1. 先 spawn 大局分析 Worker（只读代码，输出方案）\n"
            "2. 再 spawn 修改 Worker（传入分析结果作为 context 执行修改）\n"
            "3. 可复用大局 Worker 验证修改（传入 diff 作为 context）\n"
            "不要直接 spawn 修改 Worker 而不提供前置分析的 context。\n"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "instruction": {
                    "type": "string",
                    "description": (
                        "必填。Worker 的完整指令，必须包含：\n"
                        "- 它的 role（你是谁？研究员？代码修改者？测试员？）\n"
                        "- 它要解决的问题是什么\n"
                        "指令要详细、明确，让 Worker 不需要追问就能执行。"
                    ),
                },
                "name": {
                    "type": "string",
                    "description": (
                        "可选。Worker 的名称，用于跟踪、调试和获取完整结果。\n"
                        "提供 name 后返回轻量标记，完整摘要通过 read_worker_result 获取。\n"
                        "如 'researcher'、'big-picture-analyzer'、'bug-fixer'。"
                    ),
                },
                "context": {
                    "type": "string",
                    "description": (
                        "可选。Worker 执行前需要的背景信息。\n"
                        "如果是大量内容（如完整文件），传文件路径让 Worker 自己去读。"
                    ),
                },
                "task": {
                    "type": "string",
                    "description": "instruction 的别名——如果没传 instruction 但传了 task，以 task 为准。",
                },
            },
            "required": ["instruction"],
        },
    },
}


# ── read_worker_result 工具 ──

READ_WORKER_TOOL_NAME = "read_worker_result"


def execute_read_worker_result(name: str) -> str:
    """获取指定名称的 Worker 的完整结果摘要。"""
    with _WORKER_RESULTS_LOCK:
        full = _WORKER_RESULTS.get(name)
        if full is None:
            available = ', '.join(_WORKER_RESULTS.keys()) or "(无)"
            return f"没有找到 Worker '{name}' 的结果。可用的 Worker: {available}"
    return full


READ_TOOL_FUNC = execute_read_worker_result
READ_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": READ_WORKER_TOOL_NAME,
        "description": (
            "获取指定名称的 Worker 的完整结果摘要。\n"
            "spawn_worker 返回标记后，如果你需要查看详细内容，可以调此工具。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Worker 的名称（spawn_worker 时传入的 name 参数值）",
                },
            },
            "required": ["name"],
        },
    },
}


def register(reg):
    reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA)
    reg(READ_WORKER_TOOL_NAME, READ_TOOL_FUNC, READ_TOOL_SCHEMA)
