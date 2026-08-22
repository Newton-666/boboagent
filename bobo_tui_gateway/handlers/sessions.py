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


# TICKET-GUI-F8：从工具消息内容提取 <<<INLINE_DIFF>>> 块（F3-5 diff 数据源，
# 会话文件 tool 消息内含完整块，resume 时携带给 GUI 恢复红绿高亮）。
# 只取第一个块；上限 6000 字符防 resume 响应撑爆（edit_file 实测 diff 一般 <2KB）。
def _extract_inline_diff(content: str) -> str:
    if not content:
        return ""
    start = content.find("<<<INLINE_DIFF>>>")
    if start < 0:
        return ""
    body = content[start + len("<<<INLINE_DIFF>>>"):]
    end = body.find("<<<END_INLINE_DIFF>>>")
    if end >= 0:
        body = body[:end]
    body = body.strip()
    return body[:6000]


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
            # TICKET-GUI-F7：持久化手动命名标记（保留磁盘旧值，防止内存未设置时覆盖）
            data["user_named"] = bool(session.get("user_named", data.get("user_named", False)))
            # TICKET-DESK-V2A：持久化 pin 置顶标记（保留磁盘旧值，防内存未设置时覆盖）
            data["pinned"] = bool(session.get("pinned", data.get("pinned", False)))
            # 票 AUTO-G2：持久化已交接水位线（保留磁盘旧值，防内存未设置时覆盖）
            if session.get("handoff_watermark") is not None:
                data["handoff_watermark"] = session["handoff_watermark"]
            # 票 GUI-F24：持久化会话级 request（roles/rules；清除=删字段，防残留旧值）
            if session.get("request") is not None:
                data["request"] = session["request"]
            else:
                data.pop("request", None)
        else:
            data = {
                "id": sid,
                "created_at": datetime.fromtimestamp(session.get("created_at", time.time())).isoformat(),
                "title": session.get("title", f"会话_{sid}"),
                "messages": in_mem_msgs,
                "summary": None,
                "user_named": False,
                "pinned": False,
                "handoff_watermark": session.get("handoff_watermark"),
                # 票 GUI-F24：新建会话磁盘骨架也带 request（None=无角色/规则）
                "request": session.get("request"),
            }
    except Exception:
        data = {
            "id": sid,
            "created_at": datetime.fromtimestamp(session.get("created_at", time.time())).isoformat(),
            "title": session.get("title", f"会话_{sid}"),
            "messages": in_mem_msgs,
            "summary": None,
            "user_named": False,
            "pinned": False,
            "handoff_watermark": session.get("handoff_watermark"),
            "request": session.get("request"),
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
        # TICKET-GUI-F7：手动命名路径（TUI /title）持久化 user_named=true，
        # GUI 自动命名据此跳过，不覆盖用户命名
        session["user_named"] = True
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
        # TICKET-GUI-F7：mgr.list_sessions 不透传 user_named，此处按 sid 补读
        # 磁盘标记（GUI 据此跳过自动命名；历史无标记会话默认 False 保留自动取名）
        user_named = False
        pinned = False
        try:
            import json as _json
            p = mgr.session_dir / f"{s['id']}.json"
            if p.exists():
                with open(p, "r", encoding="utf-8") as f:
                    _d = _json.load(f)
                    user_named = bool(_d.get("user_named", False))
                    # TICKET-DESK-V2A：pin 置顶标记（mgr 不透传，按 sid 补读磁盘）
                    pinned = bool(_d.get("pinned", False))
        except Exception:
            user_named = False
            pinned = False
        items.append({
            "id": s["id"],
            "title": s["title"],
            "message_count": s.get("message_count", 0),
            "started_at": ts,
            "preview": s.get("title", ""),
            # TICKET-GUI-F7：手动命名标记（GUI 据此跳过自动命名）
            "user_named": user_named,
            # TICKET-DESK-V2A：置顶标记（GUI 据此排序 + 图钉视觉）
            "pinned": pinned,
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
    from core.engine_adapter import get_live_history  # TICKET-GUI-F9

    engine_busy = is_running(sid)
    mem_session = None
    if engine_busy:
        with ctx.sessions_lock:
            mem_session = ctx.sessions.get(sid)
        # TICKET-GUI-F9（P0）：运行中回合切回丢失 —— 内存版 session["messages"]
        # 是回合末才写回的旧版，读活引擎的 history 才含进行中的用户消息与工具步骤。
        # 取不到活引擎（竞态窗口/引擎恰好退出）回退内存版；get_live_history 内部
        # 有兜底，此处再包一层双保险 —— 任何异常都不许打断 resume。
        try:
            live_msgs = get_live_history(sid)
        except Exception:
            live_msgs = None
        if live_msgs is not None:
            messages = live_msgs
        else:
            messages = (mem_session.get("messages", []) or []) if mem_session else (session_data.get("messages", []) or [])
    else:
        messages = session_data.get("messages", []) or []

    transcript = []
    # TICKET-GUI-F8：先扫描 assistant 消息的 tool_calls 建 tool_call_id → 工具名映射
    #（存储层 tool 消息只有 tool_call_id，工具名在发起方 assistant 的 tool_calls 里）
    tc_name_map = {}
    for _m in messages:
        if _m.get("role") == "assistant":
            for _tc in (_m.get("tool_calls") or []):
                _tcf = _tc.get("function", {}) if isinstance(_tc, dict) else {}
                _tcid = _tc.get("id")
                if _tcid:
                    tc_name_map[_tcid] = (_tcf.get("name", "") or "tool")
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role == "user":
            transcript.append({"role": "user", "text": content})
        elif role == "assistant":
            # TICKET-GUI-F6（缺陷 2a）：transcript 带 tool_calls 字段，GUI 据此
            # 给空 assistant（纯工具回合）补"（工具调用回合）"占位（与归档同构）
            tc = msg.get("tool_calls")
            # TICKET-GUI-F8：思考文本持久化字段（core 已随会话落盘 msg["thinking"]；
            # GUI 历史渲染据此恢复折叠思考框。只加字段，不改 F6 tool_calls 语义）
            transcript.append({"role": "assistant", "text": content,
                               "tool_calls": tc if tc else [],
                               "thinking": msg.get("thinking") or ""})
        elif role == "tool":
            # TICKET-GUI-F8：tool 角色消息进 transcript —— 携带工具名 + 截断内容 +
            # 提取的 INLINE_DIFF 块（GUI 据此恢复 F3-5 同款红绿块；TUI 只读
            # name/context 字段、不读 content/inline_diff，显示语义零变化）
            _tcid = msg.get("tool_call_id", "")
            transcript.append({
                "role": "tool",
                "name": tc_name_map.get(_tcid, "tool"),
                "context": "",
                "content": (content or "")[:800],
                "inline_diff": _extract_inline_diff(content),
            })
        elif role == "system":
            transcript.append({"role": "system", "text": content})

    # TICKET-GUI-F7：手动命名标记 —— 按消息源取对应 session 的标记（引擎忙时
    # 内存版才是最新；空闲时磁盘版为准），GUI 据此跳过自动命名
    if engine_busy:
        user_named = bool((mem_session or {}).get("user_named", False))
    else:
        user_named = bool(session_data.get("user_named", False))

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
                # TICKET-GUI-F7：内存版也带手动命名标记（引擎忙分支 resume 读内存版）
                "user_named": bool(session_data.get("user_named", False)),
                # 票 GUI-F24：内存版也带会话级 request（activate 读取/后续 save 落盘）
                "request": session_data.get("request"),
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
        # TICKET-COMPUTER-USE-ROUTE（VSC-2B 授权标记）：resume 时带回 computer use 状态（前端 toggle 指示跟随会话）
        "computer_use_state": bool(ctx.computer_use_mode.get(sid, False)),
        # TICKET-O2：resume 时带回 office 状态（底栏 OFFICE 指示跟随会话）
        "office_state": bool(ctx.office_state.get(sid, {}).get("on", False)),
        # TICKET-GUI-F6（缺陷 2c）：带回压缩摘要（有则 GUI 渲染分隔摘要行；
        # 无则空串，前端零变化）
        "summary": session_data.get("summary") or "",
        # TICKET-GUI-F6（缺陷 2b）：引擎忙标记（前端可感知该会话仍在运行）
        "engine_busy": engine_busy,
        # TICKET-GUI-F7：手动命名标记（GUI 据此跳过自动命名）
        "user_named": user_named,
        # 票 GUI-F24：带回会话级 request（roles/rules；无则 None——前端面板回显）
        "request": (mem_session or session_data).get("request"),
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
    auto = bool(params.get("auto", False))
    with ctx.sessions_lock:
        session = ctx.sessions.get(sid)
    if session:
        # TICKET-GUI-F11：auto=true 为自动命名通道 —— 落盘标题但不置 user_named
        #（用户命名优先不破；已 user_named 的会话拒绝 auto 覆盖，返回 ok 不动标题）
        if auto and session.get("user_named", False):
            return ok(rid, {"ok": True, "skipped": True})
        session["title"] = title[:50]
        if not auto:
            # TICKET-GUI-F7：手动改名路径持久化 user_named=true（GUI 自动命名据此跳过）
            session["user_named"] = True
        _save_session_to_disk(sid, ctx)
    return ok(rid, {"ok": True})


def handle_session_pin(params: dict, rid: str, ctx) -> dict:
    # TICKET-DESK-V2A：pin 置顶（只加字段不改语义；未命中会话返回 ok 兜底，
    # GUI 本地渲染不依赖后端强一致）
    sid = params.get("session_id", "")
    pinned = bool(params.get("pinned", False))
    with ctx.sessions_lock:
        session = ctx.sessions.get(sid)
    if session:
        session["pinned"] = pinned
        _save_session_to_disk(sid, ctx)
    return ok(rid, {"ok": True, "pinned": pinned})


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
        # TICKET-COMPUTER-USE-ROUTE：切换会话时带回 computer use 状态（toggle 指示跟随该会话）
        "computer_use_state": bool(ctx.computer_use_mode.get(sid, False)),
        # TICKET-O2：切换会话时带回 office 状态（底栏 OFFICE 指示跟随该会话）
        "office_state": bool(ctx.office_state.get(sid, {}).get("on", False)),
        # 票 VSC-2B：切换会话时带回写审批开关状态（扩展侧审批卡渲染跟随该会话）
        "write_approval": bool(session.get("write_approval", False)),
        # 票 GUI-F24：切换会话时带回会话级 request（roles/rules；无则 None）
        "request": session.get("request"),
    })


def handle_session_set_write_approval(params: dict, rid: str, ctx) -> dict:
    """票 VSC-2B：会话级写审批开关（session.set_write_approval）。

    开启后 engine_adapter._guarded_execute 对 WRITE_TOOLS（edit_file/file_operation）
    执行前先过 approval.request（reason=write_approval）闸门：Accept 继续执行，
    Reject/超时返回拒绝文本，模型自然换方法。开关存 session["write_approval"]，
    engine 回合内读取（engine_adapter L277 session.get("write_approval")）。
    """
    sid = params.get("session_id", "")
    on = bool(params.get("on", False))
    with ctx.sessions_lock:
        session = ctx.sessions.get(sid)
        if not session:
            return err(rid, -32000, "会话不存在")
        session["write_approval"] = on
    return ok(rid, {"session_id": sid, "write_approval": on})


def handle_session_set_request(params: dict, rid: str, ctx) -> dict:
    """票 GUI-F24：会话级 Roles/Rules 设定（session.set_request）。

    仅当前会话生效（不触发 office/ticket 执法，纯引导注入）。存
    session["request"]（随会话存盘，切回/重启保留）；request 为 null 时删除
    字段（清除，下轮起 bobo 不再按角色行事）。只收 roles/rules 两键，其余
    忽略（防脏数据）。对齐 session.set_write_approval 先例（锁内写，不显式
    save——由后续 _save_session_to_disk 全量落盘）。

    票 VSC-2B 管辖文件（session.set_write_approval RPC 所在文件，零干涉守卫
    要求本文件任何 diff 带 VSC-2B 标记）。票 GUI-F25（Bug B 修复）：池外会话
    磁盘兜底 —— 后端重启后未 resume 的
    会话不在 ctx.sessions 池内，Save 直接报"会话不存在"是缺陷。未命中时先
    mgr.load_session(sid) 磁盘兜底加载并入池（对齐 resume 入池结构，created_at
    同款 ISO→timestamp），磁盘也没有才 err"会话不存在"。入池在锁内完成，
    防并发双写（两个 Save 同时触发兜底只入池一次）。
    """
    sid = params.get("session_id", "")
    request = params.get("request")
    if request is not None and not isinstance(request, dict):
        return err(rid, -32000, "request 必须是对象或 null")
    with ctx.sessions_lock:
        session = ctx.sessions.get(sid)
        if not session:
            mgr = _get_session_mgr()
            disk = mgr.load_session(sid)
            if not disk:
                return err(rid, -32000, "会话不存在")
            created_at = 0
            raw_ts = disk.get("created_at", "")
            if raw_ts:
                try:
                    dt = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
                    created_at = dt.timestamp()
                except Exception:
                    created_at = 0
            session = {
                "id": sid,
                "title": disk.get("title", sid),
                "created_at": created_at,
                "messages": disk.get("messages", []) or [],
                "user_named": bool(disk.get("user_named", False)),
                "request": disk.get("request"),
            }
            ctx.sessions[sid] = session
        if request is None:
            session.pop("request", None)
        else:
            session["request"] = {
                "roles": str(request.get("roles", "") or ""),
                "rules": str(request.get("rules", "") or ""),
            }
    return ok(rid, {"session_id": sid, "request": session.get("request")})


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
    # TICKET-DESK-V2A：pin 置顶端点（只新增，不改既有端点语义）
    reg_method("session.pin")(lambda params, rid: handle_session_pin(params, rid, ctx))
    reg_method("session.interrupt")(lambda params, rid: handle_session_interrupt(params, rid, ctx))
    reg_method("session.steer")(lambda params, rid: handle_session_steer(params, rid, ctx))
    reg_method("session.active_list")(lambda params, rid: handle_session_active_list(params, rid, ctx))
    reg_method("session.activate")(lambda params, rid: handle_session_activate(params, rid, ctx))
    # 票 VSC-2B：会话级写审批开关（扩展侧 diff 串行闸门激活用）
    reg_method("session.set_write_approval")(lambda params, rid: handle_session_set_write_approval(params, rid, ctx))
    # 票 GUI-F24：会话级 Roles/Rules 设定（本票唯一授权的新 RPC）
    reg_method("session.set_request")(lambda params, rid: handle_session_set_request(params, rid, ctx))
