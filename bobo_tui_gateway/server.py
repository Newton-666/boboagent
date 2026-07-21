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
_sessions_lock = threading.Lock()
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
    with _sessions_lock:
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
    """将内存中的会话保存到磁盘（直接原子写入，不触碰 mgr.current_session 以避免跨会话竞态）。"""
    with _sessions_lock:
        session = _sessions.get(sid)
    if not session:
        return
    mgr = _get_session_mgr()
    session_path = mgr.session_dir / f"{sid}.json"
    # 尝试加载已有会话以便保留元数据（created_at 等），否则新建
    try:
        if session_path.exists():
            with open(session_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            data["messages"] = session.get("messages", [])
            data["title"] = session.get("title", data.get("title", f"会话_{sid}"))
        else:
            data = {
                "id": sid,
                "created_at": datetime.fromtimestamp(session.get("created_at", time.time())).isoformat(),
                "title": session.get("title", f"会话_{sid}"),
                "messages": session.get("messages", []),
                "summary": None,
            }
    except Exception:
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
        return _ok(rid, {"ok": True, "message": f"{provider} 已配置", "provider_configured": True})
    except Exception as e:
        return _ok(rid, {"ok": False, "error": str(e)})


@method("session.create")
def handle_session_create(params: dict, rid: str) -> dict:
    sid = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
    session = {
        "id": sid,
        "title": params.get("title", f"会话_{sid}"),
        "created_at": time.time(),
        "messages": [],
    }
    with _sessions_lock:
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
    with _sessions_lock:
        session = _sessions.get(sid)
    if session and title:
        session["title"] = title
        _save_session_to_disk(sid)
    return _ok(rid, {"title": title, "pending": False})


@method("session.list")
def handle_session_list(params: dict, rid: str) -> dict:
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

    with _sessions_lock:
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
    with _sessions_lock:
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
    with _sessions_lock:
        _sessions.pop(sid, None)
    return _ok(rid, {"deleted": sid})


@method("session.rename")
def handle_session_rename(params: dict, rid: str) -> dict:
    sid = params.get("session_id", "")
    title = params.get("title", "").strip() or "未命名"
    with _sessions_lock:
        session = _sessions.get(sid)
    if session:
        session["title"] = title[:50]
        _save_session_to_disk(sid)
    return _ok(rid, {"ok": True})


@method("session.interrupt")
def handle_session_interrupt(params: dict, rid: str) -> dict:
    sid = params.get("session_id", "")
    try:
        from core.engine_adapter import cancel
        cancel(sid)
        return _ok(rid, {"interrupted": True})
    except Exception:
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

    with _sessions_lock:
        session = _sessions.get(sid)
    if not session:
        return _err(rid, -32000, "会话不存在")

    # 审计 #12：防止同一会话并发提交，导致两个 engine 线程同时写 history
    from core.engine_adapter import is_running
    if is_running(sid):
        return _err(rid, -32000, "该会话正在处理上一个请求，请等待完成")

    # 在后台线程中运行引擎，主线程继续处理 stdin
    from core.engine_adapter import run_engine as _run_engine_adapter

    thread = threading.Thread(
        target=_run_engine_adapter,
        args=(
            sid, session, text, _emit,
            _get_llm_caller, _get_context_length,
            register_engine_thread,
            _pending_confirm, _pending_confirm_result, _confirm_lock,
            _current_engines, _current_engines_lock,
            _session_usage, _session_usage_lock,
            _save_session_to_disk,
        ),
        name=f"engine-{sid}",
        daemon=True,
    )
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
    key = params.get("key", "")
    value = params.get("value", "")
    if key == "model" and value:
        # 解析 value: "deepseek-reasoner" 或 "deepseek-reasoner --provider deepseek #tui"
        import re
        model_name = value.split("--provider")[0].strip()
        model_name = re.sub(r"\s+#tui\s*$", "", model_name).strip()
        # 写入 .env
        env_path = os.path.expanduser("~/.bobo/.env")
        try:
            lines = []
            if os.path.exists(env_path):
                with open(env_path) as f:
                    lines = f.readlines()
            found = False
            for i, line in enumerate(lines):
                if line.strip().startswith("API_MODEL_NAME="):
                    lines[i] = f"API_MODEL_NAME={model_name}\n"
                    found = True
                    break
            if not found:
                lines.append(f"API_MODEL_NAME={model_name}\n")
            # 如果 value 中包含 --provider，也更新 BOBO_PROVIDER
            provider_match = re.search(r"--provider\s+(\S+)", value)
            if provider_match:
                prov = provider_match.group(1)
                found_p = False
                for i, line in enumerate(lines):
                    if line.strip().startswith("BOBO_PROVIDER="):
                        lines[i] = f"BOBO_PROVIDER={prov}\n"
                        found_p = True
                        break
                if not found_p:
                    lines.append(f"BOBO_PROVIDER={prov}\n")
            with open(env_path, "w") as f:
                f.writelines(lines)
            return _ok(rid, {"value": model_name, "saved": True})
        except Exception as e:
            return _ok(rid, {"value": value, "error": str(e)})
    return _ok(rid, {"value": value})


@method("config.full")
def handle_config_full(params: dict, rid: str) -> dict:
    return _ok(rid, {
        "config": {
            "display": {
                "streaming": True,
                "show_reasoning": True,
                "tui_compact": False,
                "details_mode": "expanded",
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



@method("slash.exec")
def handle_slash_exec(params: dict, rid: str) -> dict:
    command = params.get("command", "")
    sid = params.get("session_id", "")
    if command == "help":
        return _ok(rid, {"output": "可用命令: /help, /clear, /undo, /tools, /settings, /exit, /sessions"})
    elif command == "clear":
        _emit("session.cleared", sid, {"session_id": sid})
        return _ok(rid, {"output": ""})
    elif command.startswith("undo"):
        # /undo [N|关键词] — 回退对话
        target = command[4:].strip()
        sid = params.get("session_id", "")
        session = _sessions.get(sid)
        if not session:
            return _ok(rid, {"output": "没有活跃的会话"})
        checkpoints = session.get("checkpoints", [])
        if not checkpoints:
            return _ok(rid, {"output": "没有可回退的操作。"})

        # 查找目标快照
        idx = len(checkpoints) - 2  # 默认回退一步
        if target:
            try:
                steps = int(target)
                idx = max(0, len(checkpoints) - 1 - steps)
            except ValueError:
                import os
                for i in range(len(checkpoints) - 1, -1, -1):
                    if target.lower() in checkpoints[i]["label"].lower():
                        idx = i
                        break

        cp = checkpoints[idx]
        session["messages"] = cp["history"]
        session["checkpoints"] = checkpoints[:idx + 1]

        # 恢复文件
        import os
        restored = []
        for path, content in cp.get("files", {}).items():
            try:
                os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                restored.append(os.path.basename(path))
            except Exception:
                pass

        label = cp["label"]
        file_info = f"\n文件已恢复: {', '.join(restored)}" if restored else ""
        return _ok(rid, {"output": f"已回退到: {label}{file_info}"})
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
            f"可用命令:",
            f"  /provider              — 列出所有提供商",
            f"  /provider <名称>       — 切换到指定提供商",
            f"  /model <名称>          — 切换模型",
            f"配置文件位置: ~/.bobo/.env",
        ]
        return _ok(rid, {"output": "\n".join(lines)})
    elif command.startswith("mode"):
        from config import BOBO_PROACTIVE_MODE as _cfg_mode
        arg = command[4:].strip()
        if arg in ("off", "subtle", "full"):
            env_path = os.path.expanduser("~/.bobo/.env")
            try:
                lines = []
                if os.path.exists(env_path):
                    with open(env_path) as f:
                        lines = f.readlines()
                found = False
                key_prefix = "BOBO_PROACTIVE_MODE="
                for i, line in enumerate(lines):
                    if line.startswith(key_prefix):
                        lines[i] = key_prefix + arg + "\n"
                        found = True
                        break
                if not found:
                    lines.append(key_prefix + arg + "\n")
                os.makedirs(os.path.dirname(env_path), exist_ok=True)
                with open(env_path, "w") as f:
                    f.writelines(lines)
                os.environ["BOBO_PROACTIVE_MODE"] = arg
                labels = {"off": "关闭（纯响应）", "subtle": "轻度（静默注入）", "full": "完整（可主动提议）"}
                return _ok(rid, {"output": f"主动模式已设置为: {arg} ({labels.get(arg, '')})\n重启 Bobo 后生效。"})
            except Exception as e:
                return _ok(rid, {"output": f"设置失败: {e}"})
        else:
            labels = {"off": "关闭（纯响应）", "subtle": "轻度（静默注入）", "full": "完整（可主动提议）"}
            current = labels.get(_cfg_mode, _cfg_mode)
            return _ok(rid, {"output": f"当前主动模式: {_cfg_mode} ({current})\n用法: /mode off|subtle|full"})
    elif command.startswith("provider"):
        from core.provider import PROVIDERS, resolve_provider
        arg = command[8:].strip()
        if arg:
            # 切换提供商
            provider_name = arg.lower()
            if provider_name not in PROVIDERS:
                available = ", ".join(PROVIDERS.keys())
                return _ok(rid, {"output": f"未知提供商: {provider_name}\n可用: {available}"})
            # 写入 .env
            env_path = os.path.expanduser("~/.bobo/.env")
            try:
                lines = []
                if os.path.exists(env_path):
                    with open(env_path) as f:
                        lines = f.readlines()
                # 更新或追加 BOBO_PROVIDER
                found = False
                for i, line in enumerate(lines):
                    if line.strip().startswith("BOBO_PROVIDER="):
                        lines[i] = f"BOBO_PROVIDER={provider_name}\n"
                        found = True
                        break
                if not found:
                    lines.append(f"BOBO_PROVIDER={provider_name}\n")
                # 也写上对应的 API_KEY 占位提示
                p = PROVIDERS[provider_name]
                if p.get("env_key"):
                    key_present = any(line.strip().startswith(p["env_key"] + "=") for line in lines)
                    if not key_present:
                        lines.append(f"# {p['env_key']}=your_api_key_here\n")
                with open(env_path, "w") as f:
                    f.writelines(lines)
                return _ok(rid, {"output": f"已切换到提供商: {provider_name}\n重启 Bobo 后生效。\n如果尚未配置 API 密钥，请编辑 ~/.bobo/.env 添加 {PROVIDERS[provider_name].get('env_key', '')}"})
            except Exception as e:
                return _ok(rid, {"output": f"写入 .env 失败: {e}"})
        else:
            # 列出所有提供商
            current = resolve_provider()["name"]
            lines = ["可用提供商:"]
            for name, p in PROVIDERS.items():
                marker = "*" if name == current else " "
                models = ", ".join(p.get("models", []) or ["(自定义)"])
                lines.append(f"  {marker} {name} — {models}")
            lines.append("")
            lines.append("切换: /provider <名称>")
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
        # shell=True 仅用于 TUI 斜杠命令，引擎内的 execute_terminal 有安全分级
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
    with _sessions_lock:
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


@method("commands.catalog")
def handle_commands_catalog(params: dict, rid: str) -> dict:
    """返回所有可用命令列表"""
    return _ok(rid, {"commands": _COMMANDS})


@method("project.set_root")
def handle_project_set_root(params: dict, rid: str) -> dict:
    """设置项目根目录，扫描并发射文件树"""
    root = params.get("path", "")
    if not root or not os.path.isdir(root):
        return _err(rid, -32000, "路径不存在或不是目录")
    tree = _scan_directory(root)
    _emit("project.tree", "", {"tree": tree, "root": root})
    # 注入 system 消息到当前会话，通知 Bobo 项目路径
    sid = params.get("session_id", "")
    if sid and sid in _sessions:
        with _sessions_lock:
            session = _sessions.get(sid)
            if session:
                session.setdefault("messages", []).append({
                    "role": "system",
                    "content": f"📁 已导入项目: {root}。问及文件时，优先从该项目目录查找。"
                })
    return _ok(rid, {"root": root, "count": len(tree)})


def _scan_directory(path: str, max_depth: int = 4) -> list:
    """递归扫描目录，返回文件树结构"""
    tree = []
    try:
        for entry in sorted(os.scandir(path), key=lambda e: (not e.is_dir(), e.name)):
            if entry.name.startswith('.'):
                continue
            if len(tree) >= 100:
                break
            if entry.is_dir():
                if max_depth > 0:
                    children = _scan_directory(entry.path, max_depth - 1)
                else:
                    children = []
                tree.append({"name": entry.name, "type": "folder", "children": children})
            else:
                ext = os.path.splitext(entry.name)[1].lower()
                if ext in ('.py', '.js', '.ts', '.jsx', '.tsx', '.html', '.css', '.json', '.md', '.txt', '.c', '.h', '.go', '.rs', '.rb', '.yaml', '.yml', '.toml', '.sh', '.env', '.gitignore', '.cfg', '.ini', '.conf', '.sql', '.java', '.swift', '.kt'):
                    tree.append({"name": entry.name, "type": "file", "path": entry.path})
    except PermissionError:
        pass
    return tree


@method("file.read")
def handle_file_read(params: dict, rid: str) -> dict:
    """读取文件内容（供桌面端插件使用）"""
    filepath = params.get("filepath", "")
    if not filepath:
        return _err(rid, -32000, "缺少 filepath 参数")
    try:
        from tools.read_local_file import execute as read_file
        content = read_file(filepath=filepath, max_chars=10000)
        return _ok(rid, {"content": content})
    except Exception as e:
        return _err(rid, -32000, str(e))


@method("completion")
def handle_completion(params: dict, rid: str) -> dict:
    """Return autocomplete items for the current input."""
    return _ok(rid, {"items": []})


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
