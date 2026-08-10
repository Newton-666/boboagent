"""票 AUTO-E2 E2-4：spawn_worker 长超时工具同样支持 ESC 硬中断。

验证：
  - 主引擎 interrupt_event set → Worker 在 2s 内被中断（interrupted=True）
  - worker._interrupt_event 通道被 set（Worker 内部正常收束）
  - 整体超时语义不破坏（timed_out=True 照旧）
  - 中断与超时语义分开（中断不触发重试分支）
"""

import threading
import time

from tools.spawn_worker import _run_worker_with_timeout


class _BlockingWorker:
    """run() 阻塞直到中断或放行——模拟长耗时 Worker（响应中断收束）。"""

    def __init__(self):
        self._interrupt_event = threading.Event()
        self._release = threading.Event()

    def run(self, _inp):
        # 模拟真实 Worker：收到 interrupt_event 后快速收束退出
        while not self._interrupt_event.is_set() and not self._release.is_set():
            time.sleep(0.05)
        return


class TestSpawnWorkerInterrupt:
    def test_interrupt_event_stops_worker_within_2s(self):
        """ESC 中断 → 2s 内中断 Worker，interrupted=True。"""
        w = _BlockingWorker()
        ev = threading.Event()

        def _delayed_set():
            time.sleep(0.3)
            ev.set()

        threading.Thread(target=_delayed_set, daemon=True).start()
        t0 = time.time()
        result, timed_out, interrupted = _run_worker_with_timeout(
            w, "x", timeout=30, interrupt_event=ev)
        elapsed = time.time() - t0

        assert interrupted is True, "中断应返回 interrupted=True"
        assert timed_out is False, "中断不是超时"
        assert elapsed < 2.0, f"ESC → Worker 中断应 ≤2s，实际 {elapsed:.2f}s"
        # worker 中断通道被 set（Worker 内部 engine 正常收束）
        assert w._interrupt_event.is_set()

    def test_timeout_semantics_unchanged(self):
        """整体超时语义保持：timed_out=True、interrupted=False。"""
        w = _BlockingWorker()
        result, timed_out, interrupted = _run_worker_with_timeout(
            w, "x", timeout=1, interrupt_event=None)

        assert timed_out is True
        assert interrupted is False
        assert w._interrupt_event.is_set()  # 超时也走 worker 中断通道

    def test_normal_completion_unaffected(self):
        """正常完成路径不变：interrupted=False、timed_out=False。"""
        w = _BlockingWorker()

        def _release():
            time.sleep(0.2)
            w._release.set()

        threading.Thread(target=_release, daemon=True).start()
        result, timed_out, interrupted = _run_worker_with_timeout(
            w, "x", timeout=5, interrupt_event=None)

        assert timed_out is False
        assert interrupted is False
