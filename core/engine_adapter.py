"""Engine 适配层 — 隔离 server.py 与 engine.py 的直接耦合

server.py 通过此模块调用 engine，不直接 import Engine 类。
"""

import os
import threading
import time as _time

# 运行中引擎的注册表（sid → interrupt_event）
_running: dict[str, threading.Event] = {}
_running_lock = threading.Lock()

# TICKET-GUI-F9：活引擎实例注册表（sid → Engine 实例）。
# current_engines 存的是 interrupt_event（threading.Event），不是引擎实例；
# resume 忙分支要读"进行中回合"的 history，必须拿到活 Engine 本身。
# 只做只读暴露：get_live_history() 返回 history 浅拷贝，不触碰引擎内部状态。
_live_engines: dict[str, object] = {}
_live_engines_lock = threading.Lock()

# ── 票 VSC-2B：写审批闸门 —— WRITE_TOOLS 白名单（与扩展侧 diffFlow.ts 对齐）──
# 会话开启写审批（session.set_write_approval on:true）后，这些工具在执行前
# 进入 confirm_callback（approval.request）闸门：Accept=allow 继续执行；
# Reject/120s 超时=deny，工具返回拒绝结果，模型自然换方法。
_VSC2B_WRITE_TOOLS = frozenset({"edit_file", "file_operation"})


def _wait_for_confirmation(event: threading.Event, timeout: float = 120) -> bool:
    """等待用户确认（票 B-3 可测化）。

    超时返回 False = 安全默认 deny（auto 下外部不可逆操作无人应答即拒绝，
    不默认放行——v0.6.1 火 2 安全默认）。此行为由测试钉死防回归。
    """
    return event.wait(timeout=timeout)


def cancel(sid: str):
    """请求中断指定会话的 engine 执行。"""
    # 票 INT2：requested 无条件留痕 —— 原实现只在 _running 命中时写，
    # sid 错位/miss 路径完全静默（无声死亡）。现在无论命中与否都记，miss 附注册表快照。
    try:
        from core.event_bus import event_bus as _ebus
        _ebus.write("engine.cancel.requested", {"session_id": sid})
    except Exception:
        pass
    with _running_lock:
        event = _running.get(sid)
        if event is None:
            try:
                from core.event_bus import event_bus as _ebus
                _ebus.write("engine.cancel.miss", {
                    "session_id": sid,
                    "running_sids": sorted(_running.keys()),
                })
            except Exception:
                pass
            return
    try:
        from core.event_bus import event_bus as _ebus
        _ebus.write("engine.cancel.found", {"session_id": sid})
    except Exception:
        pass
    event.set()
    try:
        from core.event_bus import event_bus as _ebus
        _ebus.write("engine.cancel.set", {"session_id": sid})
    except Exception:
        pass


def is_running(sid: str) -> bool:
    """检查指定会话的 engine 是否正在执行。"""
    with _running_lock:
        return sid in _running


