"""TICKET-ENG2 (b②) 硬约束验收：测试基建并发后端 ≤2。

验收 3：试图起第 3 个并发后端时报错（BackendConcurrencyError）。
验证：guard 计数 / 上限拒绝 / release 后名额释放 / shutdown_all 兜底清理。
"""

import subprocess
import sys

import pytest

import backend_guard


def _dummy_backend_cmd():
    """轻量"后端"：sleep 进程即可（guard 只关心进程存活数，不关心真 gateway）。"""
    return [sys.executable, "-c", "import time; time.sleep(30)"]


def test_guard_allows_up_to_two():
    """允许起 2 个并发后端。"""
    procs = []
    try:
        p1 = backend_guard.spawn_backend(_dummy_backend_cmd())
        p2 = backend_guard.spawn_backend(_dummy_backend_cmd())
        procs = [p1, p2]
        assert backend_guard.alive_backend_count() == 2
    finally:
        for p in procs:
            backend_guard.release_backend(p)
    assert backend_guard.alive_backend_count() == 0


def test_guard_rejects_third():
    """第 3 个并发后端必须报错（ENG-2b② 硬约束）。"""
    procs = []
    try:
        procs.append(backend_guard.spawn_backend(_dummy_backend_cmd()))
        procs.append(backend_guard.spawn_backend(_dummy_backend_cmd()))
        with pytest.raises(backend_guard.BackendConcurrencyError) as excinfo:
            backend_guard.spawn_backend(_dummy_backend_cmd())
        assert "ENG-2b②" in str(excinfo.value)
        assert "并发后端超限" in str(excinfo.value)
    finally:
        for p in procs:
            backend_guard.release_backend(p)


def test_release_frees_slot():
    """release 一个后端后名额释放，可再起。"""
    p1 = backend_guard.spawn_backend(_dummy_backend_cmd())
    backend_guard.release_backend(p1)
    assert backend_guard.alive_backend_count() == 0
    p2 = backend_guard.spawn_backend(_dummy_backend_cmd())
    backend_guard.release_backend(p2)


def test_shutdown_all_cleans_leaked():
    """shutdown_all 兜底清理登记中的存活后端（含未 release 的泄漏）。"""
    p1 = backend_guard.spawn_backend(_dummy_backend_cmd())
    p2 = backend_guard.spawn_backend(_dummy_backend_cmd())
    n = backend_guard.shutdown_all()
    assert n == 2
    assert backend_guard.alive_backend_count() == 0
    # 进程确实已死
    assert p1.poll() is not None
    assert p2.poll() is not None
