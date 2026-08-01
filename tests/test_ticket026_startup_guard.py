"""TICKET-026: 单实例守卫 + 启动计时打点。

核心命题：① 残留 gateway 实例被自动清理，新实例不再叠罗汉；
② ready 打点进日志/事件，启动快慢从此有据可查。
"""

import json
import os
import signal
import socket
import subprocess
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
    """隔离 pidfile 到 tmp_path，测试后还原模块全局状态。"""
    monkeypatch.setattr(entry, "_LOG_DIR", str(tmp_path))
    old_t0, old_emitted = entry._BACKEND_T0, entry._READY_EMITTED
    yield
    entry._BACKEND_T0, entry._READY_EMITTED = old_t0, old_emitted
    set_transport(StdioTransport())


def _spawn_sleeper():
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])


def _spawn_dead():
    """立刻退出的进程，用于构造"已死 pid"。"""
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    return p


class TestSingleInstanceGuard:
    def test_kills_stale_instance(self, monkeypatch):
        """pidfile 指向存活的旧实例 + 授权旗标 → SIGTERM 清理，写自己 pid。"""
        monkeypatch.setenv("BOBO_GW_GUARD", "1")
        monkeypatch.delenv("BOBO_TEST_MODE", raising=False)
        monkeypatch.delenv("BOBO_GW_ALLOW_MULTI", raising=False)
        sleeper = _spawn_sleeper()
        try:
            pidfile = Path(entry._LOG_DIR) / "gateway.pid"
            pidfile.write_text(str(sleeper.pid))
            entry._single_instance_guard()
            # 回收子进程（不 wait 会是僵尸，os.kill(pid,0) 仍判活）
            try:
                sleeper.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pytest.fail("残留实例未被清理（5s 内未退出）")
            assert not entry._pid_alive(sleeper.pid)
            assert pidfile.read_text().strip() == str(os.getpid())
        finally:
            if entry._pid_alive(sleeper.pid):
                sleeper.kill()

    def test_skips_without_guard_flag(self, monkeypatch):
        """TICKET-028 金标准：无 BOBO_GW_GUARD=1 → 不动任何实例。

        误杀案复现：隔壁测试/基准起的野子进程，绝不允许触发守卫。
        """
        monkeypatch.delenv("BOBO_GW_GUARD", raising=False)
        monkeypatch.delenv("BOBO_TEST_MODE", raising=False)
        monkeypatch.delenv("BOBO_GW_ALLOW_MULTI", raising=False)
        sleeper = _spawn_sleeper()
        try:
            Path(entry._LOG_DIR, "gateway.pid").write_text(str(sleeper.pid))
            entry._single_instance_guard()
            assert entry._pid_alive(sleeper.pid), "无授权旗标时不得清理任何实例"
            # pidfile 也不应被覆写
            assert Path(entry._LOG_DIR, "gateway.pid").read_text().strip() == str(sleeper.pid)
        finally:
            sleeper.kill()

    def test_skips_when_test_mode(self, monkeypatch):
        """BOBO_TEST_MODE=1 → 不动残留实例（测试场景多实例合法）。"""
        monkeypatch.setenv("BOBO_GW_GUARD", "1")
        monkeypatch.setenv("BOBO_TEST_MODE", "1")
        sleeper = _spawn_sleeper()
        try:
            Path(entry._LOG_DIR, "gateway.pid").write_text(str(sleeper.pid))
            entry._single_instance_guard()
            assert entry._pid_alive(sleeper.pid), "测试模式下不应清理实例"
        finally:
            sleeper.kill()

    def test_stale_pidfile_dead_pid_noop(self, monkeypatch):
        """pidfile 指向已死 pid → 不炸，直接覆盖写自己。"""
        monkeypatch.setenv("BOBO_GW_GUARD", "1")
        monkeypatch.delenv("BOBO_TEST_MODE", raising=False)
        dead = _spawn_dead()
        Path(entry._LOG_DIR, "gateway.pid").write_text(str(dead.pid))
        entry._single_instance_guard()
        assert Path(entry._LOG_DIR, "gateway.pid").read_text().strip() == str(os.getpid())

    def test_pid_alive_semantics(self):
        assert entry._pid_alive(os.getpid()) is True
        dead = _spawn_dead()
        assert entry._pid_alive(dead.pid) is False


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
            # 与真实代码同构：读写同一条连接
            result["reason"] = entry._serve_connection(
                conn.makefile("r", encoding="utf-8", newline="\n"))

        try:
            set_transport(SocketTransport(conn))
            t = threading.Thread(target=_serve, daemon=True)
            t.start()
            # 前端收 ready 帧（transport 与 reader 同连接，write 不会假阻塞）
            client.settimeout(5)
            data = client.recv(65536).decode("utf-8")
            assert "gateway.ready" in data
            # 前端断开（真实 FIN，因为 client 没有 makefile 占着 fd）
            client.close()
            t.join(timeout=5)
            assert not t.is_alive(), "前端断开后 _serve_connection 未返回"
            startups = [p for typ, p in events if typ == "gateway.startup"]
            assert len(startups) == 1
            assert startups[0]["ready_ms"] >= 0
            assert startups[0]["pid"] == os.getpid()
        finally:
            conn.close()
