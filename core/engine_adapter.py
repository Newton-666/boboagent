"""Engine 适配层 — 隔离 server.py 与 engine.py 的直接耦合

server.py 通过此模块调用 engine，不直接 import Engine 类。
"""

import os
import threading
import time as _time

# 运行中引擎的注册表（sid → interrupt_event）
_running: dict[str, threading.Event] = {}
_running_lock = threading.Lock()


def cancel(sid: str):
    """请求中断指定会话的 engine 执行。"""
    with _running_lock:
        event = _running.get(sid)
    if event:
        event.set()
        # 票 W：cancel 通道必须留痕（无声死亡案的头号嫌疑通道）
        try:
            from core.event_bus import event_bus as _ebus
            _ebus.write("engine.cancel.requested", {"session_id": sid})
        except Exception:
            pass


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
    auto_mode: dict,  # 票 A：会话级 AUTO MODE 开关（/auto 翻转，放 ctx）
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

        # ── 票 M：回合边界追踪 / 心跳 / 回合小结 ──
        _turn_start = [0.0]         # 首事件时间戳，0=未启动
        _tool_calls = [0]           # 本轮工具调用计数
        _unique_tools = set()       # 本轮去重工具名
        _last_event_ts = [_time.time()]  # 末次事件时间戳
        _hb_sec = int(os.environ.get("BOBO_TUI_HEARTBEAT_SEC", "15"))
        _hb_stop = threading.Event()

        def on_event(event_type, data):
            _last_event_ts[0] = _time.time()
            if _turn_start[0] == 0.0:
                _turn_start[0] = _time.time()
            if event_type == "thinking":
                msg = data.get("message", "")
                if msg:
                    emit("status.update", sid, {
                        "kind": data.get("phase", ""),
                        "text": msg,
                        "session_id": sid,
                    })
            elif event_type == "tool_call":
                _tool_calls[0] += 1
                _unique_tools.add(data.get("name", ""))
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

        # ── 票 LN-1：bobo 启动时 MEMORY.md → JSON 导入（md 比 JSON 新才解析）──
        # 失败保守降级：解析不了就跳过，绝不污染 knowledge_base.json。
        try:
            from tools.memory_mirror import import_from_md
            import_from_md()
        except Exception:
            pass

        # ── 票 HR-1：启动补报——缺昨天的健康日报则生成（零 LLM 纯统计）──
        # 失败静默降级：报告生成失败记 WARNING，绝不影响启动。
        try:
            from tools.health_report import ensure_report
            ensure_report()
        except Exception:
            pass

        engine = Engine(llm_caller, execute_tool, callback=on_event, confirm_callback=confirm_callback,
                        auto_mode_getter=lambda: auto_mode.get(sid, False))
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
        # ── 票 W：引擎线程生死登记（无声死亡案的摄像头） ──
        # exit 事件必达（finally），reason 穷举：completed / interrupted /
        # exception:<type>。再发生线程蒸发，这里一定有遗言。
        from core.event_bus import event_bus as _ebus
        _thread_t0 = _time.time()
        try:
            _ebus.write("engine.thread.start", {"session_id": sid})
        except Exception:
            pass

        # ── 票 M：心跳 daemon（引擎存活时每 N 秒推送"仍在工作"）──
        def _hb_loop():
            while not _hb_stop.wait(_hb_sec):
                _idle = _time.time() - _last_event_ts[0]
                if _idle >= _hb_sec and _turn_start[0] > 0:
                    _elapsed = _time.time() - _turn_start[0]
                    emit("status.update", sid, {
                        "kind": "heartbeat",
                        "text": f"仍在工作 · 已运行 {_elapsed:.0f}s",
                        "session_id": sid,
                    })
        _hb_thread = threading.Thread(target=_hb_loop, daemon=True)
        _hb_thread.start()

        _exit_reason = "unknown"
        try:
            engine.run(text)
            _exit_reason = "interrupted" if (interrupt_event and interrupt_event.is_set()) else getattr(engine, '_exit_reason', 'completed')
        except Exception as _run_exc:
            _exit_reason = f"exception:{type(_run_exc).__name__}"
            raise
        finally:
            try:
                _ebus.write("engine.thread.exit", {
                    "session_id": sid,
                    "reason": _exit_reason,
                    "duration_ms": int((_time.time() - _thread_t0) * 1000),
                })
            except Exception:
                pass

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

        # ── 票 M：回合小结 + 退出标记（覆盖 message.complete 的 "ready"）──
        _hb_stop.set()  # 停止心跳 daemon
        _elapsed = _time.time() - _turn_start[0] if _turn_start[0] > 0 else 0

        # 构建回合小结文案
        _summary_parts = []
        if _tool_calls[0] > 0:
            _summary_parts.append(f"工具调用 {_tool_calls[0]} 次")
            if _unique_tools:
                _summary_parts.append(f"工具: {', '.join(sorted(_unique_tools))}")
        if engine.task_ledger:
            _done = sum(1 for t in engine.task_ledger if t.get("status") == "done")
            _total = len(engine.task_ledger)
            _summary_parts.append(f"台账 {_done}/{_total} done")

        _summary_text = None
        if _summary_parts:
            _summary_text = f"耗时 {_elapsed:.0f}s · " + " · ".join(_summary_parts)
        if _exit_reason != "completed":
            _exit_label = _exit_reason.replace("exception:", "⚠️ 异常:")
            emit("status.update", sid, {
                "kind": "turn_exit",
                "text": f"引擎退出: {_exit_label}",
                "session_id": sid,
            })
        elif not result_text[0].strip():
            # 用户 2026-07-29：收工汇报由 LLM 自己用自然语言交底（系统提示
            # "收工汇报"节），机械统计行降级为兜底——只在回合没有任何收尾
            # 话语（异常中断、空回复）时才出现。
            if _summary_text:
                emit("status.update", sid, {
                    "kind": "turn_summary",
                    "text": f"回合完成 · {_summary_text}",
                    "session_id": sid,
                })
            else:
                emit("status.update", sid, {
                    "kind": "turn_summary",
                    "text": f"回合完成 · 耗时 {_elapsed:.0f}s",
                    "session_id": sid,
                })

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        if interrupt_event and interrupt_event.is_set():
            return  # 用户中断：不 emit error
        logger.exception("prompt.submit 后台线程执行失败")
        emit("error", sid, {"message": str(e), "session_id": sid})
        # ── 票 M：异常路径回合小结 ──
        try:
            _hb_stop.set()
            _elapsed = _time.time() - _turn_start[0] if _turn_start[0] > 0 else 0
            emit("status.update", sid, {
                "kind": "turn_summary",
                "text": f"回合异常 · 耗时 {_elapsed:.0f}s · {str(e)[:120]}",
                "session_id": sid,
            })
        except Exception:
            pass
    finally:
        # 兜底：确保心跳 daemon 停止（票 M）
        try:
            _hb_stop.set()
        except Exception:
            pass
        # 确保 _running 和 current_engines 注册表一定被清理，防止 is_running 永久卡 True
        with _running_lock:
            _running.pop(sid, None)
        with current_engines_lock:
            current_engines.pop(sid, None)
