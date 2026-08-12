"""TICKET-ENG2 (b②): 测试基建并发后端硬约束 —— 同时存活真实后端 ≤2。

背景：2026-08-12 22:59 事故中 6 个 TUI 后端同一毫秒启动（僵尸前端集体重连风暴），
内存飙升触发 macOS jetsam 击杀活跃前端。测试侧同样有并发失控风险（多个 E2E/冒烟
同时 Popen 真实 gateway），本守卫统一收敛所有测试内的后端 spawn：

  - spawn_backend(): 起真实后端前检查存活数，≥ MAX（2）抛 BackendConcurrencyError
  - release_backend(): 退出/销毁时登记释放
  - shutdown_all(): 测试 session 结束时兜底清理（防测试残留僵尸后端）

用法（测试内）：
    from backend_guard import spawn_backend, release_backend
    proc = spawn_backend([sys.executable, "-m", "bobo_tui_gateway.entry"], env=...)
    ... 断言/交互 ...
    release_backend(proc)
"""

import subprocess
import threading

MAX_CONCURRENT_BACKENDS = 2


class BackendConcurrencyError(RuntimeError):
    """并发后端超限：测试试图起第 N（>2）个存活真实后端时抛出。"""


_lock = threading.Lock()
_alive: dict[int, subprocess.Popen] = {}


def _prune_dead() -> None:
    """清理已退出（poll() 非 None）的登记进程，释放名额。"""
    for pid in list(_alive):
        proc = _alive[pid]
        if proc.poll() is not None:
            del _alive[pid]


def alive_backend_count() -> int:
    """当前存活的真实后端进程数。"""
    with _lock:
        _prune_dead()
        return len(_alive)


def spawn_backend(cmd: list[str], **kwargs) -> subprocess.Popen:
    """起一个真实后端，遵守并发 ≤2 硬约束。

    Raises:
        BackendConcurrencyError: 存活后端已达上限（含本次请求即 >2）。
    """
    with _lock:
        _prune_dead()
        if len(_alive) >= MAX_CONCURRENT_BACKENDS:
            pids = sorted(_alive.keys())
            raise BackendConcurrencyError(
                f"ENG-2b② 并发后端超限：当前存活 {len(_alive)} 个 "
                f"(pid={pids}) ≥ 上限 {MAX_CONCURRENT_BACKENDS} —— "
                "施工纪律：E2E/冒烟起真实后端并发 ≤2，先 release 再起"
            )
        proc = subprocess.Popen(cmd, **kwargs)
        _alive[proc.pid] = proc
        return proc


def release_backend(proc: subprocess.Popen | None) -> None:
    """终止并释放一个后端进程。进程可能已被外部杀死，幂等。"""
    if proc is None:
        return
    with _lock:
        _alive.pop(proc.pid, None)
    if proc.poll() is None:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except (subprocess.TimeoutExpired, OSError):
            try:
                proc.kill()
            except OSError:
                pass


def shutdown_all() -> int:
    """终止全部存活后端，返回清理数量。测试 session 结束兜底调用。"""
    with _lock:
        procs = list(_alive.values())
        _alive.clear()
    n = 0
    for proc in procs:
        if proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except (subprocess.TimeoutExpired, OSError):
                try:
                    proc.kill()
                except OSError:
                    pass
            n += 1
    return n
