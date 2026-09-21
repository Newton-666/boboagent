"""
core/tool_executor.py - 工具执行器（带超时保护 + 错误分类 + 参数校验 + 执行统计）
"""

import contextvars
import inspect
import json
from config import BOBO_DATA_DIR, TOOL_TIMEOUT
import os
import threading
import time
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from tools import TOOL_FUNCTIONS
from core.tool_lifecycle import (
    AnySetEvent,
    CANCEL_GRACE_S,
    ToolCallContext,
    acquire_path_lock,
    begin_write_slot,
    bind_context,
    clamp_inner_timeout,
    finish_write_slot,
    is_cancelled,
    is_success_result,
    mark_slot_timed_out,
    release_path_lock,
    reset_context,
    resolve_timeout,
    timeout_message,
    write_identity,
    write_path_key,
)

# 审计日志：记录每次工具调用（数据访问透明度 Layer 1）
_ACCESS_LOG = str(BOBO_DATA_DIR / "access_log.jsonl")
_AUDIT_LOCK = threading.Lock()

# 审计日志不记录的工具（纯计算零数据访问 + 审计日志自己）
_SKIP_AUDIT = frozenset({"get_current_time", "save_memory", "search_memory",
                          "load_result", "bobo_config"})

def _log_access(tool_name: str, args: dict, result: str, duration: float):
    """追加一行 JSONL 到 access_log.jsonl（异步轻量，<1ms）。
    自动检测隐私标签——如果读写的文件路径命中 privacy.toml 的标签，加入 tags 字段。
    """
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
        # Privacy tags: 检测所有 path-like 参数是否命中隐私标签
        try:
            from core.privacy import match_tags
            tags = set()
            for key in ("filepath", "path", "file_path", "filename", "url"):
                val = str(args.get(key, ""))
                if val and ("/" in val or val.startswith("~")):
                    tags.update(match_tags(val))
            if tags:
                entry["tags"] = sorted(tags)
        except Exception:
            pass
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
# GitHub #2：超时必须 set cancel + kill 已登记子进程；写槽在线程真正结束后才释放。
_STUCK_WARN_THRESHOLD = 20  # 累计超过此阈值时日志警告

# 命令结果缓存：key=(tool_name, args[:200]) → (timestamp, result)
_COMMAND_CACHE: dict[tuple[str, str], tuple[float, str]] = {}
_COMMAND_CACHE_LOCK = threading.Lock()
_CACHE_TTL = 30  # 缓存有效期（秒）


def _supported_kwargs(func, arguments: dict) -> dict:
    """只传目标函数签名里有的关键字，避免注入 _interrupt_event 等撑爆无关工具。"""
    try:
        sig = inspect.signature(func)
    except (TypeError, ValueError):
        return dict(arguments)
    if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
        return dict(arguments)
    allowed = {
        name for name, p in sig.parameters.items()
        if p.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
    }
    return {k: v for k, v in arguments.items() if k in allowed}


def _invoke_tool(func, exec_args: dict, identity: str | None, path_key: str | None,
                 ctx: ToolCallContext, lock_wait: float) -> str:
    """在 worker 线程跑工具：路径锁 + 取消检查 + 结束时释放写槽。"""
    path_lock = acquire_path_lock(path_key, ctx.cancel_event, timeout=lock_wait)
    if path_key and path_lock is None:
        msg = "错误: 操作已取消（超时）— 未能获得路径写锁"
        finish_write_slot(identity, msg, success=False)
        return msg
    result = None
    try:
        if is_cancelled() or ctx.cancel_event.is_set():
            result = "错误: 操作已取消（超时）"
            return result
        result = func(**_supported_kwargs(func, exec_args))
        return result
    finally:
        finish_write_slot(identity, str(result) if result is not None else None,
                          is_success_result(result))
        release_path_lock(path_lock)


def execute_tool(tool_name: str, arguments: dict, engine=None) -> str:
    """执行工具。engine 参数仅内部路由使用，不暴露给 LLM schema。"""
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
        timeout = resolve_timeout(tool_name, arguments)
        identity = write_identity(tool_name, arguments)
        path_key = write_path_key(tool_name, arguments)

        slot_status, slot_payload = begin_write_slot(identity)
        if slot_status == "inflight":
            return slot_payload
        if slot_status == "replay":
            return f"{slot_payload}（与超时前一次写入相同，已去重，未再次落地）"

        # 热修：注入前复制，禁止污染调用方字典本体（Engine 泄漏进 JSON 序列化会炸）
        exec_args = dict(arguments)
        if tool_name in ("task_ledger", "describe_tool") and "_engine" not in exec_args:
            exec_args["_engine"] = engine

        exec_args = clamp_inner_timeout(tool_name, exec_args, timeout)

        ctx = ToolCallContext(tool_name)
        existing_interrupt = exec_args.get("_interrupt_event")
        combined = AnySetEvent(existing_interrupt, ctx.cancel_event,
                               timeout_event=ctx.cancel_event)
        exec_args["_interrupt_event"] = combined

        token = bind_context(ctx)
        copied = contextvars.copy_context()
        # 每个工具独立 executor——一个卡死不占全局槽，不影响其他工具（脆弱链 2）
        executor = ThreadPoolExecutor(max_workers=1)
        future = None
        try:
            future = executor.submit(
                copied.run,
                _invoke_tool,
                func,
                exec_args,
                identity,
                path_key,
                ctx,
                float(timeout),
            )
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
        except TimeoutError:
            ctx.cancel_event.set()
            ctx.kill_procs()
            mark_slot_timed_out(identity)
            # 宽限：若内层在取消窗口内完成，返回真实结果，避免「已写入却报超时」诱使重试
            if future is not None:
                try:
                    result = future.result(timeout=CANCEL_GRACE_S)
                    duration = time.time() - start_time
                    output = str(result) if result else "执行成功"
                    if tool_name not in _SKIP_AUDIT:
                        _log_access(tool_name, arguments, output, duration)
                    return f"{output}（耗时: {duration:.1f}s）"
                except TimeoutError:
                    pass
                except Exception as inner_e:
                    duration = time.time() - start_time
                    return f"执行失败: {str(inner_e)}（耗时: {duration:.1f}s）"
            duration = time.time() - start_time
            return timeout_message(tool_name, timeout, duration)
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
            reset_context(token)
    except TypeError as e:
        finish_write_slot(write_identity(tool_name, arguments), None, success=False)
        return f"参数错误: {str(e)}"
    except ValueError as e:
        finish_write_slot(write_identity(tool_name, arguments), None, success=False)
        return f"参数错误: {str(e)}"
    except Exception as e:
        finish_write_slot(write_identity(tool_name, arguments), None, success=False)
        duration = time.time() - start_time
        return f"执行失败: {str(e)}（耗时: {duration:.1f}s）"
