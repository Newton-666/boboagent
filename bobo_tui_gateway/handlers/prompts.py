"""handlers/prompts.py — Prompt/命令/讨论 handler（最大的 handler 组）。

包含：审批响应、消息提交、斜杠命令、命令分发、命令目录。
"""

import os
import re
import threading
from datetime import datetime

from bobo_tui_gateway.server_utils import ok, err, emit, write_atomic, get_context_length
from config import BOBO_DATA_DIR


# ── 引擎基础设施（被 handler 和 entry.py 引用）──

def register_engine_thread(t: threading.Thread, active_engine_threads, engine_threads_lock):
    with engine_threads_lock:
        active_engine_threads.append(t)


def shutdown_sessions(ctx):
    """保存所有活跃会话（在信号处理中调用）"""
    from bobo_tui_gateway.handlers import sessions as _sess
    with ctx.sessions_lock:
        for sid in list(ctx.sessions.keys()):
            _sess._save_session_to_disk(sid, ctx)
    # 等待引擎线程完成（最多 3 秒）
    with ctx.engine_threads_lock:
        threads = list(ctx.active_engine_threads)
    for t in threads:
        t.join(timeout=1.0)


def _get_llm_caller(engine_cache):
    if "_llm" not in engine_cache:
        from core.llm_caller import create_llm_caller
        from core.provider import resolve_provider
        from tools import TOOLS_SCHEMA
        # resolve_provider() 实时读取 os.environ，不用 import 时冻结的模块常量
        cfg = resolve_provider()
        engine_cache["_llm"] = create_llm_caller(
            cfg["api_key"], cfg["base_url"], cfg["model"], TOOLS_SCHEMA
        )
    return engine_cache["_llm"]


# ── Handler 函数 ──

def handle_approval_respond(params: dict, rid: str, ctx) -> dict:
    """处理前端的确认响应"""
    sid = params.get("session_id", "")
    choice = params.get("choice", "deny")
    with ctx.confirm_lock:
        event = ctx.pending_confirm.pop(sid, None)
        if event:
            if choice in ("session", "always"):
                ctx.pending_confirm_result[sid] = "all"
            elif choice in ("allow", "once"):
                ctx.pending_confirm_result[sid] = True
            else:
                ctx.pending_confirm_result[sid] = False
            event.set()
    return ok(rid, {"responded": True})


def handle_prompt_submit(params: dict, rid: str, ctx) -> dict:
    sid = params.get("session_id", "")
    text = params.get("text", "")
    if not text:
        return err(rid, -32000, "消息不能为空")

    with ctx.sessions_lock:
        session = ctx.sessions.get(sid)
    if not session:
        return err(rid, -32000, "会话不存在")

    # 审计 #12：上一个请求的 engine 仍在跑时，先中断它，再接受新请求。
    from core.engine_adapter import is_running, cancel
    if is_running(sid):
        cancel(sid)
        import time as _time
        _time.sleep(0.3)
        if is_running(sid):
            return err(rid, -32000, "无法取消上一个请求，请稍后重试")

    # 在后台线程中运行引擎，主线程继续处理 stdin
    from core.engine_adapter import run_engine as _run_engine_adapter

    thread = threading.Thread(
        target=_run_engine_adapter,
        args=(
            sid, session, text, emit,
            lambda: _get_llm_caller(ctx.engine_cache), get_context_length,
            lambda t: register_engine_thread(t, ctx.active_engine_threads, ctx.engine_threads_lock),
            ctx.pending_confirm, ctx.pending_confirm_result, ctx.confirm_lock,
            ctx.current_engines, ctx.current_engines_lock,
            ctx.session_usage, ctx.session_usage_lock,
            ctx.save_session_to_disk,
        ),
        name=f"engine-{sid}",
        daemon=True,
    )
    register_engine_thread(thread, ctx.active_engine_threads, ctx.engine_threads_lock)
    thread.start()

    return ok(rid, {"ok": True})


