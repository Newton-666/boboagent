"""Bobo TUI Gateway Server — 薄调度层，handler 逻辑在 handlers/ 子模块。"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
from typing import Any

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from bobo_tui_gateway.transport import write_json
from bobo_tui_gateway.server_utils import write_atomic as _write_atomic, ok as _ok, err as _err, emit as _emit, get_context_length as _get_context_length
from config import BOBO_DATA_DIR

logger = logging.getLogger(__name__)

# ── 模块级状态 ──

_sessions: dict[str, dict] = {}
_sessions_lock = threading.Lock()
_current_sid: str | None = None
_methods: dict[str, callable] = {}
_engine_cache: dict[str, Any] = {}
_pending_confirm: dict[str, threading.Event] = {}
_pending_confirm_result: dict[str, bool] = {}
_confirm_lock = threading.Lock()
_auto_mode: dict[str, bool] = {}  # 票 A：会话级 AUTO MODE 开关（/auto 翻转）
_office_state: dict[str, dict] = {}  # TICKET-O2：会话级 OFFICE 状态（/office 翻转，存 {on, session}）
_session_usage: dict[str, dict] = {}
_session_usage_lock = threading.Lock()
_current_engines: dict[str, threading.Event] = {}
_current_engines_lock = threading.Lock()
_active_engine_threads: list[threading.Thread] = []
_engine_threads_lock = threading.Lock()
_scan_candidates: dict[str, list] = {}   # TICKET-SCAN-L3: sid → /scan 候选列表
_relay_links: dict[str, dict] = {}       # TICKET-SCAN-L3: sid → 已建立的互传通道


# ── 方法注册装饰器 ──

def method(name: str):
    def wrapper(fn):
        _methods[name] = fn
        return fn
    return wrapper


# ── ServerContext ──

class _ServerContext:
    """上下文对象，封装 sessions/engine 状态供 handlers 模块访问。"""

    def __init__(self):
        self.sessions = _sessions
        self.sessions_lock = _sessions_lock
        self.engine_cache = _engine_cache
        self.engine_threads_lock = _engine_threads_lock
        self.active_engine_threads = _active_engine_threads
        self.confirm_lock = _confirm_lock
        self.pending_confirm = _pending_confirm
        self.pending_confirm_result = _pending_confirm_result
        self.auto_mode = _auto_mode
        self.office_state = _office_state  # TICKET-O2：/office 会话级状态（仿 _auto_mode）
        self.current_engines = _current_engines
        self.current_engines_lock = _current_engines_lock
        self.session_usage = _session_usage
        self.session_usage_lock = _session_usage_lock
        self.scan_candidates = _scan_candidates
        self.relay_links = _relay_links

    def get_current_sid(self):
        return _current_sid

    def set_current_sid(self, sid):
        global _current_sid
        _current_sid = sid

    def save_session_to_disk(self, sid: str):
        from bobo_tui_gateway.handlers import sessions as _sess
        _sess._save_session_to_disk(sid, self)


_ctx = _ServerContext()


def get_office_on(sid: str) -> bool:
    """票 O4-1：office 会话状态读取器——供 core/injector 延迟 import 查询。

    唯一事实源 = _office_state（/office 翻转与 resume/activate 共用同一 dict），
    普通模式（无记录）返回 False → injector 零注入（对照组铁律）。
    """
    try:
        return bool(_office_state.get(sid, {}).get("on", False))
    except Exception:
        return False


# ── 公开 API（供 entry.py 引用）──

def _save_session_to_disk(sid: str):
    from bobo_tui_gateway.handlers import sessions as _sess
    _sess._save_session_to_disk(sid, _ctx)

def shutdown_sessions():
    from bobo_tui_gateway.handlers import prompts as _prompts
    _prompts.shutdown_sessions(_ctx)


# ── 注册所有 handler 模块 ──

from bobo_tui_gateway.handlers import sessions, configs, models, prompts, tools, misc

for mod in (sessions, configs, models, prompts, tools, misc):
    if mod is configs:
        mod.register(method, _engine_cache)
    else:
        mod.register(method, _ctx)


# ── 请求分发 ──

def dispatch(req: dict) -> dict | None:
    rid = req.get("id")
    method_name = req.get("method", "")
    params = req.get("params", {}) or {}

    handler = _methods.get(method_name)
    if not handler:
        return _err(rid, -32601, f"未知方法: {method_name}")

    try:
        return handler(params, rid)
    except Exception as e:
        logger.exception(f"方法 {method_name} 执行失败")
        return _err(rid, -32000, str(e))
