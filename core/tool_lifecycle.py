"""工具调用生命周期：统一超时、超时取消、写路径互斥/幂等。

圈 1.5 / P0（GitHub #2）：
- ThreadPoolExecutor.future.result(timeout) 不会取消内层线程/子进程。
- 超时文案曾引导「加大 timeout 重试」，写路径可二次落地。
- config.TOOL_TIMEOUT 曾是死配置（executor 另写 30）。

本模块是超时与写槽的单一事实源。tool_executor 负责接线；
写工具/终端在关键点查询 is_cancelled() 并登记子进程，便于外层超时杀组。
"""

from __future__ import annotations

import contextvars
import hashlib
import json
import os
import signal
import threading
import time
from dataclasses import dataclass, field

# ── 超时：config.TOOL_TIMEOUT 为通用默认；长任务保留专用上限 ──
# execute_terminal 外层 120s：内层默认 30s，LLM 可经 timeout 参数上调，封顶 outer-1。
# spawn_worker 外层 310s：覆盖首次 110s + 重试 300s 的预算。
TOOL_TIMEOUT_OVERRIDES = {
    "spawn_worker": 310,
    "execute_terminal": 120,
}

# 超时后给协作取消 / killpg 的收束窗口。超时内已完成则返回真实结果，避免「已写入却报超时」诱使重试。
CANCEL_GRACE_S = 2.0

# 仅对「超时后仍跑完」的成功写做短 TTL 回放，正常成功路径不缓存（避免挡住有意的二次同参写入）。
_REPLAY_TTL_S = 120.0

WRITE_TOOLS = frozenset({
    "edit_file",
    "file_operation",
    "file_writer",
    "write_obsidian",
    "append_obsidian",
    "delete_file",
    "refactor",
})

# 有副作用、超时重试危险的工具（含终端命令）。
SIDE_EFFECT_TOOLS = WRITE_TOOLS | frozenset({"execute_terminal", "spawn_worker"})

_READ_FILE_OPS = frozenset({"read", "exists"})

_INFLIGHT_REJECT = (
    "错误: 相同写操作仍在执行（上次调用已超时但内层尚未结束）。"
    "请勿用相同参数重试，等待前一次完成或取消后再决定。"
)

_call_ctx: contextvars.ContextVar[ToolCallContext | None] = contextvars.ContextVar(
    "tool_call_ctx", default=None
)

_slots_lock = threading.Lock()
_slots: dict[str, "_WriteSlot"] = {}
_path_locks_guard = threading.Lock()
_path_locks: dict[str, threading.Lock] = {}


def resolve_timeout(tool_name: str, arguments: dict | None = None) -> int:
    """返回该工具的外层超时秒数。通用工具走 config.TOOL_TIMEOUT。"""
    override = TOOL_TIMEOUT_OVERRIDES.get(tool_name)
    if override is not None:
        return int(override)
    import config
    return int(getattr(config, "TOOL_TIMEOUT", 20))


class AnySetEvent:
    """只读 OR：任一底层 Event.set 则 is_set()。set() 只打到 timeout 侧，不污染引擎 ESC。"""

    def __init__(self, *events, timeout_event=None):
        self._events = [e for e in events if e is not None]
        self._timeout_event = timeout_event

    def is_set(self) -> bool:
        return any(e.is_set() for e in self._events)

    def set(self) -> None:
        if self._timeout_event is not None:
            self._timeout_event.set()


class ToolCallContext:
    """单次 execute_tool 调用的取消令牌 + 子进程登记。"""

    def __init__(self, tool_name: str):
        self.tool_name = tool_name
        self.cancel_event = threading.Event()
        self._procs: list = []
        self._lock = threading.Lock()

    def register_proc(self, proc) -> None:
        with self._lock:
            self._procs.append(proc)

    def kill_procs(self) -> None:
        with self._lock:
            procs = list(self._procs)
        for proc in procs:
            _kill_process_group(proc)


def current_context() -> ToolCallContext | None:
    return _call_ctx.get()


def bind_context(ctx: ToolCallContext):
    return _call_ctx.set(ctx)


def reset_context(token) -> None:
    try:
        _call_ctx.reset(token)
    except Exception:
        pass


