"""
core/tool_executor.py - 工具执行器（带超时保护 + 错误分类 + 参数校验 + 执行统计）
"""

import json
from config import BOBO_DATA_DIR
import os
import threading
import time
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from tools import TOOL_FUNCTIONS

TOOL_TIMEOUT = 30

# ── 审计日志：记录每次工具调用（数据访问透明度 Layer 1）────────────
_ACCESS_LOG = str(BOBO_DATA_DIR / "access_log.jsonl")
_AUDIT_LOCK = threading.Lock()

# 审计日志不记录的工具（纯计算零数据访问 + 审计日志自己）
_SKIP_AUDIT = frozenset({"get_current_time", "save_memory", "search_memory",
                          "load_result", "bobo_config"})

def _log_access(tool_name: str, args: dict, result: str, duration: float):
    """追加一行 JSONL 到 {BOBO_DATA_DIR}/access_log.jsonl（异步轻量，<1ms）。"""
    try:
        os.makedirs(os.path.dirname(_ACCESS_LOG) or ".", exist_ok=True)
        summary = {k: str(v)[:80] for k, v in args.items()} if args else {}
        entry = {
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "tool": tool_name,
            "args": summary,
            "size": len(result),
            "duration_ms": int(duration * 1000),
        }
        line = json.dumps(entry, ensure_ascii=False) + "\n"
        with _AUDIT_LOCK:
            with open(_ACCESS_LOG, "a", encoding="utf-8") as f:
                f.write(line)
    except Exception:
        pass  # 审计日志写入失败不影响工具执行

# 审计 #11 + 脆弱链 2：不再使用全局共享线程池。每个工具调用创建独立的
# 1-worker executor，shutdown(wait=False)。一个工具卡死不会占用槽位影响
# 其他工具——下一个调用获得全新的 executor。
# 代价：无法限制并发线程总数。实际场景中并行工具数由 LLM 的一次调用中
# 的 tool_calls 数量自然限制（通常 ≤10），风险可控。
_STUCK_WARN_THRESHOLD = 20  # 累计超过此阈值时日志警告

# 命令结果缓存：key=(tool_name, args[:200]) → (timestamp, result)
_COMMAND_CACHE: dict[tuple[str, str], tuple[float, str]] = {}
_COMMAND_CACHE_LOCK = threading.Lock()
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

    # 命令缓存：只缓存纯读工具（execute_terminal 有副作用，不缓存；审计 #18）
    if tool_name in ("git_status", "grep_code", "search_code"):
        arg_key = str(arguments)[:200]
        cache_key = (tool_name, arg_key)
        cached = None
        with _COMMAND_CACHE_LOCK:
            hit = _COMMAND_CACHE.get(cache_key)
            if hit and time.time() - hit[0] < _CACHE_TTL:
                cached = hit
        if cached:
            return f"{cached[1]}\\n（缓存结果，{_CACHE_TTL}s 内有效）"

    try:
        func = TOOL_FUNCTIONS[tool_name]
        # 每个工具独立 executor——一个卡死不占全局槽，不影响其他工具（脆弱链 2）
        executor = ThreadPoolExecutor(max_workers=1)
        try:
            future = executor.submit(func, **arguments)
            # spawn_worker 需要更长的超时时间（含重试），execute_terminal 次之
            _timeout_map = {"spawn_worker": 310, "execute_terminal": 120}
            timeout = _timeout_map.get(tool_name, TOOL_TIMEOUT)
            result = future.result(timeout=timeout)
            duration = time.time() - start_time
            output = str(result) if result else "执行成功"
            # 写入缓存（只缓存读工具；审计 #18）
            if tool_name in ("git_status", "grep_code", "search_code"):
                arg_key = str(arguments)[:200]
                with _COMMAND_CACHE_LOCK:
                    _COMMAND_CACHE[(tool_name, arg_key)] = (time.time(), output)
                    # 限制缓存大小
                    if len(_COMMAND_CACHE) > 50:
                        old_keys = sorted(_COMMAND_CACHE.keys(), key=lambda k: _COMMAND_CACHE[k][0])[:20]
                        for k in old_keys:
                            _COMMAND_CACHE.pop(k, None)
            # 审计日志：旁路记录，不影响工具执行（<1ms）
            if tool_name not in _SKIP_AUDIT:
                _log_access(tool_name, arguments, output, duration)
            return f"{output}（耗时: {duration:.1f}s）"
        finally:
            executor.shutdown(wait=False)  # 不等待卡死的线程
    except TimeoutError:
        duration = time.time() - start_time
        return f"工具 '{tool_name}' 执行超过 {timeout}s（上限）。如果工具支持 timeout 参数，请指定更大值后重试（已等待 {duration:.1f}s）"
    except TypeError as e:
        return f"参数错误: {str(e)}"
    except ValueError as e:
        return f"参数错误: {str(e)}"
    except Exception as e:
        duration = time.time() - start_time
        return f"执行失败: {str(e)}（耗时: {duration:.1f}s）"
