"""Transport - JSON-RPC 通信层（从 Hermes 精简）"""

from __future__ import annotations

import errno
import json
import logging
import os
import sys
import threading
from typing import Any, Callable

logger = logging.getLogger(__name__)

_PEER_GONE_ERRNOS = frozenset({
    errno.EPIPE,
    errno.ECONNRESET,
    errno.EBADF,
    errno.ESHUTDOWN,
})


class StdioTransport:
    """通过 stdin/stdout 与 TUI 前端通信"""

    def __init__(self):
        self._lock = threading.Lock()

    def write(self, obj: dict) -> bool:
        line = json.dumps(obj, ensure_ascii=False) + "\n"
        with self._lock:
            try:
                sys.stdout.write(line)
                sys.stdout.flush()
            except (BrokenPipeError, OSError):
                return False
            except ValueError:
                return False
        return True

    def close(self):
        pass


class SocketTransport:
    """通过 unix socket 与 TUI 前端通信（TICKET-018）

    与 StdioTransport 的关键区别：socket 由 **python 自己** bind/listen，
    前端（Node）只是连接方。前端侧任何 fd 故障（原生层误关、进程崩溃）
    都只会表现为"客户端断开"，gateway 进程本身不受牵连，等待重连即可。
    """

    def __init__(self, conn):
        self._conn = conn
        self._lock = threading.Lock()

    def write(self, obj: dict) -> bool:
        line = (json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")
        with self._lock:
            try:
                self._conn.sendall(line)
            except OSError:
                return False
        return True

    def close(self):
        try:
            self._conn.close()
        except OSError:
            pass


# 全局传输实例（socket 模式下由 set_transport 替换）
_stdio_transport = StdioTransport()
_active_transport = _stdio_transport


def set_transport(transport) -> None:
    """切换当前生效的传输通道（socket 模式每次接受新连接时调用）。"""
    global _active_transport
    _active_transport = transport


def write_json(obj: dict) -> bool:
    return _active_transport.write(obj)
