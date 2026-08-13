"""handlers/sessions.py — Session 生命周期 handler（create/resume/list/close/delete/rename/interrupt/steer/activate）。"""

import logging
import os
import time
import uuid
from datetime import datetime

from bobo_tui_gateway.server_utils import ok, err, emit, write_atomic, get_context_length
from config import API_MODEL_NAME, ACTIVE_PROVIDER, SESSION_DIR

logger = logging.getLogger(__name__)

_session_mgr = None


def _get_session_mgr():
    global _session_mgr
    if _session_mgr is None:
        from core.session_manager import SessionManager
        _session_mgr = SessionManager(session_dir=SESSION_DIR)
    return _session_mgr


def _save_session_to_disk(sid, ctx):
    """将内存中的会话保存到磁盘（直接原子写入，不触碰 mgr.current_session 以避免跨会话竞态）。

    TICKET-GUI-F3 F3-4（Kimi 特批 2026-08-13）：防数据破坏兜底 ——
    内存 messages 为空且磁盘已有同 sid 非空版本时，拒绝覆盖并记 warning 日志。
    """
    with ctx.sessions_lock:
        session = ctx.sessions.get(sid)
    if not session:
        return
    mgr = _get_session_mgr()
    session_path = mgr.session_dir / f"{sid}.json"
    in_mem_msgs = session.get("messages", []) or []
    # 尝试加载已有会话以便保留元数据（created_at 等），否则新建
    try:
        if session_path.exists():
            with open(session_path, "r", encoding="utf-8") as f:
                import json as _json
                data = _json.load(f)
            # F3-4 兜底：内存空消息不得覆盖磁盘非空历史（竞态丢消息案，20260813_105719 等 0 消息落盘）
            if not in_mem_msgs and data.get("messages"):
                logger.warning(
                    "F3-4 拒绝覆盖：session %s 内存 messages 为空但磁盘已有 %d 条消息，保留磁盘版本",
                    sid, len(data["messages"]),
                )
                return
            data["messages"] = in_mem_msgs
            data["title"] = session.get("title", data.get("title", f"会话_{sid}"))
        else:
            data = {
                "id": sid,
                "created_at": datetime.fromtimestamp(session.get("created_at", time.time())).isoformat(),
                "title": session.get("title", f"会话_{sid}"),
                "messages": in_mem_msgs,
                "summary": None,
            }
    except Exception:
        data = {
            "id": sid,
            "created_at": datetime.fromtimestamp(session.get("created_at", time.time())).isoformat(),
            "title": session.get("title", f"会话_{sid}"),
            "messages": in_mem_msgs,
            "summary": None,
        }
    mgr._write_atomic(session_path, data)


def _build_session_info(sid, ctx):
    from tools import TOOLS_SCHEMA
    from core.context import ContextMixin
    from core.skill_manager import get_skill_manager
    _skill_mgr = get_skill_manager()

    # 使用引擎本身的工具分类，而不是把所有工具塞进 "general"
    tool_categories: dict[str, list[str]] = {}
    for cat, names in ContextMixin.TOOL_CATEGORIES.items():
        tool_categories[cat] = [n for n in names if any(
            t.get("function", t).get("name") == n for t in TOOLS_SCHEMA
        )]
    # 处理不在任何分类中的工具
    all_categorized = set()
    for names in tool_categories.values():
        all_categorized.update(names)
    uncategorized = []
    for t in TOOLS_SCHEMA:
        name = t.get("function", t).get("name", "")
        if name and name not in all_categorized:
            uncategorized.append(name)
    if uncategorized:
        tool_categories["other"] = uncategorized
    # 去掉空类别
    tool_categories = {k: v for k, v in tool_categories.items() if v}

    session = ctx.sessions.get(sid, {})
    messages = session.get("messages", [])

    return {
        "model": API_MODEL_NAME,
        "provider": ACTIVE_PROVIDER,
        "tools": tool_categories,
        "skills": {"skills": _skill_mgr.list_skills()},
        "version": "2.0",
        "cwd": os.getcwd(),
        "message_count": len(messages),
        "context_max": get_context_length(),
    }


# ── Handler 函数 ──

