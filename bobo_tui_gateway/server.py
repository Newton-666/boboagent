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
from bobo_tui_gateway.server_utils import write_atomic as _write_atomic, ok as _ok, err as _err, emit as _emit, get_context_length as _get_context_length
from bobo_tui_gateway.handlers import sessions, configs
from config import BOBO_DATA_DIR

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


# ── 会话持久化包装器（委托给 handlers/sessions.py，用模块级全局构建 ctx）──

def _save_session_to_disk(sid: str):
    """将内存中的会话保存到磁盘（保持旧签名兼容 engine_adapter）。"""
    sessions._save_session_to_disk(sid, _ctx)


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


def method(name: str):
    def wrapper(fn):
        _methods[name] = fn
        return fn
    return wrapper




def _get_llm_caller():
    if "_llm" not in _engine_cache:
        from core.llm_caller import create_llm_caller
        from core.provider import resolve_provider
        from tools import TOOLS_SCHEMA
        # resolve_provider() 实时读取 os.environ，不用 import 时冻结的模块常量
        cfg = resolve_provider()
        _engine_cache["_llm"] = create_llm_caller(
            cfg["api_key"], cfg["base_url"], cfg["model"], TOOLS_SCHEMA
        )
    return _engine_cache["_llm"]




# ── RPC 方法 ──────────────────────────────────────────────────────────












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

    # 审计 #12：上一个请求的 engine 仍在跑时，先中断它，再接受新请求。
    # 之前的行为是直接拒绝——用户看到"发消息没反应"。
    from core.engine_adapter import is_running, cancel
    if is_running(sid):
        cancel(sid)
        import time as _time
        _time.sleep(0.3)  # 给旧线程 300ms 响应中断信号
        if is_running(sid):
            return _err(rid, -32000, "无法取消上一个请求，请稍后重试")

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





# ── Model Picker（TUI 交互式模型切换）──────────────────────────────

@method("model.options")
def handle_model_options(params: dict, rid: str) -> dict:
    """返回所有 provider 及其 model 列表，供 TUI ModelPicker 渲染。
    API key 的检查只读环境变量，不经过 LLM。"""
    from core.provider import PROVIDERS, get_provider
    from config import API_MODEL_NAME, API_KEY

    active_provider_name = os.environ.get("BOBO_PROVIDER", "deepseek")
    providers_out = []

    for slug, cfg in PROVIDERS.items():
        env_key = cfg.get("env_key", "")
        models = cfg.get("models", [])
        # 如果 provider 有 env_key，检查是否已配置
        authenticated = True
        if env_key:
            authenticated = bool(os.environ.get(env_key, ""))

        providers_out.append({
            "name": cfg.get("name", slug),
            "slug": slug,
            "auth_type": "api_key" if env_key else "none",
            "authenticated": authenticated,
            "is_current": slug == active_provider_name,
            "key_env": env_key,
            "models": models,
            "total_models": len(models),
            "warning": "" if authenticated else f"Set {env_key} in {BOBO_DATA_DIR}/.env",
        })

    return _ok(rid, {
        "model": API_MODEL_NAME,
        "provider": active_provider_name,
        "providers": providers_out,
    })