def handle_slash_exec(params: dict, rid: str, ctx) -> dict:
    import os as _os_module  # 必须在函数顶部，避免 elif 分支里的 import os 导致 UnboundLocalError
    command = params.get("command", "")
    sid = params.get("session_id", "")
    if command == "help":
        return ok(rid, {"output": "可用命令: /help, /clear, /undo, /tools, /settings, /exit, /sessions, /mode, /duo, /bobo-audit, /memory-consolidate\n\n/duo <任务> — 双员模式：A 干活 B 验收；/duo 商讨：<问题> — 双方案辩论出决策清单"})
    elif command == "clear":
        emit("session.cleared", sid, {"session_id": sid})
        return ok(rid, {"output": ""})
    elif command.startswith("undo"):
        # /undo [N|关键词] — 回退对话
        target = command[4:].strip()
        sid = params.get("session_id", "")
        session = ctx.sessions.get(sid)
        if not session:
            return ok(rid, {"output": "没有活跃的会话"})
        checkpoints = session.get("checkpoints", [])
        if not checkpoints:
            return ok(rid, {"output": "没有可回退的操作。"})

        # 查找目标快照
        idx = len(checkpoints) - 2  # 默认回退一步
        if target:
            try:
                steps = int(target)
                idx = max(0, len(checkpoints) - 1 - steps)
            except ValueError:
                for i in range(len(checkpoints) - 1, -1, -1):
                    if target.lower() in checkpoints[i]["label"].lower():
                        idx = i
                        break

        cp = checkpoints[idx]
        session["messages"] = cp["history"]
        session["checkpoints"] = checkpoints[:idx + 1]

        # 恢复文件
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
        return ok(rid, {"output": f"已回退到: {label}{file_info}"})
    elif command == "tools":
        from tools import TOOLS_SCHEMA
        names = [t.get("function", t).get("name", "") for t in TOOLS_SCHEMA]
        return ok(rid, {"output": "可用工具:\n  " + "\n  ".join(names)})
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
        return ok(rid, {"output": "\n".join(lines)})
    elif command == "memory-consolidate":
        """后台合并：识别重复/相似记忆，合并内容，归档低分草稿。从不删除。"""
        try:
            from tools.v5_memory import get_all, _save, _write_lock
            data = get_all()
            entries = data.get("entries", [])
            if len(entries) < 3:
                return ok(rid, {"output": f"只有 {len(entries)} 条记忆，不需要合并。"})
            # 按文本相似度分组（共享词占比 > 60% 视为重复）
            merged = 0
            archived = 0
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
            return ok(rid, {"output": "\n".join(lines)})
        except Exception as e:
            return ok(rid, {"output": f"合并失败: {e}"})
    elif command == "bobo-audit" or command.startswith("bobo-audit "):
        import json as _aj
        log_path = str(BOBO_DATA_DIR / "access_log.jsonl")
        arg = command[11:].strip()  # "bobo-audit 20" → "20"
        limit = 50
        if arg and arg.isdigit():
            limit = int(arg)
        try:
            audit_lines = []
            if os.path.exists(log_path):
                with open(log_path, "r", encoding="utf-8") as f:
                    audit_lines = f.readlines()
            recent = audit_lines[-limit:]
            if not recent:
                return ok(rid, {"output": "暂无审计记录。Bobo 还没有执行过任何工具调用。"})
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
            return ok(rid, {"output": "\n".join(output_lines)})
        except Exception as e:
            return ok(rid, {"output": f"读取审计日志失败: {e}"})
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
                write_atomic(env_path, content)
            except Exception as e:
                return ok(rid, {"output": f"设置失败: {e}"})
            labels = {"off": "关闭", "subtle": "轻量", "full": "完整"}
            return ok(rid, {"output": f"主动模式已设置为: {arg} ({labels.get(arg, '')})\n下次对话生效。"})
        else:
            current = {"off": "关闭", "subtle": "轻量", "full": "完整"}.get(_cfg_mode, _cfg_mode)
            return ok(rid, {"output": f"当前主动模式: {_cfg_mode} ({current})\n用法: /mode off|subtle|full"})
    elif command == "provider" or command.startswith("provider "):
        from core.provider import PROVIDERS, resolve_provider, get_provider
        provider_name = command[8:].strip()
        if provider_name:
            if provider_name not in PROVIDERS:
                available = ", ".join(PROVIDERS.keys())
                return ok(rid, {"output": f"未知提供商: {provider_name}\n可用: {available}"})
            env_path = str(BOBO_DATA_DIR / ".env")
            try:
                lines = []
                if os.path.exists(env_path):
                    with open(env_path, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                found = False
                for i, line in enumerate(lines):
                    if line.strip().startswith("BOBO_PROVIDER="):
                        lines[i] = f"BOBO_PROVIDER={provider_name}\n"
                        found = True
                        break
                if not found:
                    lines.append(f"BOBO_PROVIDER={provider_name}\n")
                # 如果新 provider 需要 key，添加注释提示
                p = PROVIDERS[provider_name]
                has_key_line = False
                env_key = p.get('env_key', '')
                if env_key:
                    for line in lines:
                        if line.strip().startswith(f"{env_key}="):
                            has_key_line = True
                            break
                    if not has_key_line:
                        lines.append(f"# {p['env_key']}=your_api_key_here\n")
                write_atomic(env_path, "".join(lines))
                return ok(rid, {"output": f"已切换到提供商: {provider_name}\n重启 Bobo 后生效。\n如果尚未配置 API 密钥，请编辑 {BOBO_DATA_DIR}/.env 添加 {PROVIDERS[provider_name].get('env_key', '')}"})
            except Exception as e:
                return ok(rid, {"output": f"写入 .env 失败: {e}"})
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
            return ok(rid, {"output": "\n".join(lines)})
    elif command == "duo" or command.startswith("duo "):
        rest = command[3:].strip()
        # 商讨/讨论 → 代码编排（确定性流程，防止模型自演双簧）
        import re as _re
        m = _re.match(r'^(商讨|讨论)[:：]\s*(.+)$', rest, _re.S)
        if m:
            question = m.group(2).strip()
            # 前置检查复用 handle_prompt_submit
            with ctx.sessions_lock:
                session = ctx.sessions.get(sid)
            if not session:
                return err(rid, -32000, "会话不存在")
            from core.engine_adapter import is_running, cancel
            if is_running(sid):
                cancel(sid)
                import time as _time
                _time.sleep(0.3)
                if is_running(sid):
                    return err(rid, -32000, "无法取消上一个请求，请稍后重试")

            from core.duo_orchestrator import run_deliberation
            t = threading.Thread(
                target=run_deliberation,
                args=(question, emit, sid),
                name=f"duo-deliberate-{sid}",
                daemon=True,
            )
            t.start()
            return ok(rid, {"output": f"双员商讨已启动：{question}"})

        # 其他 /duo 用法（实现验收等）→ 维持现状透传 prompt.submit
        text = f"duo {rest}".strip()
        result = handle_prompt_submit(
            {"session_id": sid, "text": text}, rid, ctx)
        if isinstance(result, dict) and result.get("result", {}).get("ok"):
            return ok(rid, {"output": f"双员模式已启动：{text}"})
        return result

    else:
        return ok(rid, {"output": f"未知命令: /{command}"})


def handle_command_dispatch(params: dict, rid: str) -> dict:
    name = params.get("name", "")
    return ok(rid, {"type": "exec", "output": f"执行命令: {name}"})


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


def handle_commands_catalog(params: dict, rid: str) -> dict:
    """返回所有可用命令列表"""
    return ok(rid, {"commands": _COMMANDS})


# ── 注册 ──

def register(reg_method, ctx):
    reg_method("approval.respond")(lambda params, rid: handle_approval_respond(params, rid, ctx))
    reg_method("prompt.submit")(lambda params, rid: handle_prompt_submit(params, rid, ctx))
    reg_method("slash.exec")(lambda params, rid: handle_slash_exec(params, rid, ctx))
    reg_method("command.dispatch")(handle_command_dispatch)
    reg_method("commands.catalog")(handle_commands_catalog)
