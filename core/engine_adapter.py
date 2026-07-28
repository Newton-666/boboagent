"""Engine 适配层 — 隔离 server.py 与 engine.py 的直接耦合

server.py 通过此模块调用 engine，不直接 import Engine 类。
"""

import threading

# 运行中引擎的注册表（sid → interrupt_event）
_running: dict[str, threading.Event] = {}
_running_lock = threading.Lock()


def cancel(sid: str):
    """请求中断指定会话的 engine 执行。"""
    with _running_lock:
        event = _running.get(sid)
    if event:
        event.set()


def is_running(sid: str) -> bool:
    """检查指定会话的 engine 是否正在执行。"""
    with _running_lock:
        return sid in _running


def run_engine(
    sid: str,
    session: dict,
    text: str,
    emit,
    get_llm_caller,
    get_context_length,
    register_engine_thread,
    pending_confirm: dict,
    pending_confirm_result: dict,
    confirm_lock: threading.Lock,
    current_engines: dict,
    current_engines_lock: threading.Lock,
    session_usage: dict,
    session_usage_lock: threading.Lock,
    save_session_to_disk,
):
    """在独立线程中执行 Engine，通过 emit 向桌面端/TUI 发送事件。"""
    interrupt_event = None  # 审计 #20a：提前声明，确保 finally 中可引用
    try:
        from core.engine import Engine
        from core.tool_executor import execute_tool

        llm_caller = get_llm_caller()
        result_text = [""]
        last_usage = [{}]

        def on_event(event_type, data):
            if event_type == "thinking":
                msg = data.get("message", "")
                if msg:
                    emit("status.update", sid, {
                        "kind": data.get("phase", ""),
                        "text": msg,
                        "session_id": sid,
                    })
            elif event_type == "tool_call":
                emit("tool.start", sid, {
                    "tool_id": data.get("name", ""),
                    "name": data.get("name", ""),
                    "arguments": data.get("args", {}),
                    "context": data.get("context", ""),
                    "session_id": sid,
                })
            elif event_type == "tool_result":
                tool_output = data.get("result", "")
                # 提取 inline diff（edit_file 附加在结果末尾的分隔块）
                inline_diff = ""
                if "<<<INLINE_DIFF>>>" in tool_output:
                    tool_output, _, tail = tool_output.partition("<<<INLINE_DIFF>>>")
                    inline_diff, _, _ = tail.partition("<<<END_INLINE_DIFF>>>")
                    tool_output = tool_output.rstrip()
                    inline_diff = inline_diff.strip()
                emit("tool.complete", sid, {
                    "tool_id": data.get("name", ""),
                    "name": data.get("name", ""),
                    "arguments": data.get("args", {}),
                    "duration": data.get("duration", 0),
                    "result_text": tool_output,
                    "inline_diff": inline_diff,
                    "error": "" if data.get("success", True) else (
                        tool_output[:200] if tool_output else "工具执行失败"
                    ),
                    "session_id": sid,
                })
            elif event_type == "complete":
                result_text[0] = data.get("content", "")
                raw = data.get("usage", {})
                if raw:
                    input_tokens = raw.get("prompt_tokens", 0)
                    output_tokens = raw.get("completion_tokens", 0)
                    total = raw.get("total_tokens", 0)
                    with session_usage_lock:
                        acc = session_usage.setdefault(sid, {"input": 0, "output": 0})
                        acc["input"] = input_tokens
                        acc["output"] = output_tokens
                    context_used = acc["input"] + acc["output"]
                    last_usage[0] = {
                        "input": acc["input"],
                        "output": acc["output"],
                        "total": total,
                        "context_max": get_context_length(),
                        "context_used": context_used,
                        "context_percent": round(context_used / get_context_length() * 100, 1),
                    }
            elif event_type == "error":
                emit("gateway.error", sid, {
                    "message": data.get("content", ""),
                    "session_id": sid,
                })
                result_text[0] = data.get("content", "")
            elif event_type == "thinking.delta":
                emit("message.delta", sid, {
                    "text": data.get("text", ""),
                    "session_id": sid,
                })
            elif event_type == "status.update":
                emit("status.update", sid, {
                    "kind": data.get("kind", ""),
                    "text": data.get("text", ""),
                    "session_id": sid,
                })
            elif event_type == "notes.changed":
                emit("notes.changed", sid, {
                    "file": data.get("file", ""),
                    "diff": data.get("diff", ""),
                    "tool": data.get("tool", ""),
                    "session_id": sid,
                })
            elif event_type == "terminal.output":
                emit("terminal.output", sid, {
                    "command": data.get("command", ""),
                    "output": data.get("output", ""),
                    "duration": data.get("duration", 0),
                    "session_id": sid,
                })

        def confirm_callback(tool_name: str, tool_args: dict, reason: str) -> bool:
            event = threading.Event()
            with confirm_lock:
                pending_confirm[sid] = event

            emit("approval.request", sid, {
                "command": tool_name,
                "description": reason,
                "session_id": sid,
            })

            if not event.wait(timeout=120):
                with confirm_lock:
                    pending_confirm.pop(sid, None)
                return False

            with confirm_lock:
                result = pending_confirm_result.pop(sid, False)
            return result

        emit("message.start", sid, {"session_id": sid})

        # 注入 Worker 事件发射器，让 spawn_worker 能实时向 TUI 发进度
        try:
            from tools.spawn_worker import set_worker_event_emitter
            set_worker_event_emitter(emit, sid)
        except ImportError:
            pass

        interrupt_event = threading.Event()
        with _running_lock:
            _running[sid] = interrupt_event
        with current_engines_lock:
            current_engines[sid] = interrupt_event

        engine = Engine(llm_caller, execute_tool, callback=on_event, confirm_callback=confirm_callback)
        # 会话 ID：gateway 传真实 sid（格式 20260321_153022_a1b2c3），
        # engine.__init__ 已有 boot-{timestamp}-{随机} 兜底
        engine.sid = sid
        engine.proactive.load_config()
        # 冲突 #2：不要直接引用 session["messages"]——engine 会原地 append，
        # main 线程同时遍历保存（_save_session_to_disk）会导致丢消息。
        engine.history = list(session.get("messages", []))
        engine.checkpoint_mgr.checkpoints[:] = session.get("checkpoints", [])
        # ── 票 K v2：从会话恢复台账 ──
        engine.task_ledger = list(session.get("task_ledger", []))
        try:
            from tools.task_ledger import _set_ledger
            _set_ledger(engine.task_ledger)
        except Exception:
            pass
        engine._interrupt_event = interrupt_event
        engine.run(text)

        # 中断后直接退出，不写 stdout、不存 session
        if interrupt_event and interrupt_event.is_set():
            return

        session["checkpoints"] = engine.checkpoint_mgr.checkpoints

        if engine.history:
            session["messages"] = engine.history

        # ── 票 K v2 + L：台账回写会话 ──
        # task_ledger 工具在 Engine 上下文中已直接修改 engine.task_ledger，
        # 持久化直接取 Engine 实例字段，不再依赖模块级 _get_ledger。
        session["task_ledger"] = list(engine.task_ledger)

        save_session_to_disk(sid)

        # 无论成功或失败，都要发射 message.complete 给 TUI。
        # 此前 STATE_ERROR 时跳过了这个事件，TUI 的回合生命周期依赖
        # message.complete / error / interrupt 三者之一来解除 busy 状态。
        # gateway.error 事件在 Hermes fork 的 TUI 中没有处理器，被丢弃，
        # 导致 busy 永不解锁 → Bobo 用户看到的"不回复"其实是 TUI 死锁。
        emit("message.complete", sid, {
            "session_id": sid,
            "final_text": result_text[0],
            "usage": last_usage[0],
        })

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        if interrupt_event and interrupt_event.is_set():
            return  # 用户中断：不 emit error
        logger.exception("prompt.submit 后台线程执行失败")
        emit("error", sid, {"message": str(e), "session_id": sid})
    finally:
        # 确保 _running 和 current_engines 注册表一定被清理，防止 is_running 永久卡 True
        with _running_lock:
            _running.pop(sid, None)
        with current_engines_lock:
            current_engines.pop(sid, None)
