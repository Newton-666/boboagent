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


# 全局传输实例
_stdio_transport = StdioTransport()


def write_json(obj: dict) -> bool:
    return _stdio_transport.write(obj)
