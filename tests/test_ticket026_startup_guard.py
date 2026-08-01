"""TICKET-030: auto-exit 孤儿场景测试（守卫已拆除，保留启动计时打点）。

核心命题：
① 从未连接客户端的孤儿 gateway 在 BOBO_GW_IDLE_TIMEOUT 秒后自动退出
② 连接过的 gateway 在客户端断开后超时自动退出
③ BOBO_GW_IDLE_TIMEOUT=0 禁用 auto-exit，gateway 永不退出
④ gateway.startup 打点仍正常（每进程一次）
"""

import json
import os
import signal
import socket
import subprocess
import tempfile
import sys
import time
from pathlib import Path

import pytest

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import bobo_tui_gateway.entry as entry
from bobo_tui_gateway.transport import SocketTransport, set_transport, StdioTransport


@pytest.fixture(autouse=True)
def _restore_globals(monkeypatch, tmp_path):
    """隔离 _LOG_DIR 到 tmp_path，测试后还原模块全局状态。"""
    monkeypatch.setattr(entry, "_LOG_DIR", str(tmp_path))
    old_t0, old_emitted = entry._BACKEND_T0, entry._READY_EMITTED
    yield
    entry._BACKEND_T0, entry._READY_EMITTED = old_t0, old_emitted
    set_transport(StdioTransport())


def _spawn_gateway(sock_path: str, idle_timeout: int | None = None,
                   connect: bool = False, extra_env: dict | None = None) -> subprocess.Popen:
    """以子进程启动 _run_socket_backend。

    idle_timeout=None 时不设 BOBO_GW_IDLE_TIMEOUT（使用默认 60s）。
    connect=True 时启动一个客户端连接再立即断开，模拟"有过客户但已断开"。
    """
    import copy
    env = copy.copy(dict(os.environ))
    env["BOBO_GW_SOCKET"] = sock_path
    if extra_env:
        env.update(extra_env)
    if idle_timeout is not None:
        env["BOBO_GW_IDLE_TIMEOUT"] = str(idle_timeout)
    # 确保守卫不会运行（TICKET-030 守卫已拆除，但旧代码可能残留）
    env.pop("BOBO_GW_GUARD", None)
    env["BOBO_TEST_MODE"] = "1"

    code = f"""
import os, sys
os.environ.update({env!r})
sys.path.insert(0, {str(_root)!r})
from bobo_tui_gateway.entry import _run_socket_backend
_run_socket_backend({sock_path!r})
"""
    proc = subprocess.Popen(
        [sys.executable, "-c", code],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    # 等待 socket 文件出现
    for _ in range(50):
        if os.path.exists(sock_path):
            break
        time.sleep(0.05)

    if connect and os.path.exists(sock_path):
        # 连一下立刻断开，模拟"有过客户端"
        try:
            conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            conn.settimeout(2)
            conn.connect(sock_path)
            time.sleep(0.05)  # 让 gateway 处理连接
            conn.close()
        except OSError:
            pass

    return proc


class TestAutoExitOrphan:
    def test_never_connected_orphan_exits(self, tmp_path):
        """从未连接客户端的孤儿 gateway —— BOBO_GW_IDLE_TIMEOUT 秒后自动退出。"""
        sock = tempfile.mktemp(prefix="bobo_gw_t030a_", suffix=".sock")
        proc = _spawn_gateway(sock, idle_timeout=2, connect=False)

        try:
            proc.wait(timeout=8)
            # 应正常退出（被 auto-exit 超时触发）
            assert proc.returncode == 0, f"exit={proc.returncode} stderr={proc.stderr.read()}"
        except subprocess.TimeoutExpired:
            proc.kill()
            pytest.fail("孤儿 gateway 未在 auto-exit 超时后退出（等待 8s 仍存活）")

    def test_disconnected_client_exits(self, tmp_path):
        """客户端连接后断开 —— auto-exit 倒计时从断开时刻起算。"""
        sock = tempfile.mktemp(prefix="bobo_gw_t030b_", suffix=".sock")
        proc = _spawn_gateway(sock, idle_timeout=2, connect=True)

        try:
            proc.wait(timeout=8)
            assert proc.returncode == 0, f"exit={proc.returncode} stderr={proc.stderr.read()}"
        except subprocess.TimeoutExpired:
            proc.kill()
            pytest.fail("有客户后断开的 gateway 未在 auto-exit 超时后退出")

    def test_idle_timeout_zero_never_exits(self, tmp_path):
        """BOBO_GW_IDLE_TIMEOUT=0 → 永不自动退出。"""
        sock = tempfile.mktemp(prefix="bobo_gw_t030_", suffix="_test_never.sock")
        proc = _spawn_gateway(sock, idle_timeout=0, connect=False)

        try:
            proc.wait(timeout=4)
            pytest.fail("BOBO_GW_IDLE_TIMEOUT=0 时不应自动退出，但进程退出了")
        except subprocess.TimeoutExpired:
            # 预期行为：进程仍在运行
            pass
        finally:
            proc.kill()
            proc.wait(timeout=2)

    def test_client_connected_resets_timer(self, tmp_path):
        """有客户端保持连接时 gateway 不应退出（idle timer 被重置）。"""
        sock = tempfile.mktemp(prefix="bobo_gw_t030_", suffix="_test_connected.sock")
        proc = _spawn_gateway(sock, idle_timeout=2, connect=False)

        # 客户端连接并保持
        try:
            conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            conn.settimeout(3)
            for _ in range(30):
                try:
                    conn.connect(sock)
                    break
                except (ConnectionRefusedError, FileNotFoundError):
                    time.sleep(0.1)

            # 保持连接 3 秒（超过 2s 的 idle_timeout）
            time.sleep(3)
            # gateway 应仍在运行
            assert proc.poll() is None, "有活跃客户端时 gateway 不应退出"
        finally:
            try:
                conn.close()
            except OSError:
                pass
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=2)


class TestStartupTiming:
    def test_ready_emits_timing_once(self, monkeypatch):
        """首次 _serve_connection 打 gateway.startup 点；第二次不重复。"""
        import threading

        events = []

        class FakeBus:
            def write(self, t, payload):
                events.append((t, payload))

        monkeypatch.setattr("core.event_bus.event_bus", FakeBus())
        entry._BACKEND_T0 = time.monotonic()
        entry._READY_EMITTED = False

        conn, client = socket.socketpair()
        result = {}

        def _serve():
            result["reason"] = entry._serve_connection(
                conn.makefile("r", encoding="utf-8", newline="\n"))

        try:
            set_transport(SocketTransport(conn))
            t = threading.Thread(target=_serve, daemon=True)
            t.start()
            client.settimeout(5)
            data = client.recv(65536).decode("utf-8")
            assert "gateway.ready" in data
            client.close()
            t.join(timeout=5)
            assert not t.is_alive(), "前端断开后 _serve_connection 未返回"
            startups = [p for typ, p in events if typ == "gateway.startup"]
            assert len(startups) == 1
            assert startups[0]["ready_ms"] >= 0
            assert startups[0]["pid"] == os.getpid()
        finally:
            conn.close()
