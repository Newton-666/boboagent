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


# 全局传输实例（socket 模式下由 set_transport 替换；多客户端模式见注册表）
_stdio_transport = StdioTransport()
_active_transport = _stdio_transport

# TICKET-GW-MULTI：socket 模式多客户端注册表——每条连接一个 SocketTransport。
# 事件（server_utils.emit → write_json）全广播，客户端按 session_id 过滤
# （widget.html 已有 sid 过滤先例）；RPC 响应走连接定向写（_serve_connection 内）。
_transports: list[Any] = []
_transports_lock = threading.Lock()


def set_transport(transport) -> None:
    """切换当前生效的传输通道（stdio 默认；socket 单连接旧路径兼容）。"""
    global _active_transport
    _active_transport = transport


def register_transport(transport) -> None:
    """注册一条 socket 客户端传输（连接建立时调用，断开时注销）。"""
    with _transports_lock:
        if transport not in _transports:
            _transports.append(transport)


def unregister_transport(transport) -> None:
    """注销一条 socket 客户端传输（连接断开时调用）。"""
    with _transports_lock:
        try:
            _transports.remove(transport)
        except ValueError:
            pass


def active_client_count() -> int:
    """当前活跃 socket 客户端数（多客户端空闲超时判定用）。"""
    with _transports_lock:
        return len(_transports)


def write_json(obj: dict) -> bool:
    """广播到所有注册传输；无注册时回退单播（stdio 模式行为不变）。

    socket 多客户端：emit 事件全广播，客户端按 session_id 过滤；单客户端时
    等价于旧单播语义。某个客户端写失败不影响其余客户端（继续广播）。
    """
    with _transports_lock:
        targets = list(_transports)
    if not targets:
        return _active_transport.write(obj)
    ok_all = True
    for t in targets:
        if not t.write(obj):
            ok_all = False
    return ok_all
