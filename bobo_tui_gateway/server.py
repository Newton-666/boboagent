"""Bobo TUI Gateway Server - JSON-RPC 方法实现"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import uuid
import threading
from datetime import datetime
from typing import Any

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from bobo_tui_gateway.transport import write_json

logger = logging.getLogger(__name__)

_sessions: dict[str, dict] = {}
_current_sid: str | None = None
_methods: dict[str, callable] = {}
_engine_cache: dict[str, Any] = {}

# 确认请求队列：{session_id: threading.Event}
_pending_confirm: dict[str, threading.Event] = {}
_pending_confirm_result: dict[str, bool] = {}
_confirm_lock = threading.Lock()

# 上下文窗口大小（从环境变量覆盖，否则从 provider 配置获取）
_CONTEXT_LENGTH = int(os.environ.get("CONTEXT_LENGTH", "0"))

def _get_context_length() -> int:
    """返回当前 provider 的上下文长度。优先使用环境变量覆盖。"""
    if _CONTEXT_LENGTH:
        return _CONTEXT_LENGTH
    try:
        from core.provider import resolve_provider
        cfg = resolve_provider()
        return cfg.get("context_length", 128000)
    except Exception:
        return 128000

# 累计 token 用量（跨轮次累加）
_session_usage: dict[str, dict] = {}
_session_usage_lock = threading.Lock()

# 正在运行的引擎实例（用于中断）
_current_engines: dict[str, threading.Event] = {}
_current_engines_lock = threading.Lock()

# 活跃引擎线程跟踪，用于优雅关闭
_active_engine_threads: list[threading.Thread] = []
_engine_threads_lock = threading.Lock()


def register_engine_thread(t: threading.Thread):
    with _engine_threads_lock:
        _active_engine_threads.append(t)


def shutdown_sessions():
    """保存所有活跃会话（在信号处理中调用）"""
    for sid in list(_sessions.keys()):
        _save_session_to_disk(sid)
    # 等待引擎线程完成（最多 3 秒）
    with _engine_threads_lock:
        threads = list(_active_engine_threads)
    for t in threads:
        t.join(timeout=1.0)

# 会话管理器（持久化到磁盘）
_session_mgr = None

def _get_session_mgr():
    global _session_mgr
    if _session_mgr is None:
        from core.session_manager import SessionManager
        from config import SESSION_DIR
        _session_mgr = SessionManager(session_dir=SESSION_DIR)
    return _session_mgr


def method(name: str):
    def wrapper(fn):
        _methods[name] = fn
        return fn
    return wrapper


def _ok(rid, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": rid, "result": result}


def _err(rid, code: int, msg: str) -> dict:
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": msg}}


def _emit(event: str, sid: str, payload: dict | None = None):
    write_json({
        "jsonrpc": "2.0", "method": "event",
        "params": {"type": event, "payload": payload or {}, "session_id": sid}
    })


def _get_llm_caller():
    if "_llm" not in _engine_cache:
        from core.llm_caller import create_llm_caller
        from config import API_KEY, API_BASE_URL, API_MODEL_NAME
        from tools import TOOLS_SCHEMA
        _engine_cache["_llm"] = create_llm_caller(API_KEY, API_BASE_URL, API_MODEL_NAME, TOOLS_SCHEMA)
    return _engine_cache["_llm"]


def _save_session_to_disk(sid: str):
    """将内存中的会话保存到磁盘"""
    session = _sessions.get(sid)
    if not session:
        return
    mgr = _get_session_mgr()
    # 尝试加载已有会话，如果没有则新建
    existing = mgr.load_session(sid)
    if existing:
        existing["messages"] = session.get("messages", [])
        existing["title"] = session.get("title", existing["title"])
        mgr.current_session = existing
        mgr.current_session_id = sid
        mgr._save()
    else:
        # 新建会话文件
        session_path = mgr.session_dir / f"{sid}.json"
        data = {
            "id": sid,
            "created_at": datetime.fromtimestamp(session.get("created_at", time.time())).isoformat(),
            "title": session.get("title", f"会话_{sid}"),
            "messages": session.get("messages", []),
            "summary": None,
        }
        mgr._write_atomic(session_path, data)


def _build_session_info(sid: str) -> dict:
    from config import API_MODEL_NAME, ACTIVE_PROVIDER
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

    session = _sessions.get(sid, {})
    messages = session.get("messages", [])

    return {
        "model": API_MODEL_NAME,
        "provider": ACTIVE_PROVIDER,
        "tools": tool_categories,
        "skills": {"skills": _skill_mgr.list_skills()},
        "version": "2.0",
        "cwd": os.getcwd(),
        "message_count": len(messages),
        "context_max": _get_context_length(),
    }


# ── RPC 方法 ──────────────────────────────────────────────────────────

@method("setup.status")
def handle_setup_status(params: dict, rid: str) -> dict:
    from config import API_KEY, ACTIVE_PROVIDER
    return _ok(rid, {
        "provider_configured": bool(API_KEY),
        "provider": ACTIVE_PROVIDER,
        "providers": ["deepseek", "openai", "anthropic", "openrouter", "google", "ollama", "custom"],
    })


@method("setup.submit")
def handle_setup_submit(params: dict, rid: str) -> dict:
    """保存用户通过 TUI 设置表单提交的 API Key。"""
    provider = params.get("provider", "deepseek")
    api_key = params.get("api_key", "")
    if not api_key:
        return _ok(rid, {"ok": False, "error": "API Key 不能为空"})
    
    env_path = os.path.expanduser("~/.bobo/.env")
    os.makedirs(os.path.dirname(env_path), exist_ok=True)
    
    from core.provider import get_provider
    provider_cfg = get_provider(provider)
    if not provider_cfg:
        return _ok(rid, {"ok": False, "error": f"不支持的提供商: {provider}"})
    
    env_key = provider_cfg["env_key"]
    if not env_key:
        return _ok(rid, {"ok": False, "error": f"{provider} 不需要 API Key（如 Ollama）"})
    
    # 写入 .env 文件
    try:
        key_eq = env_key + "="
        if os.path.exists(env_path):
            with open(env_path) as f:
                content = f.read()
            found = False
            for line in content.split("\n"):
                if line.startswith(key_eq):
                    content = content.replace(line, key_eq + api_key)
                    found = True
                    break
            if not found:
                content += "\n" + key_eq + api_key
        else:
            content = key_eq + api_key + "\n"
        if provider != "deepseek":
            prov_line = "BOBO_PROVIDER="
            found = False
            for line in content.split("\n"):
                if line.startswith(prov_line):
                    content = content.replace(line, prov_line + provider)
                    found = True
                    break
            if not found:
                content += "\n" + prov_line + provider
        with open(env_path, "w") as f:
            f.write(content)
        return {"ok": True, "message": f"{provider} 已配置", "provider_configured": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@method("session.create")
def handle_session_create(params: dict, rid: str) -> dict:
    sid = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
    session = {
        "id": sid,
        "title": params.get("title", f"会话_{sid}"),
        "created_at": time.time(),
        "messages": [],
    }
    _sessions[sid] = session
    global _current_sid
    _current_sid = sid

    # 保存到磁盘
    _save_session_to_disk(sid)

    return _ok(rid, {
        "session_id": sid,
        "info": _build_session_info(sid),
    })


@method("session.title")
def handle_session_title(params: dict, rid: str) -> dict:
    sid = params.get("session_id", "")
    title = params.get("title", "")
    session = _sessions.get(sid)
    if session and title:
        session["title"] = title
        _save_session_to_disk(sid)
    return _ok(rid, {"title": title, "pending": False})


@method("session.list")
def handle_session_list(params: dict, rid: str) -> dict:
    mgr = _get_session_mgr()
    sessions = mgr.list_sessions(limit=20)
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
    return _ok(rid, {"sessions": items})


@method("session.resume")
def handle_session_resume(params: dict, rid: str) -> dict:
    sid = params.get("session_id", "")
    mgr = _get_session_mgr()
    session_data = mgr.load_session(sid)
    if not session_data:
        return _err(rid, -32000, f"会话不存在: {sid}")

    messages = session_data.get("messages", [])
    transcript = []
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role == "user":
            transcript.append({"role": "user", "text": content})
        elif role == "assistant":
            transcript.append({"role": "assistant", "text": content})
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

    _sessions[sid] = {
        "id": sid,
        "title": session_data.get("title", sid),
        "created_at": created_at,
        "messages": messages,
    }
    global _current_sid
    _current_sid = sid

    return _ok(rid, {
        "session_id": sid,
        "messages": transcript,
        "message_count": len(transcript),
        "info": _build_session_info(sid),
        "status": "idle",
        "resumed": sid,
    })


@method("session.close")
def handle_session_close(params: dict, rid: str) -> dict:
    sid = params.get("session_id", "")
    _save_session_to_disk(sid)
    _sessions.pop(sid, None)
    return _ok(rid, {"closed": sid})


@method("session.delete")
def handle_session_delete(params: dict, rid: str) -> dict:
    sid = params.get("session_id", "")
    mgr = _get_session_mgr()
    path = mgr.session_dir / f"{sid}.json"
    if path.exists():
        path.unlink()
    bak = path.with_suffix(".json.bak")
    if bak.exists():
        bak.unlink()
    _sessions.pop(sid, None)
    return _ok(rid, {"deleted": sid})


@method("session.interrupt")
def handle_session_interrupt(params: dict, rid: str) -> dict:
    sid = params.get("session_id", "")
    with _current_engines_lock:
        event = _current_engines.pop(sid, None)
    if event:
        event.set()  # 通知引擎线程中断
        return _ok(rid, {"interrupted": True})
    return _ok(rid, {"interrupted": False})


@method("session.steer")
def handle_session_steer(params: dict, rid: str) -> dict:
    return _ok(rid, {"steered": True})


@method("approval.respond")
def handle_approval_respond(params: dict, rid: str) -> dict:
    """处理前端的确认响应"""
    # 前端发送的格式：{ choice, session_id }
    # 我们用 session_id 来匹配等待中的确认请求
    sid = params.get("session_id", "")
    choice = params.get("choice", "deny")
    with _confirm_lock:
        event = _pending_confirm.pop(sid, None)
        if event:
            # 映射 TUI 的选择到 engine 期望的值:
            # "allow" → True（仅允许这一次）
            # "session"/"always" → "all"（本次对话全部允许）
            if choice in ("session", "always"):
                _pending_confirm_result[sid] = "all"
            elif choice in ("allow", "once"):
                _pending_confirm_result[sid] = True
            else:
                _pending_confirm_result[sid] = False
            event.set()
    return _ok(rid, {"responded": True})


@method("prompt.submit")
def handle_prompt_submit(params: dict, rid: str) -> dict:
    sid = params.get("session_id", "")
    text = params.get("text", "")
    if not text:
        return _err(rid, -32000, "消息不能为空")

    session = _sessions.get(sid)
    if not session:
        return _err(rid, -32000, "会话不存在")

    def _run_engine():
        try:
            from core.engine import Engine
            from core.tool_executor import execute_tool

            llm_caller = _get_llm_caller()
            result_text = [""]
            last_usage = [{}]

            def on_event(event_type, data):
                if event_type == "thinking":
                    # 将引擎思考阶段显示为状态更新（不插入对话）
                    msg = data.get("message", "")
                    if msg:
                        _emit("status.update", sid, {
                            "kind": data.get("phase", ""),
                            "text": msg,
                            "session_id": sid,
                        })
                elif event_type == "tool_call":
                    _emit("tool.start", sid, {
                        "tool_id": data.get("name", ""),
                        "name": data.get("name", ""),
                        "arguments": data.get("args", {}),
                        "context": data.get("context", ""),
                        "session_id": sid,
                    })
                elif event_type == "tool_result":
                    _emit("tool.complete", sid, {
                        "tool_id": data.get("name", ""),
                        "name": data.get("name", ""),
                        "duration": data.get("duration", 0),
                        "session_id": sid,
                    })
                elif event_type == "complete":
                    result_text[0] = data.get("content", "")
                    # 转换 usage 格式以匹配 Hermes TUI 期望的字段
                    raw = data.get("usage", {})
                    if raw:
                        input_tokens = raw.get("prompt_tokens", 0)
                        output_tokens = raw.get("completion_tokens", 0)
                        total = raw.get("total_tokens", 0)
                        # 累计会话 token 用量
                        with _session_usage_lock:
                            acc = _session_usage.setdefault(sid, {"input": 0, "output": 0})
                            acc["input"] += input_tokens
                            acc["output"] += output_tokens
                        context_used = acc["input"] + acc["output"]
                        last_usage[0] = {
                            "input": acc["input"],
                            "output": acc["output"],
                            "total": total,
                            "context_max": _get_context_length(),
                            "context_used": context_used,
                            "context_percent": round(context_used / _get_context_length() * 100, 1),
                        }
                elif event_type == "error":
                    # 将错误发送到 TUI 作为可见错误提示
                    _emit("gateway.error", sid, {
                        "message": data.get("content", ""),
                        "session_id": sid,
                    })
                    # 同时记录到会话文本中，方便追溯
                    result_text[0] = data.get("content", "")
                elif event_type == "thinking.delta":
                    # 将流式 token 实时转发到 TUI
                    _emit("message.delta", sid, {
                        "text": data.get("text", ""),
                        "session_id": sid,
                    })
                elif event_type == "status.update":
                    # 将状态更新转发到 TUI
                    _emit("status.update", sid, {
                        "kind": data.get("kind", ""),
                        "text": data.get("text", ""),
                        "session_id": sid,
                    })

            def confirm_callback(tool_name: str, tool_args: dict, reason: str) -> bool:
                """通过 TUI 前端让用户确认高风险操作"""
                event = threading.Event()
                with _confirm_lock:
                    _pending_confirm[sid] = event

                _emit("approval.request", sid, {
                    "command": tool_name,
                    "description": reason,
                    "session_id": sid,
                })

                # 等待前端响应（最多 120 秒）
                if not event.wait(timeout=120):
                    with _confirm_lock:
                        _pending_confirm.pop(sid, None)
                    return False

                with _confirm_lock:
                    result = _pending_confirm_result.pop(sid, False)
                return result

            _emit("message.start", sid, {"session_id": sid})

            # 创建中断事件
            interrupt_event = threading.Event()
            with _current_engines_lock:
                _current_engines[sid] = interrupt_event

            engine = Engine(llm_caller, execute_tool, callback=on_event, confirm_callback=confirm_callback)
            engine.history = session.get("messages", [])
            engine._interrupt_event = interrupt_event
            engine.run(text)

            # 清理中断事件
            with _current_engines_lock:
                _current_engines.pop(sid, None)

            if engine.history:
                session["messages"] = engine.history

            _save_session_to_disk(sid)

            _emit("message.complete", sid, {
                "session_id": sid,
                "final_text": result_text[0],
                "usage": last_usage[0],
            })

        except Exception as e:
            logger.exception("prompt.submit 后台线程执行失败")
            _emit("error", sid, {"message": str(e), "session_id": sid})

    # 在后台线程中运行引擎，主线程继续处理 stdin
    thread = threading.Thread(target=_run_engine, name=f"engine-{sid}", daemon=True)
    register_engine_thread(thread)
    thread.start()

    return _ok(rid, {"ok": True})


@method("config.get")
def handle_config_get(params: dict, rid: str) -> dict:
    key = params.get("key", "")
    from config import API_MODEL_NAME
    values = {"model": API_MODEL_NAME}
    return _ok(rid, {"value": values.get(key, "")})


@method("config.set")
def handle_config_set(params: dict, rid: str) -> dict:
    return _ok(rid, {"value": params.get("value", "")})


@method("config.full")
def handle_config_full(params: dict, rid: str) -> dict:
    return _ok(rid, {
        "config": {
            "display": {
                "streaming": True,
                "show_reasoning": True,
                "tui_compact": True,
                "details_mode": "collapsed",
            }
        }
    })


@method("tools.list")
def handle_tools_list(params: dict, rid: str) -> dict:
    from tools import TOOLS_SCHEMA
    tools = []
    for t in TOOLS_SCHEMA:
        fn = t.get("function", t)
        tools.append({"name": fn.get("name", ""), "description": fn.get("description", "")})
    return _ok(rid, {"tools": tools})


@method("skills.list")
def handle_skills_list(params: dict, rid: str) -> dict:
    return _ok(rid, {"skills": []})


@method("slash.exec")
def handle_slash_exec(params: dict, rid: str) -> dict:
    command = params.get("command", "")
    sid = params.get("session_id", "")
    if command == "help":
        return _ok(rid, {"output": "可用命令: /help, /clear, /tools, /settings, /exit, /sessions"})
    elif command == "clear":
        _emit("session.cleared", sid, {"session_id": sid})
        return _ok(rid, {"output": ""})
    elif command == "tools":
        from tools import TOOLS_SCHEMA
        names = [t.get("function", t).get("name", "") for t in TOOLS_SCHEMA]
        return _ok(rid, {"output": "可用工具:\n  " + "\n  ".join(names)})
    elif command == "settings":
        from config import API_MODEL_NAME, ACTIVE_PROVIDER
        lines = [
            f"Bobo 当前配置:",
            f"  提供商: {ACTIVE_PROVIDER}",
            f"  模型: {API_MODEL_NAME}",
            f"",
            f"要修改配置，直接在聊天中说:",
            f"  \"切换到 OpenAI\"",
            f"  \"使用 gpt-4o 模型\"",
            f"  \"更新 API 密钥\"",
            f"  \"查看我的配置\"",
            f"",
            f"配置文件位置: ~/.bobo/.env",
        ]
        return _ok(rid, {"output": "\n".join(lines)})
    else:
        return _ok(rid, {"output": f"未知命令: /{command}"})


@method("command.dispatch")
def handle_command_dispatch(params: dict, rid: str) -> dict:
    name = params.get("name", "")
    return _ok(rid, {"type": "exec", "output": f"执行命令: {name}"})


@method("shell.exec")
def handle_shell_exec(params: dict, rid: str) -> dict:
    import subprocess
    command = params.get("command", "")
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=10)
        output = result.stdout or result.stderr or "(无输出)"
        return _ok(rid, {"output": output.strip()})
    except Exception as e:
        return _ok(rid, {"output": f"错误: {e}"})


@method("image.attach")
def handle_image_attach(params: dict, rid: str) -> dict:
    return _ok(rid, {"attached": True})


@method("paste.collapse")
def handle_paste_collapse(params: dict, rid: str) -> dict:
    return _ok(rid, {"path": None})


@method("terminal.resize")
def handle_terminal_resize(params: dict, rid: str) -> dict:
    return _ok(rid, {"resized": True})


@method("session.active_list")
def handle_session_active_list(params: dict, rid: str) -> dict:
    items = []
    for sid, session in _sessions.items():
        items.append({
            "id": sid,
            "title": session.get("title", sid),
            "status": "idle",
            "message_count": len(session.get("messages", [])),
        })
    return _ok(rid, {"sessions": items})


@method("session.activate")
def handle_session_activate(params: dict, rid: str) -> dict:
    sid = params.get("session_id", "")
    session = _sessions.get(sid)
    if not session:
        return _err(rid, -32000, "会话不存在")
    global _current_sid
    _current_sid = sid
    messages = session.get("messages", [])
    transcript = []
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role == "user":
            transcript.append({"role": "user", "text": content})
        elif role == "assistant":
            transcript.append({"role": "assistant", "text": content})
    return _ok(rid, {
        "session_id": sid,
        "messages": transcript,
        "message_count": len(transcript),
        "info": _build_session_info(sid),
        "status": "idle",
    })


@method("input.detect_drop")
def handle_input_detect_drop(params: dict, rid: str) -> dict:
    return _ok(rid, {"dropped": False})


# ── 请求分发 ──────────────────────────────────────────────────────────

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