@method("model.save_key")
def handle_model_save_key(params: dict, rid: str) -> dict:
    """保存 API key 到 .env（直接写入，不经过 LLM）。
    前端 ModelPicker 的 key 输入框调用此方法。"""
    slug = params.get("slug", "")
    api_key = params.get("api_key", "")

    if not slug or not api_key:
        return _ok(rid, {"ok": False, "error": "slug and api_key required"})

    from core.provider import PROVIDERS
    cfg = PROVIDERS.get(slug)
    if not cfg:
        return _ok(rid, {"ok": False, "error": f"unknown provider: {slug}"})

    env_key = cfg.get("env_key", "")
    if not env_key:
        return _ok(rid, {"ok": False, "error": f"{slug} does not use an API key"})

    # 原子写入 .env
    env_path = str(BOBO_DATA_DIR / ".env")
    try:
        lines = []
        if os.path.exists(env_path):
            with open(env_path) as f:
                lines = f.readlines()
        found = False
        for i, line in enumerate(lines):
            if line.strip().startswith(f"{env_key}="):
                lines[i] = f"{env_key}={api_key}\n"
                found = True
                break
        if not found:
            lines.append(f"{env_key}={api_key}\n")
        _write_atomic(env_path, "".join(lines))

        # 热生效
        os.environ[env_key] = api_key
        _engine_cache.pop("_llm", None)

        models = cfg.get("models", [])
        return _ok(rid, {"provider": {
            "name": cfg.get("name", slug),
            "slug": slug,
            "auth_type": "api_key",
            "authenticated": True,
            "is_current": os.environ.get("BOBO_PROVIDER", "") == slug,
            "key_env": env_key,
            "models": models,
            "total_models": len(models),
            "warning": "",
        }})
    except Exception as e:
        return _ok(rid, {"ok": False, "error": str(e)})


