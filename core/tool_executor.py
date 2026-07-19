"""
core/tool_executor.py - 工具执行器（带超时保护 + 错误分类 + 参数校验 + 执行统计）
"""

import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from tools import TOOL_FUNCTIONS

TOOL_TIMEOUT = 30
_executor = ThreadPoolExecutor(max_workers=4)

# 命令结果缓存：key=(tool_name, args[:200]) → (timestamp, result)
_COMMAND_CACHE: dict[tuple[str, str], tuple[float, str]] = {}
_CACHE_TTL = 30  # 缓存有效期（秒）


def execute_tool(tool_name: str, arguments: dict) -> str:
    """执行工具"""
    if tool_name not in TOOL_FUNCTIONS:
        return f"错误: 未知工具 '{tool_name}'"

    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        return f"参数错误: 工具 '{tool_name}' 期望 dict 类型参数，收到 {type(arguments).__name__}"

    start_time = time.time()

    # 命令缓存：相同的工具+参数在 30s 内返回缓存结果
    if tool_name in ("execute_terminal", "git_status", "grep_code", "search_code"):
        arg_key = str(arguments)[:200]
        cache_key = (tool_name, arg_key)
        cached = _COMMAND_CACHE.get(cache_key)
        if cached and time.time() - cached[0] < _CACHE_TTL:
            return f"{cached[1]}\\n（缓存结果，{_CACHE_TTL}s 内有效）"

    try:
        func = TOOL_FUNCTIONS[tool_name]
        future = _executor.submit(func, **arguments)
        # spawn_worker 需要更长的超时时间（含重试），execute_terminal 次之
        _timeout_map = {"spawn_worker": 310, "execute_terminal": 120}
        timeout = _timeout_map.get(tool_name, TOOL_TIMEOUT)
        result = future.result(timeout=timeout)
        duration = time.time() - start_time
        output = str(result) if result else "执行成功"
        # 写入缓存
        if tool_name in ("execute_terminal", "git_status", "grep_code", "search_code"):
            arg_key = str(arguments)[:200]
            _COMMAND_CACHE[(tool_name, arg_key)] = (time.time(), output)
            # 限制缓存大小
            if len(_COMMAND_CACHE) > 50:
                old_keys = sorted(_COMMAND_CACHE.keys(), key=lambda k: _COMMAND_CACHE[k][0])[:20]
                for k in old_keys:
                    _COMMAND_CACHE.pop(k, None)
        return f"{output}（耗时: {duration:.1f}s）"
    except TimeoutError:
        duration = time.time() - start_time
        return f"工具 '{tool_name}' 执行超过 {TOOL_TIMEOUT}s（当前上限）。如果工具支持 timeout 参数，请指定更大值后重试（已等待 {duration:.1f}s）"
    except TypeError as e:
        return f"参数错误: {str(e)}"
    except ValueError as e:
        return f"参数错误: {str(e)}"
    except Exception as e:
        duration = time.time() - start_time
        return f"执行失败: {str(e)}（耗时: {duration:.1f}s）"
