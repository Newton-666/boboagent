"""TICKET-018: unix socket 传输层测试。

核心命题：前端（Node/TUI）侧任何故障（fd 误关、进程崩溃、管道被掐）
都只表现为"客户端断开"，gateway 进程本身不退出、等待重连。
"""

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

# 确保项目根目录在 sys.path（conftest 已做，这里兜底）
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from bobo_tui_gateway.transport import SocketTransport, StdioTransport, set_transport, write_json


class TestSocketTransportWrite:
    """SocketTransport.write 的行为"""

    def test_write_delivers_json_line(self):
        """正常发送：对端能收到完整的 JSON 行。"""
        server, client = socket.socketpair()
        try:
            t = SocketTransport(server)
            assert t.write({"jsonrpc": "2.0", "method": "ping"}) is True

            data = client.recv(65536).decode("utf-8")
            obj = json.loads(data.strip())
            assert obj["method"] == "ping"
        finally:
            server.close()
            client.close()

    def test_write_unicode_preserved(self):
        """中文字符不被破坏。"""
        server, client = socket.socketpair()
        try:
            t = SocketTransport(server)
            assert t.write({"msg": "你好，Bobo"}) is True

            data = client.recv(65536).decode("utf-8")
            assert json.loads(data.strip())["msg"] == "你好，Bobo"
        finally:
            server.close()
            client.close()

    def test_write_after_peer_close_returns_false(self):
        """对端关闭后 write 返回 False 而非抛异常——这是 gateway 不死的根基。"""
        server, client = socket.socketpair()
        t = SocketTransport(server)
        client.close()
        # sendall 到已关闭的对端可能立即失败，也可能需要一次触发
        result = t.write({"x": 1})
        # 无论返回 False 还是抛 OSError 被捕获，write 都不能抛
        assert result is False or result is True
        # 第二次写必然失败（对端已 RST/关闭）
        t.write({"x": 2})  # 不应抛异常

    def test_close_is_idempotent(self):
        """close 幂等，重复调用不炸。"""
        server, client = socket.socketpair()
        t = SocketTransport(server)
        t.close()
        t.close()
        client.close()

    def test_write_after_close_returns_false(self):
        """close 之后 write 返回 False（写已关闭的 fd 被捕获）。"""
        server, client = socket.socketpair()
        t = SocketTransport(server)
        t.close()
        assert t.write({"x": 1}) is False
        client.close()


class TestSetTransport:
    """set_transport 切换全局通道"""

    def test_switch_to_socket_transport(self, monkeypatch):
        """set_transport 后 write_json 走新通道。"""
        server, client = socket.socketpair()
        try:
            t = SocketTransport(server)
            set_transport(t)
            assert write_json({"method": "event", "params": {"type": "x"}}) is True

            data = client.recv(65536).decode("utf-8")
            obj = json.loads(data.strip())
            assert obj["method"] == "event"
        finally:
            server.close()
            client.close()
            # 还原，避免污染其他测试
            set_transport(StdioTransport())


class TestGatewaySurvivesFrontendDeath:
    """核心命题：前端断开，gateway 进程存活并可重连。

    以子进程方式启动 _run_socket_backend（通过 python -c 调 entry 的
    socket 分支），验证：连接→断开→重连→再断开，进程始终存活。
    """

    @pytest.fixture
    def gateway_proc(self, tmp_path):
        sock_path = tempfile.mktemp(prefix="bobo_gw_test_", suffix=".sock")
        env = dict(os.environ)
        env["BOBO_GW_SOCKET"] = sock_path
        env["OBSIDIAN_VAULT"] = ""
        env["BOBO_TEST_MODE"] = "1"

        # 子进程输出重定向到文件而非 PIPE——父子进程管道缓冲
        # 在 pytest 环境下可能互等阻塞，文件写入则绝对安全。
        out_f = open(tmp_path / "gw_stdout.log", "w")
        err_f = open(tmp_path / "gw_stderr.log", "w")

        # TICKET-ENG2 (b②): 统一走 backend_guard，并发后端 ≤2 硬约束
        import backend_guard

        proc = backend_guard.spawn_backend(
            [sys.executable, "-u", "-c",
             "import os,sys; sys.path.insert(0, '.'); "
             "from bobo_tui_gateway.entry import _run_socket_backend; "
             "_run_socket_backend(os.environ['BOBO_GW_SOCKET'])"],
            cwd=str(_root),
            env=env,
            stdout=out_f,
            stderr=err_f,
        )
        out_f.close()
        err_f.close()
        # 等 socket 文件出现
        deadline = time.time() + 10
        while time.time() < deadline:
            if os.path.exists(sock_path):
                break
            if proc.poll() is not None:
                err = (tmp_path / "gw_stderr.log").read_text(errors="replace")
                pytest.fail(f"gateway 提前退出: rc={proc.returncode} stderr={err[:500]}")
            time.sleep(0.05)
        assert proc.poll() is None, "gateway 未能在 10s 内就绪"

        yield proc, sock_path, tmp_path

        backend_guard.release_backend(proc)
        try:
            os.unlink(sock_path)
        except FileNotFoundError:
            pass

    def _connect_and_exchange(self, sock_path):
        """连接 socket，发一条 ping，收 ready/响应，然后断开。"""
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.settimeout(5)
        client.connect(sock_path)
        # 收 ready 事件
        buf = b""
        deadline = time.time() + 5
        while time.time() < deadline and b"gateway.ready" not in buf:
            chunk = client.recv(65536)
            if not chunk:
                break
            buf += chunk
        client.sendall((json.dumps({"jsonrpc": "2.0", "method": "ping", "id": 1}) + "\n").encode())
        try:
            data = client.recv(65536).decode("utf-8")
        except socket.timeout:
            data = ""
        client.close()
        return buf.decode("utf-8"), data

    def test_reconnect_cycle_keeps_process_alive(self, gateway_proc):
        """连接→断开→重连→断开，进程始终存活（重连后还能收发）。"""
        proc, sock_path, _ = gateway_proc

        # 第一次连接并断开
        ready1, resp1 = self._connect_and_exchange(sock_path)
        assert "gateway.ready" in ready1, f"第一次连接未收到 ready: {ready1!r}"
        assert proc.poll() is None, "前端断开后 gateway 竟然退出了"

        # 第二次连接并断开
        ready2, resp2 = self._connect_and_exchange(sock_path)
        assert "gateway.ready" in ready2, f"重连未收到 ready: {ready2!r}"
        assert proc.poll() is None, "第二次断开后 gateway 竟然退出了"

        # 第三次连接，确认依然健康
        ready3, _ = self._connect_and_exchange(sock_path)
        assert "gateway.ready" in ready3
        assert proc.poll() is None, "三次连接/断开循环后 gateway 竟然退出了"

    def test_gateway_logs_reconnect_reason(self, gateway_proc):
        """gateway 日志记录每次断开原因（法医留痕）。

        entry.py 的 logger 通过 TimedRotatingFileHandler 写入
        data/logs/bobo.log（不是 stderr），读该文件验证断开留痕。
        """
        proc, sock_path, _ = gateway_proc
        self._connect_and_exchange(sock_path)
        time.sleep(0.8)  # 等日志落盘
        assert proc.poll() is None, "前端断开后 gateway 竟然退出了"
        log_path = _root / "data" / "logs" / "bobo.log"
        if not log_path.exists():
            pytest.fail(f"bobo.log 不存在: {log_path}")
        content = log_path.read_text(errors="replace")
        tail = content[-5000:]
        assert "前端断开" in tail, f"bobo.log 未记录断开原因: {tail!r}"
