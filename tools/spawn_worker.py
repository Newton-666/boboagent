"""spawn_worker — 将子任务派给独立 Worker Agent 执行

Worker 有独立上下文，不会污染主 Engine 的对话。
完成任务后返回结果摘要。
禁止嵌套 spawn（代码层拦截）。
"""

import os
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError

TOOL_NAME = "spawn_worker"
_WORKER_TIMEOUT = 25  # Worker 超时，略低于 tool_executor 的 TOOL_TIMEOUT=30

# 线程局部变量：标记当前是否在 Worker 中运行
_worker_depth = threading.local()
_worker_depth.depth = 0


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
    """执行子任务并返回结果摘要。"""
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
        worker_prompt = (
            "你是 Bobo 的 Worker Agent。\n\n"
            "## 核心规则\n"
            "- 你的角色在指令中指定。完成指令后返回结果摘要。\n"
            "- **重要规则：单独的纯文字回复 = 任务结束。"
            "如果你还有工作要做，回复必须同时包含工具调用。不要只做'进度汇报'而不调工具。**\n"
            "- 如果工具调用失败，尝试替代方案。\n"
            "- 在完成任务之前，继续调用工具。不要提前停止。\n"
            "- **禁止调用 spawn_worker 工具（禁止嵌套）。**\n\n"
            "## 输出要求\n"
            "- 任务完成后，输出一段简洁的摘要，包含：做了什么、结果是什么、需注意的事项。\n"
            '- 不要输出"第X步完成"之类的进度汇报。\n'
        )

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
        return result

    except Exception as e:
        return f"[WORKER_ERROR] Worker 执行失败: {str(e)}"
    finally:
        _worker_depth.depth = max(0, getattr(_worker_depth, "depth", 0) - 1)


TOOL_FUNC = execute
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": (
            "将一个子任务派给独立的 Worker Agent 执行，完成后返回结果摘要。\n"
            "Worker 有独立的对话上下文，不会污染当前对话。\n"
            "适用场景：需要长时间独立运行的任务、多文件大规模改动、独立研究。\n"
            "不适用于：单步简单操作（直接调工具即可）。\n\n"
            "代码修改任务建议分三步：\n"
            "1. 先 spawn 大局分析 Worker（只读代码，输出方案）\n"
            "2. 再 spawn 修改 Worker（按方案执行，需要传入分析结果作为 context）\n"
            "3. 可复用大局 Worker 验证修改（传入 diff 作为 context）"
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
                        "可选。Worker 的名称，用于跟踪和调试。"
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


def register(reg):
    reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA)