def is_cancelled() -> bool:
    ctx = _call_ctx.get()
    return bool(ctx is not None and ctx.cancel_event.is_set())


def register_current_proc(proc) -> None:
    ctx = _call_ctx.get()
    if ctx is not None:
        ctx.register_proc(proc)


def _kill_process_group(proc) -> None:
    """外层超时杀组：TERM → 短等 → KILL。长宽限留给工具自己的 _kill_process_group。"""
    if proc is None:
        return
    pid = getattr(proc, "pid", None)
    if not pid:
        return
    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            proc.terminate()
        except Exception:
            pass
    try:
        proc.wait(timeout=0.3)
        return
    except Exception:
        pass
    try:
        os.killpg(os.getpgid(pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            proc.kill()
        except Exception:
            pass
    try:
        proc.wait(timeout=0.5)
    except Exception:
        pass


@dataclass
class _WriteSlot:
    status: str = "inflight"  # inflight | done
    timed_out: bool = False
    success: bool = False
    result: str | None = None
    expires: float = 0.0
    started: float = field(default_factory=time.time)


def _canonical_path(path: str | None) -> str:
    if not path:
        return ""
    try:
        return os.path.realpath(os.path.expanduser(str(path)))
    except Exception:
        return str(path)


def _fingerprint(obj) -> str:
    try:
        blob = json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str)
    except Exception:
        blob = repr(obj)
    return hashlib.sha256(blob.encode("utf-8", errors="replace")).hexdigest()[:16]


def _public_args(arguments: dict | None) -> dict:
    if not arguments:
        return {}
    return {
        k: v for k, v in arguments.items()
        if not str(k).startswith("_") and k != "timeout"
    }


def write_identity(tool_name: str, arguments: dict | None) -> str | None:
    """副作用工具的幂等键。读操作返回 None（不占写槽）。"""
    if tool_name not in SIDE_EFFECT_TOOLS:
        return None
    args = arguments or {}
    if tool_name == "file_operation":
        action = str(args.get("action", "")).strip()
        if action in _READ_FILE_OPS or not action:
            return None
        if action == "batch_write":
            files = args.get("files") or []
            payload = [
                (_canonical_path(f.get("path")) if isinstance(f, dict) else "",
                 (f.get("content") if isinstance(f, dict) else f))
                for f in files
            ]
            return f"{tool_name}|batch_write|{_fingerprint(payload)}"
        return f"{tool_name}|{action}|{_canonical_path(args.get('path'))}|{_fingerprint(args.get('content'))}"
    path = (
        args.get("path")
        or args.get("file_path")
        or args.get("filepath")
        or args.get("filename")
        or ""
    )
    if tool_name == "execute_terminal":
        return f"{tool_name}|{_fingerprint(args.get('command'))}"
    if tool_name == "spawn_worker":
        return f"{tool_name}|{_fingerprint(_public_args(args))}"
    if tool_name == "edit_file":
        return (
            f"{tool_name}|{_canonical_path(path)}|"
            f"{_fingerprint((args.get('old_string'), args.get('new_string')))}"
        )
    return f"{tool_name}|{_canonical_path(path)}|{_fingerprint(_public_args(args))}"


def write_path_key(tool_name: str, arguments: dict | None) -> str | None:
    """同路径写串行化键。终端/无路径工具返回 None。"""
    if tool_name not in WRITE_TOOLS:
        return None
    args = arguments or {}
    if tool_name == "file_operation" and str(args.get("action", "")).strip() in _READ_FILE_OPS:
        return None
    if tool_name == "file_operation" and str(args.get("action", "")).strip() == "batch_write":
        files = args.get("files") or []
        paths = sorted({
            _canonical_path(f.get("path"))
            for f in files if isinstance(f, dict) and f.get("path")
        })
        return "|".join(p for p in paths if p) or None
    path = (
        args.get("path")
        or args.get("file_path")
        or args.get("filepath")
        or args.get("filename")
        or ""
    )
    canon = _canonical_path(path)
    return canon or None


def _get_path_lock(path_key: str) -> threading.Lock:
    with _path_locks_guard:
        lock = _path_locks.get(path_key)
        if lock is None:
            lock = threading.Lock()
            _path_locks[path_key] = lock
        return lock


def acquire_path_lock(path_key: str | None, cancel_event: threading.Event | None,
                      timeout: float = 30.0) -> threading.Lock | None:
    """可取消地获取路径锁。超时/取消返回 None（调用方应放弃写入）。"""
    if not path_key:
        return None
    lock = _get_path_lock(path_key)
    deadline = time.time() + max(0.1, timeout)
    while True:
        if cancel_event is not None and cancel_event.is_set():
            return None
        if lock.acquire(timeout=0.1):
            return lock
        if time.time() >= deadline:
            return None


def release_path_lock(lock: threading.Lock | None) -> None:
    if lock is None:
        return
    try:
        lock.release()
    except RuntimeError:
        pass


def begin_write_slot(identity: str | None) -> tuple[str, str | None]:
    """('run', None) | ('inflight', msg) | ('replay', cached_result)。"""
    if not identity:
        return "run", None
    now = time.time()
    with _slots_lock:
        slot = _slots.get(identity)
        if slot is None:
            _slots[identity] = _WriteSlot()
            return "run", None
        if slot.status == "inflight":
            return "inflight", _INFLIGHT_REJECT
        if slot.status == "done" and slot.success and slot.expires > now:
            cached = slot.result if slot.result is not None else "执行成功（与超时前一次写入相同，已去重）"
            return "replay", cached
        _slots[identity] = _WriteSlot()
        return "run", None


def mark_slot_timed_out(identity: str | None) -> None:
    if not identity:
        return
    with _slots_lock:
        slot = _slots.get(identity)
        if slot is not None and slot.status == "inflight":
            slot.timed_out = True


def finish_write_slot(identity: str | None, result: str | None, success: bool) -> None:
    if not identity:
        return
    with _slots_lock:
        slot = _slots.get(identity)
        if slot is None:
            return
        if slot.timed_out and success:
            slot.status = "done"
            slot.success = True
            slot.result = result
            slot.expires = time.time() + _REPLAY_TTL_S
            return
        # 正常完成或失败：释放槽，允许后续同参写入
        _slots.pop(identity, None)


def is_success_result(result) -> bool:
    if result is None:
        return False
    text = str(result).lstrip()
    if not text:
        return False
    if text.startswith(("错误", "❌", "⛔", "执行失败")):
        return False
    head = text[:200]
    if "已取消" in head:
        return False
    if ("超过" in head or "超时" in head) and ("已终止" in head or "上限" in head):
        return False
    return True


def timeout_message(tool_name: str, timeout: int, duration: float) -> str:
    if tool_name in SIDE_EFFECT_TOOLS:
        return (
            f"工具 '{tool_name}' 执行超过 {timeout}s，已发出取消并尝试终止内层工作。"
            f"请勿用相同参数立即重试——前一次副作用仍可能在收束，重复提交会被拒绝或去重。"
            f"（已等待 {duration:.1f}s）"
        )
    return (
        f"工具 '{tool_name}' 执行超过 {timeout}s（上限 {timeout}s，来自 TOOL_TIMEOUT/"
        f"每工具上限）。已取消内层执行。（已等待 {duration:.1f}s）"
    )


def clamp_inner_timeout(tool_name: str, arguments: dict, outer: int) -> dict:
    """把工具自带 timeout 参数封顶到 outer-1，让内层先杀子进程，外层作兜底。"""
    args = dict(arguments)
    if tool_name not in ("execute_terminal", "spawn_worker"):
        return args
    try:
        outer_i = int(outer)
    except (TypeError, ValueError):
        return args
    inner_cap = max(1, outer_i - 1) if outer_i > 1 else 1
    current = args.get("timeout")
    if current is None:
        if tool_name == "execute_terminal":
            args["timeout"] = min(30, inner_cap)
        return args
    try:
        args["timeout"] = min(int(current), inner_cap)
    except (TypeError, ValueError):
        args["timeout"] = inner_cap
    return args


def reset_for_tests() -> None:
    """测试间清空写槽。路径锁可能仍被卡住的测试线程持有，仅清登记表。"""
    with _slots_lock:
        _slots.clear()
    ctx = _call_ctx.get()
    if ctx is not None:
        ctx.cancel_event.set()
        ctx.kill_procs()