@method("model.disconnect")
def handle_model_disconnect(params: dict, rid: str) -> dict:
    """移除 provider 的 API key（从 .env 中删除）。"""
    slug = params.get("slug", "")
    if not slug:
        return _ok(rid, {"disconnected": False})

    from core.provider import PROVIDERS
    cfg = PROVIDERS.get(slug)
    if not cfg:
        return _ok(rid, {"disconnected": False})

    env_key = cfg.get("env_key", "")
    if not env_key:
        return _ok(rid, {"disconnected": True})

    env_path = str(BOBO_DATA_DIR / ".env")
    try:
        lines = []
        if os.path.exists(env_path):
            with open(env_path) as f:
                lines = f.readlines()
        lines = [l for l in lines if not l.strip().startswith(f"{env_key}=")]
        _write_atomic(env_path, "".join(lines))

        # 清理环境变量和缓存
        os.environ.pop(env_key, None)
        _engine_cache.pop("_llm", None)

        return _ok(rid, {"disconnected": True})
    except Exception as e:
        return _ok(rid, {"disconnected": False, "error": str(e)})


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
    import os  # 必须在函数顶部，避免 elif 分支里的 import os 导致 UnboundLocalError
    command = params.get("command", "")
    sid = params.get("session_id", "")
    if command == "help":
        return _ok(rid, {"output": "可用命令: /help, /clear, /undo, /tools, /settings, /exit, /sessions, /mode, /duo, /bobo-audit, /memory-consolidate\n\n/duo <任务> — 双员模式：A 干活 B 验收；/duo 商讨：<问题> — 双方案辩论出决策清单"})
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
        from config import API_MODEL_NAME, ACTIVE_PROVIDER, BOBO_PROACTIVE_MODE
        lines = [
            f"Bobo 当前配置:",
            f"  提供商: {ACTIVE_PROVIDER}",
            f"  模型: {API_MODEL_NAME}",
            f"  主动模式: {BOBO_PROACTIVE_MODE}（用 /mode off|subtle|full 切换）",
            f"",
            f"可用命令:",
            f"  /provider              — 列出所有提供商",
            f"  /provider <名称>       — 切换到指定提供商",
            f"  /model <名称>          — 切换模型",
            f"  /mode off|subtle|full  — 切换主动模式",
            f"配置文件位置: {BOBO_DATA_DIR}/.env",
        ]
        return _ok(rid, {"output": "\n".join(lines)})
    elif command == "memory-consolidate":
        """后台合并：识别重复/相似记忆，合并内容，归档低分草稿。从不删除。"""
        try:
            from tools.v5_memory import get_all, bump_signal, _save, _write_lock
            data = get_all()
            entries = data.get("entries", [])
            if len(entries) < 3:
                return _ok(rid, {"output": f"只有 {len(entries)} 条记忆，不需要合并。"})
            # 按文本相似度分组（共享词占比 > 60% 视为重复）
            merged = 0
            archived = 0
            keep = []
            seen = set()
            for i, e1 in enumerate(entries):
                if i in seen:
                    continue
                group = [e1]
                t1 = set(e1.get("text", "").split())
                for j, e2 in enumerate(entries):
                    if j <= i or j in seen:
                        continue
                    t2 = set(e2.get("text", "").split())
                    if t1 and t2:
                        overlap = len(t1 & t2) / max(len(t1), len(t2))
                        if overlap > 0.6:
                            group.append(e2)
                            seen.add(j)
                if len(group) > 1:
                    # 保留最高分的那条，合并文本
                    best = max(group, key=lambda e: e.get("signal_score", 100))
                    merged_texts = [e.get("text", "") for e in group if e != best]
                    best["text"] = best.get("text", "") + "；也即：" + "；".join(merged_texts)[:200]
                    best["signal_score"] = max(e.get("signal_score", 100) for e in group)
                    best["consolidated_from"] = len(group)
                    merged += len(group) - 1
                    for e in group:
                        if e != best:
                            e["archived"] = True
                            e["signal_score"] = 0
                keep.append(e1)
                seen.add(i)
            # 归档低分草稿（signal_score < 20 且 is_draft）
            for e in entries:
                if e.get("is_draft") and e.get("signal_score", 100) < 20 and not e.get("archived"):
                    e["archived"] = True
                    e["signal_score"] = 0
                    archived += 1
            with _write_lock:
                _save(data)
            lines = [f"记忆合并完成：合并 {merged} 条重复记忆，归档 {archived} 条低分草稿。"]
            lines.append(f"当前共 {len([e for e in entries if not e.get('archived')])} 条活跃记忆"
                         f"（总计 {len(entries)} 条含归档）。")
            return _ok(rid, {"output": "\n".join(lines)})
        except Exception as e:
            return _ok(rid, {"output": f"合并失败: {e}"})
    elif command == "bobo-audit" or command.startswith("bobo-audit "):
        import json as _aj
        log_path = str(BOBO_DATA_DIR / "access_log.jsonl")
        arg = command[11:].strip()  # "bobo-audit 20" → "20"
        limit = 50
        if arg and arg.isdigit():
            limit = int(arg)
        try:
            lines = []
            if os.path.exists(log_path):
                with open(log_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
            recent = lines[-limit:]
            if not recent:
                return _ok(rid, {"output": "暂无审计记录。Bobo 还没有执行过任何工具调用。"})
            output_lines = [f"最近 {len(recent)} 条工具调用:",
                            f"{'时间':<20} {'工具':<22} {'参数':<40} {'大小':>8}",
                            "-" * 92]
            for line in recent:
                e = _aj.loads(line)
                ts = e.get("ts", "")[11:19]  # HH:MM:SS
                tool = e.get("tool", "")[:22]
                args = ", ".join(f"{k}={v}" for k, v in e.get("args", {}).items())[:38]
                size = f"{e.get('size', 0):,}B"
                output_lines.append(f"{ts:<20} {tool:<22} {args:<40} {size:>8}")
            return _ok(rid, {"output": "\n".join(output_lines)})
        except Exception as e:
            return _ok(rid, {"output": f"读取审计日志失败: {e}"})
    elif command == "mode" or command.startswith("mode "):
        from config import BOBO_PROACTIVE_MODE as _cfg_mode
        arg = command[4:].strip()  # "mode off" → "off"
        if arg in ("off", "subtle", "full"):
            import re as _mre
            env_path = str(BOBO_DATA_DIR / ".env")
            try:
                if os.path.exists(env_path):
                    with open(env_path, "r", encoding="utf-8") as f:
                        content = f.read()
                else:
                    content = ""
                if _mre.search(r"^BOBO_PROACTIVE_MODE=", content, _mre.MULTILINE):
                    content = _mre.sub(
                        r"^BOBO_PROACTIVE_MODE=.*$",
                        f"BOBO_PROACTIVE_MODE={arg}",
                        content, flags=_mre.MULTILINE
                    )
                else:
                    content = content.rstrip("\n") + f"\nBOBO_PROACTIVE_MODE={arg}\n"
                _write_atomic(env_path, content)
            except Exception as e:
                import traceback, sys
                traceback.print_exc(file=sys.stderr)
                return _ok(rid, {"output": f"设置失败: {e}"})
            os.environ["BOBO_PROACTIVE_MODE"] = arg
            labels = {"off": "关闭（纯响应）", "subtle": "轻度（静默注入）", "full": "完整（可主动提议）"}
            return _ok(rid, {"output": f"主动模式已设置为: {arg} ({labels.get(arg, '')})\n下次对话生效。"})
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
            env_path = str(BOBO_DATA_DIR / ".env")
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
                _write_atomic(env_path, "".join(lines))
                return _ok(rid, {"output": f"已切换到提供商: {provider_name}\n重启 Bobo 后生效。\n如果尚未配置 API 密钥，请编辑 {BOBO_DATA_DIR}/.env 添加 {PROVIDERS[provider_name].get('env_key', '')}"})
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
    elif command == "duo" or command.startswith("duo "):
        rest = command[3:].strip()
        # 商讨/讨论 → 代码编排（确定性流程，防止模型自演双簧）
        import re as _re
        m = _re.match(r'^(商讨|讨论)[:：]\s*(.+)$', rest, _re.S)
        if m:
            question = m.group(2).strip()
            # 前置检查复用 handle_prompt_submit
            with _sessions_lock:
                session = _sessions.get(sid)
            if not session:
                return _err(rid, -32000, "会话不存在")
            from core.engine_adapter import is_running, cancel
            if is_running(sid):
                cancel(sid)
                import time as _time
                _time.sleep(0.3)
                if is_running(sid):
                    return _err(rid, -32000, "无法取消上一个请求，请稍后重试")

            from core.duo_orchestrator import run_deliberation
            t = threading.Thread(
                target=run_deliberation,
                args=(question, _emit, sid),
                name=f"duo-deliberate-{sid}",
                daemon=True,
            )
            t.start()
            return _ok(rid, {"output": f"双员商讨已启动：{question}"})

        # 其他 /duo 用法（实现验收等）→ 维持现状透传 prompt.submit
        text = f"duo {rest}".strip()
        result = handle_prompt_submit(
            {"session_id": sid, "text": text}, rid)
        if isinstance(result, dict) and result.get("result", {}).get("ok"):
            return _ok(rid, {"output": f"双员模式已启动：{text}"})
        return result

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




@method("input.detect_drop")
def handle_input_detect_drop(params: dict, rid: str) -> dict:
    return _ok(rid, {"dropped": False})


_COMMANDS = {
    "canon": {
        "/bobo-audit": "/bobo-audit",
        "/memory-consolidate": "/memory-consolidate",
        "/mode": "/mode",
        "/help": "/help",
        "/clear": "/clear",
        "/undo": "/undo",
        "/tools": "/tools",
        "/settings": "/settings",
        "/exit": "/exit",
        "/sessions": "/sessions",
        "/duo": "/duo",
        "/provider": "/provider",
    }
}


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

class _ServerContext:
    """上下文对象，封装 sessions 状态供 handlers 模块访问。"""
    def __init__(self, sessions_dict, sessions_lock_obj, current_sid_getter, current_sid_setter):
        self.sessions = sessions_dict
        self.sessions_lock = sessions_lock_obj
        self._get_current_sid = current_sid_getter
        self._set_current_sid = current_sid_setter

    def get_current_sid(self):
        return self._get_current_sid()

    def set_current_sid(self, sid):
        self._set_current_sid(sid)


_ctx = _ServerContext(
    _sessions, _sessions_lock,
    lambda: _current_sid,
    lambda v: globals().update({'_current_sid': v}),
)
sessions.register(method, _ctx)
configs.register(method, _engine_cache)


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
