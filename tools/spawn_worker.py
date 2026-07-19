"""spawn_worker — 将子任务派给独立 Worker Agent 执行

Worker 有独立上下文，不会污染主 Engine 的对话。
完成任务后返回轻量标记，完整摘要可通过 read_worker_result 获取。
禁止嵌套 spawn（代码层拦截）。
"""

import os
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError

TOOL_NAME = "spawn_worker"
_WORKER_TIMEOUT = 110  # Worker 超时，低于 tool_executor 的 120s 上限

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
_WORKER_RESULTS: dict[str, str] = {}


def _extract_worker_result(history: list) -> str:
    """从 Worker 的 history 中提取最终回复作为结果摘要。"""
    for msg in reversed(history):
        role = msg.get("role", "")
        if role == "assistant":
            content = msg.get("content", "")
            if content and content.strip():
                return content.strip()
    return "(Worker 没有产生回复)"


def execute(instruction: str, name: str = "", context: str = "") -> str:
    """执行子任务并返回轻量标记，完整结果可通过 read_worker_result 获取。"""
    # ── 禁止嵌套 spawn ──
    if getattr(_worker_depth, "depth", 0) > 0:
        return (
            "[ERROR] 嵌套 spawn 被禁止：Worker 不能 spawn 子 Worker。\n"
            "请将子任务合并到当前 Worker 的指令中，或返回主 Agent 重新调度。"
        )

    try:
        # ── 加载依赖（确保在 tool context 内延迟导入） ──
        from core.llm_caller import create_llm_caller
        from core.provider import resolve_provider
        from core.engine import Engine
        from core.tool_executor import execute_tool
        from tools import TOOLS_SCHEMA

        # ── 解析当前 API 配置 ──
        config = resolve_provider()
        llm_caller = create_llm_caller(
            api_key=config["api_key"],
            api_url=config["base_url"],
            model_name=config["model"],
            tools_schema=TOOLS_SCHEMA,
        )

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
        )
        worker.system_prompt = worker_prompt

        # ── 设置嵌套检测标志 ──
        _worker_depth.depth = getattr(_worker_depth, "depth", 0) + 1

        # ── 在独立线程中运行 Worker ──
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(worker.run, worker_input)
            try:
                future.result(timeout=_WORKER_TIMEOUT)
            except TimeoutError:
                if hasattr(worker, "_interrupt_event") and worker._interrupt_event:
                    worker._interrupt_event.set()
                partial = _extract_worker_result(worker.history)
                return (
                    f"[WORKER_TIMEOUT] Worker 执行超过 {_WORKER_TIMEOUT}s。\n"
                    f"已完成部分:\n{partial}"
                )

        # ── 提取结果 ──
        result = _extract_worker_result(worker.history)
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
            _WORKER_RESULTS[name] = result

        # 返回轻量标记：有 name 时只带状态摘要，无 name 时返回全文
        if name:
            summary = result[:120].replace('\n', ' ').strip()
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
            "适用场景：需要长时间独立运行的任务、多文件大规模改动、独立研究。\n"
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
            },
            "required": ["instruction"],
        },
    },
}


# ── read_worker_result 工具 ──

READ_WORKER_TOOL_NAME = "read_worker_result"


def execute_read_worker_result(name: str) -> str:
    """获取指定名称的 Worker 的完整结果摘要。"""
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