def get_live_history(sid: str):
    """TICKET-GUI-F9：只读暴露活引擎的 history 浅拷贝。

    引擎正在跑回合时，session["messages"] 是旧的（回合末才写回），
    resume 忙分支必须读这里才能拿到进行中的用户消息与工具步骤。
    取不到活引擎（竞态窗口/引擎恰好退出）返回 None，调用方回退内存版。
    禁止抛异常打断 resume —— 任何异常都折返 None。
    """
    try:
        with _live_engines_lock:
            engine = _live_engines.get(sid)
        if engine is None:
            return None
        return list(engine.history)
    except Exception:
        return None


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
                # TICKET-SCAN-L3b：API 直采 —— relay 在等 bobo 回复时，直取完整输出
                try:
                    from tools.relay_hooks import is_active as _relay_active
                    from tools.relay_hooks import push_bobo_reply as _relay_push_reply

                    if _relay_active(sid):
                        _relay_push_reply(sid, result_text[0])
                except Exception:
                    pass
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

            # ── 票 VSC-2B：写审批闸门 —— 写审批模式的 approval.request 带
            # tool_name/arguments/reason，供扩展侧（VS Code）按 reason=write_approval
            # 过滤并渲染审批卡（diff 在工具执行前无内容，inline_diff 留空占位）。
            if reason == "write_approval":
                emit("approval.request", sid, {
                    "command": tool_name,
                    "description": f"写文件审批: {tool_name}",
                    "tool_name": tool_name,
                    "arguments": tool_args or {},
                    "inline_diff": "",
                    "reason": "write_approval",
                    "session_id": sid,
                })
            else:
                emit("approval.request", sid, {
                    "command": tool_name,
                    "description": reason,
                    "session_id": sid,
                })

            if not _wait_for_confirmation(event, timeout=120):
                with confirm_lock:
                    pending_confirm.pop(sid, None)
                return False

            with confirm_lock:
                result = pending_confirm_result.pop(sid, False)
            return result

        # ── 票 VSC-2B：写审批闸门（扩展侧激活用）──
        # 写审批开启 + 工具命中 WRITE_TOOLS → 执行前先过 confirm_callback 闸门。
        # _approval_lock 串行化同会话的写审批：并行工具调用时一次只弹一个审批卡，
        # Accept 后下一个才出现（引擎 pending_confirm 按 sid 单槽，覆盖即丢失）。
        # Reject/超时 → 返回拒绝文本，模型收到工具拒绝结果自然换方法（既有引擎语义）。
        _approval_lock = threading.Lock()

        def _guarded_execute(tool_name: str, tool_args: dict) -> str:
            if session.get("write_approval") and tool_name in _VSC2B_WRITE_TOOLS:
                with _approval_lock:
                    allowed = confirm_callback(tool_name, tool_args, "write_approval")
                if not allowed:
                    return f"操作被用户拒绝（write_approval）: {tool_name}，请换一种方法或征得用户同意后再试。"
            return execute_tool(tool_name, tool_args)

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

        engine = Engine(llm_caller, _guarded_execute, callback=on_event, confirm_callback=confirm_callback,
                        auto_mode_getter=lambda: auto_mode.get(sid, False))
        # 会话 ID：gateway 传真实 sid（格式 20260321_153022_a1b2c3），
        # engine.__init__ 已有 boot-{timestamp}-{随机} 兜底
        engine.sid = sid
        # TICKET-GUI-F9：注册活引擎实例（resume 忙分支只读 history 用）。
        # 与 current_engines（interrupt_event）并列维护，互不干扰。
        with _live_engines_lock:
            _live_engines[sid] = engine
        engine.proactive.load_config()
        # ── 票 AUTO-G2：注入会话级"已交接水位线"（None=首回合列全部）──
        engine.handoff_watermark = session.get("handoff_watermark")
        # ── 票 DESK-P1：会话项目根（None=默认现状；前端选项目后经
        # prompt.submit 落 session["project_root"]）──
        engine.project_root = session.get("project_root")
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

        # ── 票 AUTO-E E-1：中断保进度 ──
        # 旧行为：中断即 return，checkpoints/history/ledger 回写 + save_session_to_disk
        # + message.complete 全部跳过 → 本次回合进度（写文件记录/台账/对话）全丢。
        # 新行为：中断与正常完成走同一条回写路径，进度必落盘；仅 final_text 标注。
        _interrupted = bool(interrupt_event and interrupt_event.is_set())

        session["checkpoints"] = engine.checkpoint_mgr.checkpoints

        if engine.history:
            session["messages"] = engine.history

        # ── 票 K v2 + L：台账回写会话 ──
        # task_ledger 工具在 Engine 上下文中已直接修改 engine.task_ledger，
        # 持久化直接取 Engine 实例字段，不再依赖模块级 _get_ledger。
        session["task_ledger"] = list(engine.task_ledger)

        # ── 票 L1：台账持久化独立事件（ledger.persist）──
        # 落盘前发独立事件，md5 复核可区分"台账改动"与"业务改动"；
        # 事件含指纹（items/done/verify/evidence 计数），供对账与审计。
        try:
            import hashlib as _hl
            _led = session["task_ledger"]
            _done = sum(1 for e in _led if isinstance(e, dict) and e.get("status") == "done")
            _v = sum(1 for e in _led if isinstance(e, dict) and (e.get("verify") or "").strip())
            _ev = sum(1 for e in _led if isinstance(e, dict) and (e.get("evidence") or "").strip())
            _fp = _hl.md5(repr(_led).encode("utf-8", "replace")).hexdigest()[:12]
            _ebus.write("ledger.persist", {
                "session_id": sid,
                "items": len(_led),
                "done": _done,
                "with_verify": _v,
                "with_evidence": _ev,
                "fingerprint": _fp,
            })
        except Exception:
            pass  # 审计事件失败不阻塞落盘（事件总线铁律）

        # ── 票 AUTO-G2：已交接水位线回写会话（收工列出新拒绝后水位线推到本回合
        # 最后一条 deny 的 ts；下次收工旧账不再重复糊出）。
        # getattr 防御：外部替身引擎（测试 FakeEngine 等）可能无该属性，静默跳过。
        _new_wm = getattr(engine, "_handoff_last_ts", None) or getattr(engine, "handoff_watermark", None)
        if _new_wm is not None:
            session["handoff_watermark"] = _new_wm

        save_session_to_disk(sid)

        # ── ENG-1：回合小结与心跳停止先于 message.complete ──
        # owner 裁决：message.complete = 回合结束信号，发出后零用户可见事件、
        # 零 LLM/工具调用，状态立即 ready。故心跳必须在此停、回合小结必须在此发，
        # complete 必须是引擎层最后一个 emit（emit 见下方收尾段末尾）。
        _hb_stop.set()  # 停止心跳 daemon（ENG-1：必须在 complete 之前）
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

        # ── ENG-1：message.complete 必须是本回合最后一个 emit ──
        # 无论成功或失败（含中断），都要发射 message.complete 给 TUI（票 AUTO-E
        # Q1 裁决：中断也发——回合必有一个结束事件；TUI 已有 interrupted 抑制逻辑，
        # 发安全）。此前 STATE_ERROR 时跳过了这个事件，TUI 的回合生命周期依赖
        # message.complete / error / interrupt 三者之一来解除 busy 状态。
        emit("message.complete", sid, {
            "session_id": sid,
            "final_text": result_text[0] if not _interrupted else f"{result_text[0]}\n\n*[已中断]*",
            "usage": last_usage[0],
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
        # TICKET-GUI-F9：活引擎实例同步清理（防 get_live_history 读到僵尸引擎）
        with _live_engines_lock:
            _live_engines.pop(sid, None)
