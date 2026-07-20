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
                emit("tool.complete", sid, {
                    "tool_id": data.get("name", ""),
                    "name": data.get("name", ""),
                    "arguments": data.get("args", {}),
                    "duration": data.get("duration", 0),
                    "result_text": tool_output,
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
                        acc["input"] += input_tokens
                        acc["output"] += output_tokens
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
            set_worker_event_emitter(emit)
        except ImportError:
            pass

        interrupt_event = threading.Event()
        with _running_lock:
            _running[sid] = interrupt_event
        with current_engines_lock:
            current_engines[sid] = interrupt_event

        engine = Engine(llm_caller, execute_tool, callback=on_event, confirm_callback=confirm_callback)
        engine.history = session.get("messages", [])
        engine._checkpoints = session.get("checkpoints", [])
        engine._interrupt_event = interrupt_event
        engine.run(text)

        # 中断后直接退出，不写 stdout、不存 session
        if interrupt_event and interrupt_event.is_set():
            return

        session["checkpoints"] = engine._checkpoints

        if engine.history:
            session["messages"] = engine.history

        save_session_to_disk(sid)

        if engine.state != engine.STATE_ERROR:
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
