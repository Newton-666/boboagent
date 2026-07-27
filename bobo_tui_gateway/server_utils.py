"""server_utils.py — 共享工具函数，被多个 handler 组复用。"""

import json
import logging
import os
import sys
import tempfile
import shutil as _sh
from bobo_tui_gateway.transport import write_json

logger = logging.getLogger(__name__)

# 上下文窗口大小（从环境变量覆盖，否则从 provider 配置获取）
_CONTEXT_LENGTH = int(os.environ.get("CONTEXT_LENGTH", "0"))


def get_context_length() -> int:
    """返回当前 model 的上下文长度（先查 model_context，再 provider，最后 128k 兜底）。"""
    if _CONTEXT_LENGTH:
        return _CONTEXT_LENGTH
    try:
        from core.provider import get_context_length as _gcl
        return _gcl()
    except Exception:
        return 128_000


def ok(rid, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": rid, "result": result}


def err(rid, code: int, msg: str) -> dict:
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": msg}}


def emit(event: str, sid: str, payload: dict | None = None):
    write_json({
        "jsonrpc": "2.0", "method": "event",
        "params": {"type": event, "payload": payload or {}, "session_id": sid},
    })


def write_atomic(path: str, content: str):
    """原子写入：先写 tmp 再 rename，防止中途崩溃导致文件损坏。"""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path) or ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        _sh.move(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except Exception:
            pass
        raise