def handle_session_create(params: dict, rid: str, ctx) -> dict:
    sid = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
    session = {
        "id": sid,
        "title": params.get("title", f"会话_{sid}"),
        "created_at": time.time(),
        "messages": [],
    }
    with ctx.sessions_lock:
        ctx.sessions[sid] = session
        ctx.set_current_sid(sid)

    # 保存到磁盘
    _save_session_to_disk(sid, ctx)

    return ok(rid, {
        "session_id": sid,
        "info": _build_session_info(sid, ctx),
    })


def handle_session_title(params: dict, rid: str, ctx) -> dict:
    sid = params.get("session_id", "")
    title = params.get("title", "")
    with ctx.sessions_lock:
        session = ctx.sessions.get(sid)
    if session and title:
        session["title"] = title
        _save_session_to_disk(sid, ctx)
    return ok(rid, {"title": title, "pending": False})


def handle_session_list(params: dict, rid: str, ctx) -> dict:
    mgr = _get_session_mgr()
    sessions = mgr.list_sessions(limit=100)
    items = []
    for s in sessions:
        # 解析 created_at 为 Unix 时间戳
        ts = 0
        raw = s.get("created_at", "")
        if raw:
            try:
                dt = datetime.strptime(str(raw)[:19], "%Y%m%d_%H%M%S")
                ts = dt.timestamp()
            except ValueError:
                try:
                    dt = datetime.fromisoformat(str(raw))
                    ts = dt.timestamp()
                except Exception:
                    ts = 0
        items.append({
            "id": s["id"],
            "title": s["title"],
            "message_count": s.get("message_count", 0),
            "started_at": ts,
            "preview": s.get("title", ""),
        })
    return ok(rid, {"sessions": items})


def handle_session_resume(params: dict, rid: str, ctx) -> dict:
    sid = params.get("session_id", "")
    mgr = _get_session_mgr()
    session_data = mgr.load_session(sid)
    if not session_data:
        return err(rid, -32000, f"会话不存在: {sid}")

    # TICKET-GUI-F6（缺陷 2b）：时序竞争修复 —— 该 sid 引擎正跑回合（有未落盘
    # 消息）时，resume 返回内存版最新消息，禁止磁盘版覆盖运行中会话（否则最近
    # 对话"消失"且丢回合）。仅在引擎空闲时才允许磁盘版覆盖内存（原行为）。
    from core.engine_adapter import is_running

    engine_busy = is_running(sid)
    if engine_busy:
        with ctx.sessions_lock:
            mem_session = ctx.sessions.get(sid)
        messages = (mem_session.get("messages", []) or []) if mem_session else (session_data.get("messages", []) or [])
    else:
        messages = session_data.get("messages", []) or []

    transcript = []
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role == "user":
            transcript.append({"role": "user", "text": content})
        elif role == "assistant":
            # TICKET-GUI-F6（缺陷 2a）：transcript 带 tool_calls 字段，GUI 据此
            # 给空 assistant（纯工具回合）补"（工具调用回合）"占位（与归档同构）
            tc = msg.get("tool_calls")
            transcript.append({"role": "assistant", "text": content,
                               "tool_calls": tc if tc else []})
        elif role == "system":
            transcript.append({"role": "system", "text": content})

    # 恢复 created_at
    created_at = 0
    raw_ts = session_data.get("created_at", "")
    if raw_ts:
        try:
            dt = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
            created_at = dt.timestamp()
        except Exception:
            created_at = 0

    if not engine_busy:
        with ctx.sessions_lock:
            ctx.sessions[sid] = {
                "id": sid,
                "title": session_data.get("title", sid),
                "created_at": created_at,
                "messages": messages,
            }
    # 引擎忙时禁止磁盘覆盖内存（丢回合风险）；但当前会话指向仍要切到该 sid
    with ctx.sessions_lock:
        ctx.set_current_sid(sid)

    return ok(rid, {
        "session_id": sid,
        "messages": transcript,
        "message_count": len(transcript),
        "info": _build_session_info(sid, ctx),
        "status": "idle",
        "resumed": sid,
        # 票 AUTO-F：resume 时带回 auto 状态，前端底栏指示不丢
        "auto_state": bool(ctx.auto_mode.get(sid, False)),
        # TICKET-O2：resume 时带回 office 状态（底栏 OFFICE 指示跟随会话）
        "office_state": bool(ctx.office_state.get(sid, {}).get("on", False)),
        # TICKET-GUI-F6（缺陷 2c）：带回压缩摘要（有则 GUI 渲染分隔摘要行；
        # 无则空串，前端零变化）
        "summary": session_data.get("summary") or "",
        # TICKET-GUI-F6（缺陷 2b）：引擎忙标记（前端可感知该会话仍在运行）
        "engine_busy": engine_busy,
    })


