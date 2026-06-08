"""
core/tool_executor.py - 工具执行器（带超时保护 + 错误分类 + 参数校验 + 执行统计）
"""

import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from tools import TOOL_FUNCTIONS

TOOL_TIMEOUT = 30
_executor = ThreadPoolExecutor(max_workers=4)


def execute_tool(tool_name: str, arguments: dict) -> str:
    """执行工具"""
    if tool_name not in TOOL_FUNCTIONS:
        return f"错误: 未知工具 '{tool_name}'"

    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        return f"参数错误: 工具 '{tool_name}' 期望 dict 类型参数，收到 {type(arguments).__name__}"

    start_time = time.time()

    try:
        func = TOOL_FUNCTIONS[tool_name]
        future = _executor.submit(func, **arguments)
        result = future.result(timeout=TOOL_TIMEOUT)
        duration = time.time() - start_time
        output = str(result) if result else "执行成功"
        return f"{output}（耗时: {duration:.1f}s）"
    except TimeoutError:
        duration = time.time() - start_time
        return f"错误: 工具 '{tool_name}' 执行超时（{TOOL_TIMEOUT}秒，已等待 {duration:.1f}s）"
    except TypeError as e:
        return f"参数错误: {str(e)}"
    except ValueError as e:
        return f"参数错误: {str(e)}"
    except Exception as e:
        duration = time.time() - start_time
        return f"执行失败: {str(e)}（耗时: {duration:.1f}s）"