def handle_session_close(params: dict, rid: str, ctx) -> dict:
    sid = params.get("session_id", "")
    _save_session_to_disk(sid, ctx)
    with ctx.sessions_lock:
        ctx.sessions.pop(sid, None)
    return ok(rid, {"closed": sid})


def handle_session_delete(params: dict, rid: str, ctx) -> dict:
    sid = params.get("session_id", "")
    mgr = _get_session_mgr()
    path = mgr.session_dir / f"{sid}.json"
    if path.exists():
        path.unlink()
    bak = path.with_suffix(".json.bak")
    if bak.exists():
        bak.unlink()
    with ctx.sessions_lock:
        ctx.sessions.pop(sid, None)
    return ok(rid, {"deleted": sid})


def handle_session_rename(params: dict, rid: str, ctx) -> dict:
    sid = params.get("session_id", "")
    title = params.get("title", "").strip() or "未命名"
    with ctx.sessions_lock:
        session = ctx.sessions.get(sid)
    if session:
        session["title"] = title[:50]
        _save_session_to_disk(sid, ctx)
    return ok(rid, {"ok": True})


def handle_session_interrupt(params: dict, rid: str, ctx) -> dict:
    sid = params.get("session_id", "")
    try:
        from core.engine_adapter import cancel
        cancel(sid)
        return ok(rid, {"interrupted": True})
    except Exception:
        return ok(rid, {"interrupted": False})


def handle_session_steer(params: dict, rid: str, ctx) -> dict:
    return ok(rid, {"steered": True})


def handle_session_active_list(params: dict, rid: str, ctx) -> dict:
    items = []
    with ctx.sessions_lock:
        for sid, session in ctx.sessions.items():
            items.append({
                "id": sid,
                "title": session.get("title", sid),
                "status": "idle",
                "message_count": len(session.get("messages", [])),
            })
    return ok(rid, {"sessions": items})


def handle_session_activate(params: dict, rid: str, ctx) -> dict:
    sid = params.get("session_id", "")
    session = ctx.sessions.get(sid)
    if not session:
        return err(rid, -32000, "会话不存在")
    ctx.set_current_sid(sid)
    messages = session.get("messages", [])
    transcript = []
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role == "user":
            transcript.append({"role": "user", "text": content})
        elif role == "assistant":
            transcript.append({"role": "assistant", "text": content})
    return ok(rid, {
        "session_id": sid,
        "messages": transcript,
        "message_count": len(transcript),
        "info": _build_session_info(sid, ctx),
        "status": "idle",
        # 票 AUTO-F：切换会话时带回 auto 状态，底栏指示跟随该会话
        "auto_state": bool(ctx.auto_mode.get(sid, False)),
        # TICKET-O2：切换会话时带回 office 状态（底栏 OFFICE 指示跟随该会话）
        "office_state": bool(ctx.office_state.get(sid, {}).get("on", False)),
    })


# ── 注册 ──

def register(reg_method, ctx):
    """注册所有 session handler。

    Args:
        reg_method: 方法注册函数（server.py 的 method 装饰器等价物）
        ctx: _ServerContext 实例，提供 sessions / sessions_lock / current_sid 访问
    """
    reg_method("session.create")(lambda params, rid: handle_session_create(params, rid, ctx))
    reg_method("session.title")(lambda params, rid: handle_session_title(params, rid, ctx))
    reg_method("session.list")(lambda params, rid: handle_session_list(params, rid, ctx))
    reg_method("session.resume")(lambda params, rid: handle_session_resume(params, rid, ctx))
    reg_method("session.close")(lambda params, rid: handle_session_close(params, rid, ctx))
    reg_method("session.delete")(lambda params, rid: handle_session_delete(params, rid, ctx))
    reg_method("session.rename")(lambda params, rid: handle_session_rename(params, rid, ctx))
    reg_method("session.interrupt")(lambda params, rid: handle_session_interrupt(params, rid, ctx))
    reg_method("session.steer")(lambda params, rid: handle_session_steer(params, rid, ctx))
    reg_method("session.active_list")(lambda params, rid: handle_session_active_list(params, rid, ctx))
    reg_method("session.activate")(lambda params, rid: handle_session_activate(params, rid, ctx))
