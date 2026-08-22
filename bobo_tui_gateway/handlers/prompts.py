"""handlers/prompts.py — Prompt/命令/讨论 handler（最大的 handler 组）。

包含：审批响应、消息提交、斜杠命令、命令分发、命令目录。
"""

import os
import re
import threading
from datetime import datetime

from bobo_tui_gateway.server_utils import ok, err, emit, write_atomic, get_context_length
from config import BOBO_DATA_DIR


# ── 票 O-2：OFFICE 审计（office.guard / office.setup / office.teardown）──

def _audit_office(event: str, detail: str):
    """写 data/office_audit.jsonl 一行（与 office_manager 同文件，事件可串读）。"""
    try:
        import json
        ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        path = BOBO_DATA_DIR / "office_audit.jsonl"
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": ts, "event": event, "detail": detail},
                               ensure_ascii=False) + "\n")
    except Exception:
        pass


# ── 引擎基础设施（被 handler 和 entry.py 引用）──

def register_engine_thread(t: threading.Thread, active_engine_threads, engine_threads_lock):
    with engine_threads_lock:
        active_engine_threads.append(t)


def shutdown_sessions(ctx):
    """保存所有活跃会话并强制退出（在信号处理或 stdin EOF 时调用）。

    不等待引擎线程 join：daemon=True 的线程在进程退出时 OS 自动终止。
    原 thread.join() 导致 engine 阻塞在 requests/SSE 流不返回——
    main thread 永久卡死 → 超时 SIGKILL（退出码 -9）。
    119 个孤儿子进程 = 119 次 join 死锁实证。
    """
    import os as _os
    import logging as _logging

    from bobo_tui_gateway.handlers import sessions as _sess

    _logged = _logging.getLogger(__name__)

    # 1. 保存所有活跃会话到磁盘
    with ctx.sessions_lock:
        sids = list(ctx.sessions.keys())
    for sid in sids:
        _sess._save_session_to_disk(sid, ctx)

    # 2. 验证落盘（崩溃案的教训：存盘半截比不存更危险）
    mgr = _sess._get_session_mgr()
    for sid in sids:
        session_path = mgr.session_dir / f"{sid}.json"
        if not session_path.exists() or session_path.stat().st_size == 0:
            _logged.error("shutdown: 会话 %s 落盘验证失败", sid)

    # 3. 刷新缓冲区
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    except Exception:
        pass

    # 4. 跳过 engine 线程 join，直接 os._exit 兜底
    _os._exit(0)


def _get_llm_caller(engine_cache):
    if "_llm" not in engine_cache:
        from core.llm_caller import create_llm_caller
        from core.provider import get_provider, resolve_provider
        from tools import TOOLS_SCHEMA
        # resolve_provider() 实时读取 os.environ，不用 import 时冻结的模块常量
        cfg = resolve_provider()
        # TICKET-PROVIDER-ADAPTER（COST-1c 特批标记）：传入 provider 协议声明
        # （reasoning/tools），llm_caller 读声明行事——新 provider 纯注册零改代码。
        proto = get_provider(cfg["name"]) or {}
        engine_cache["_llm"] = create_llm_caller(
            cfg["api_key"], cfg["base_url"], cfg["model"], TOOLS_SCHEMA,
            provider_proto=proto,
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


def _cancel_engine_and_wait(sid: str, timeout: float = 3.0) -> bool:
    """中断 sid 的 engine 并轮询等待其退出（最长 timeout 秒）。

    TICKET-AUTO-G3：E-1 中断保进度让引擎退出从"立即 return"变为"先落盘再退出"
    （1-2s），原 0.3s 单次检查窗口配不上新退出时长 → 改为 100ms 轮询，
    引擎消失立即放行；超过 timeout 仍运行 → 返回 False（调用方保留原报错兜底）。
    引擎本来没在运行 → 不进等待逻辑，立即返回 True（零回归路径）。
    """
    import time as _time
    from core.engine_adapter import is_running, cancel

    if not is_running(sid):
        return True
    cancel(sid)
    deadline = _time.monotonic() + timeout
    while _time.monotonic() < deadline:
        if not is_running(sid):
            return True
        _time.sleep(0.1)
    return not is_running(sid)


def handle_prompt_submit(params: dict, rid: str, ctx) -> dict:
    sid = params.get("session_id", "")
    text = params.get("text", "")
    _img = params.get("image")  # TICKET-VISION-CHAT-UPLOAD：可选图片 base64 data URL
    if not text and not _img:
        return err(rid, -32000, "消息不能为空")

    # COST-1b：记录用户输入长度（度量层只观测；message.start 事件不带 prompt 内容）
    try:
        from bobo_tui_gateway.metrics import metrics_sink
        metrics_sink.record_user_prompt(sid, text)
    except Exception:
        pass

    with ctx.sessions_lock:
        session = ctx.sessions.get(sid)
    if not session:
        return err(rid, -32000, "会话不存在")

    # ── 票 DESK-P1：前端随 prompt.submit 下发 project_root（会话级）──
    # None/空串=默认现状（绝对兼容）；仅显式传入非空路径才落会话元数据。
    # 路径规范化：去除尾部斜杠，避免 /a/b/ 与 /a/b 双形态。
    _pr = params.get("project_root")
    if _pr is not None:
        _pr = str(_pr).strip().rstrip("/") or None
        with ctx.sessions_lock:
            session["project_root"] = _pr

    # 审计 #12：上一个请求的 engine 仍在跑时，先中断它，再接受新请求。
    if not _cancel_engine_and_wait(sid):
        return err(rid, -32000, "无法取消上一个请求，请稍后重试")

    # TICKET-SCAN-L3b：API 直采 —— relay 在等用户话题时，直取本输入
    # TICKET-SCAN-L3c：路由闸 —— 多模式下用户输入 = 发给 pi 的消息，只进 relay，
    # 不启动引擎（bobo 不抢答）。bobo 的回复由 relay 线程显式调引擎产生。
    try:
        from tools.relay_hooks import is_active as _relay_active
        from tools.relay_hooks import push_user_input as _relay_push_user

        if _relay_active(sid):
            _relay_push_user(sid, text)
            return ok(rid, {"ok": True, "relay": True})
    except Exception:
        pass

    # ── TICKET-VISION-CHAT-UPLOAD：图片 → 多模态 user 消息（图+文一条）──
    # 带图：text+image 合成 content list 注入 session 历史；engine 侧 text 传空
    # （避免 engine 再 append 一条 user text 造成重复）。无图：原样 text（绝对兼容）。
    _send_text = text
    if _img:
        from core.provider import resolve_provider, supports_vision
        _cfg = resolve_provider()
        if not supports_vision(_cfg.get("name", ""), _cfg.get("model", "")):
            return err(rid, -32000,
                       f"当前模型 {_cfg.get('model')}（{_cfg.get('name')}）不支持看图，"
                       "请切换 vision 模型（如 deepseek-v4-flash-vision-exp）")
        _st = str(_img).strip()
        if not _st.startswith("data:"):
            _st = "data:image/png;base64," + _st
        _multi = [{"type": "text", "text": text or "请描述这张图片"},
                  {"type": "image_url", "image_url": {"url": _st}}]
        with ctx.sessions_lock:
            session = ctx.sessions.get(sid)
            if session is not None:
                session.setdefault("messages", []).append(
                    {"role": "user", "content": _multi})
        _send_text = ""  # 已注入历史，engine 不重复加 user text

    # 在后台线程中运行引擎，主线程继续处理 stdin
    from core.engine_adapter import run_engine as _run_engine_adapter

    thread = threading.Thread(
        target=_run_engine_adapter,
        args=(
            sid, session, _send_text, emit,
            lambda: _get_llm_caller(ctx.engine_cache), get_context_length,
            lambda t: register_engine_thread(t, ctx.active_engine_threads, ctx.engine_threads_lock),
            ctx.pending_confirm, ctx.pending_confirm_result, ctx.confirm_lock,
            ctx.auto_mode,
            ctx.computer_use_mode,
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
        return ok(rid, {"output": "可用命令: /help, /clear, /clear-handoff, /undo, /tools, /settings, /exit, /sessions, /mode, /duo, /bobo-audit, /memory-consolidate, /auto, /office, /scan, /connect, /disconnect\n\n/duo <任务> — 双员模式：A 干活 B 验收；/duo 商讨：<问题> — 双方案辩论出决策清单\n/auto [on|off] — AUTO MODE：灰名单命令自主决策（纯读放行），/auto 单独使用为翻转\n/office [on|off] — OFFICE MODE：老板专用开关（员工环境拒绝），搭建/收尾走 office_manager 工具\n/scan — 侦查 tmux 内活着的 bobo/pi 并列出候选\n/connect <编号> [轮数] — 连接 /scan 候选对象，建立互传通道（默认 5 轮）\n/disconnect — 断开当前会话的互传通道\n/clear-handoff — 待人工清单清零：水位线推到最新，旧账不再出现"})
    elif command == "clear":
        emit("session.cleared", sid, {"session_id": sid})
        return ok(rid, {"output": ""})
    elif command == "clear-handoff":
        # 票 AUTO-G2：待人工清单清零——水位线推到当前时刻，此前的 auto 拒绝
        # 全部视为"已交接"，下次收工不再列出；拒绝记录本身照记（安全语义不动）。
        import time as _tm
        session = ctx.sessions.get(sid)
        if not session:
            return ok(rid, {"output": "没有活跃的会话"})
        _wm = _tm.time()
        session["handoff_watermark"] = _wm
        try:
            ctx.save_session_to_disk(sid)
        except Exception:
            pass
        return ok(rid, {"output": "待人工清单已清零（水位线推到最新，旧账不再出现）"})
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
    elif command == "auto" or command.startswith("auto "):
        # 票 A：/auto [on|off] — 翻转会话级 AUTO MODE 开关（不打断工作管线）
        arg = command[5:].strip().lower()
        auto_mode = ctx.auto_mode
        if arg == "on":
            auto_mode[sid] = True
        elif arg == "off":
            auto_mode[sid] = False
        else:
            auto_mode[sid] = not auto_mode.get(sid, False)
        state = "开启" if auto_mode.get(sid, False) else "关闭"
        # 票 AUTO-F：AUTO ON 指示走 TUI 底部状态栏（session.auto_state 实时推送），
        # 不再依赖对话流内的大段状态文本；slash 返回保留简短确认。
        emit("session.auto_state", sid, {"session_id": sid, "on": bool(auto_mode.get(sid, False))})
        return ok(rid, {"output": f"AUTO MODE 已{state}（会话级）"})
    elif command == "computer-use" or command.startswith("computer-use "):
        # TICKET-COMPUTER-USE-ROUTE（COST-1b/COST-1c 授权标记）：/computer-use [on|off] — 会话级 computer use 模式开关（复用 /auto）
        arg = command[13:].strip().lower()
        cu_mode = ctx.computer_use_mode
        if arg == "on":
            cu_mode[sid] = True
        elif arg == "off":
            cu_mode[sid] = False
        else:
            cu_mode[sid] = not cu_mode.get(sid, False)
        state = "开启" if cu_mode.get(sid, False) else "关闭"
        emit("session.computer_use_state", sid, {"session_id": sid, "on": bool(cu_mode.get(sid, False))})
        return ok(rid, {"output": f"computer use 模式已{state}（会话级）"})
    elif command == "office" or command.startswith("office "):
        # 票 O-2：/office [on|off] — 会话级 OFFICE MODE 开关（老板专用）。
        # 角色闸：员工环境（BOBO_ROLE=staff|dispatcher）一律拒绝——
        # "/office 全世界只存在于 owner 终端"（票 O-2 最高原则 2）。
        role = os.environ.get("BOBO_ROLE", "").strip().lower()
        if role in ("staff", "dispatcher"):
            _audit_office("office.guard", f"BOBO_ROLE={role} 尝试执行 /office 被拒（员工无此命令）")
            return ok(rid, {"output": "员工没有这个命令（/office 仅限 owner；"
                                      f"当前环境已注入 BOBO_ROLE={role}）"})
        arg = command[7:].strip().lower()
        office_state = ctx.office_state
        cur = dict(office_state.get(sid, {"on": False, "session": None}))
        if arg == "on":
            cur["on"] = True
        elif arg == "off":
            cur["on"] = False
        else:
            cur["on"] = not cur.get("on", False)
        office_state[sid] = cur
        state = "开启" if cur["on"] else "关闭"
        # 票 O2-4：OFFICE 指示走 TUI 底部状态栏（session.office_state 实时推送）
        emit("session.office_state", sid, {"session_id": sid, "on": bool(cur["on"]),
                                           "session": cur.get("session")})
        if cur["on"]:
            guide = ("已进入 OFFICE 模式。告诉我需求：几个人配合、分工、"
                     "几个窗口/几个 office。\n办公室搭建/状态/收尾由 office_manager "
                     "工具完成（launch/status/teardown）；/office off 关闭并走收尾。")
        else:
            # O2-3 收尾：停 relay + 员工 pane 发退出指令 + 审计（session 保留/清理由 owner 决定）
            teardown_note = ""
            if cur.get("session"):
                try:
                    from tools.office_manager import teardown as _om_teardown
                    teardown_note = "\n" + _om_teardown(cur["session"], keep=True)
                except Exception as e:
                    teardown_note = f"\n（收尾执行失败：{e}）"
            guide = f"OFFICE MODE 已关闭（会话级）{teardown_note}"
        return ok(rid, {"output": f"OFFICE MODE 已{state}（会话级）\n{guide}"})
    elif command == "scan":
        """TICKET-SCAN-L3-1: /scan — 侦查 tmux 内活着的 bobo/pi，列出候选。

        复用 tools/agent_scan.py 的识别逻辑（不复制代码）；unknown 一律不列为
        候选（保守策略，误报率=0 红线延续）。候选暂存 ctx.scan_candidates[sid]
        供 /connect 使用。
        """
        try:
            from tools.agent_scan import scan as _agent_scan
            results = _agent_scan()
        except Exception as e:
            return ok(rid, {"output": f"/scan 执行失败: {e}"})
        cands = [r for r in results if r["kind"] in ("bobo", "pi")]
        if not cands:
            return ok(rid, {"output": "未发现可对话对象（tmux 内无 bobo/pi）"})
        ctx.scan_candidates[sid] = cands
        lines = ["检测到以下可对话对象：", ""]
        for i, c in enumerate(cands, 1):
            cwd = c.get("cwd") or "?"
            lstart = c.get("lstart") or "?"
            lines.append(f"{i}. [{c['kind'].upper()}] {c['pane']}")
            lines.append(f"   工作目录: {cwd}")
            lines.append(f"   启动时间: {lstart}")
        lines.append("")
        # TICKET-SCAN-L3b：自我状态行（API 直采 / pane 模式）
        try:
            from tools.agent_connect import find_own_pane as _find_own_pane
            _own = _find_own_pane()
            if _own:
                lines.append(f"当前 bobo：pane 模式（{_own}）")
            else:
                lines.append("当前 bobo：API 直采模式 ✓（无需 tmux）")
        except Exception:
            lines.append("当前 bobo：API 直采模式 ✓（无需 tmux）")
        lines.append("")
        lines.append("连接: /connect <编号> [轮数]   （如 /connect 1 5，默认 5 轮）")
        return ok(rid, {"output": "\n".join(lines)})
    elif command == "connect" or command.startswith("connect "):
        """TICKET-SCAN-L3-2/3/4: /connect <编号> — 确认后建互传通道。

        - 发送前复核（Kimi 补丁③）：verify_pane_identity 重新核验目标 pane，
          身份变化则拒绝并报错；
        - 安全闸：仅向已确认候选 pane 发送（unknown 永不成为目标）；
        - 复用 tools/agent_connect.py 的 relay 线程（pi_relay.py 范式）。
        """
        parts = command.split()
        if len(parts) < 2:
            cands = ctx.scan_candidates.get(sid, [])
            if not cands:
                return ok(rid, {"output": "用法: /connect <编号> [轮数]，请先运行 /scan 获取候选列表"})
            hint = "用法: /connect <编号> [轮数]，候选：" + "、".join(
                f"{i}.{c['kind']}@{c['pane']}" for i, c in enumerate(cands, 1))
            return ok(rid, {"output": hint})
        num = parts[1]
        # TICKET-SCAN-L4-1：显式指定轮数从用户；不带轮数 → None（relay 内按话题复杂度自主评估）
        rounds = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None
        cands = ctx.scan_candidates.get(sid, [])
        if not cands:
            return ok(rid, {"output": "请先运行 /scan 获取候选列表"})
        if not num.isdigit():
            return ok(rid, {"output": "编号必须是数字，如 /connect 1"})
        idx = int(num) - 1
        if idx < 0 or idx >= len(cands):
            return ok(rid, {"output": f"编号超出范围（1-{len(cands)}）"})
        target = cands[idx]

        # 同一会话已有连接在跑 → 拒绝重复连接
        if ctx.relay_links.get(sid):
            return ok(rid, {"output": "本会话已有互传通道在运行，先 /disconnect 断开"})

        # Kimi 补丁③：发送前复核（现在复核一次，发送时 send_safe 还会再复核）
        from tools.agent_connect import verify_pane_identity
        ok_verify, reason = verify_pane_identity(target)
        if not ok_verify:
            return ok(rid, {"output": f"目标 pane 身份已变化，已中止：{reason}"})

        # 建互传通道（后台线程，daemon）
        import threading as _th
        from tools.agent_connect import run_relay_thread

        # TICKET-SCAN-L3c：relay 线程的引擎注入——bobo 接话时显式调引擎
        # （输入=pi 净化回复），用户输入只进 relay，不允许直通引擎。
        def _make_engine_runner(sid, session):
            def _runner(text: str) -> str:
                from core.engine_adapter import run_engine as _run_engine_adapter
                from tools.relay_hooks import poll_bobo_reply as _poll_bobo_reply
                _run_engine_adapter(
                    sid, session, text, emit,
                    lambda: _get_llm_caller(ctx.engine_cache), get_context_length,
                    lambda t: register_engine_thread(t, ctx.active_engine_threads, ctx.engine_threads_lock),
                    ctx.pending_confirm, ctx.pending_confirm_result, ctx.confirm_lock,
                    ctx.auto_mode,
                    ctx.computer_use_mode,
                    ctx.current_engines, ctx.current_engines_lock,
                    ctx.session_usage, ctx.session_usage_lock,
                    ctx.save_session_to_disk,
                )
                # run_engine 跑完时 complete 事件已 push_bobo_reply（relay active），
                # 这里同步取回作为 bobo 回复。
                return _poll_bobo_reply(sid, 0.5) or ""
            return _runner

        session = ctx.sessions.get(sid)
        engine_runner = _make_engine_runner(sid, session) if session else None
        t = _th.Thread(
            target=run_relay_thread,
            args=(sid, target, rounds, emit),
            kwargs={"engine_runner": engine_runner},
            name=f"scan-connect-{sid}",
            daemon=True,
        )
        ctx.relay_links[sid] = {
            "target_pane": target["pane"],
            "target_kind": target["kind"],
            "thread": t,
            "started": datetime.now().isoformat(timespec="seconds"),
        }
        t.start()
        return ok(rid, {"output": f"已连接 {target['kind']}（{target['pane']}），启动 {rounds} 轮互传。在输入框输入话题即可开始。"})
    elif command == "disconnect":
        """TICKET-SCAN-L3: /disconnect — 断开当前会话的互传通道（守护线程无法强杀，标记停止）。"""
        link = ctx.relay_links.pop(sid, None)
        if not link:
            return ok(rid, {"output": "本会话没有活动的互传通道"})
        # TICKET-SCAN-L3b：释放 API 直采数据通道（线程在 finally 也会兜底）
        try:
            from tools.relay_hooks import unregister as _relay_unregister
            _relay_unregister(sid)
        except Exception:
            pass
        return ok(rid, {"output": f"已断开与 {link.get('target_kind')}（{link.get('target_pane')}）的互传（线程将在下一轮循环自然退出）"})
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
            if not _cancel_engine_and_wait(sid):
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
        "/auto": "/auto",
        "/office": "/office",  # TICKET-O2：老板专用 OFFICE 开关
        "/scan": "/scan",
        "/connect": "/connect <编号> [轮数]",
        "/disconnect": "/disconnect",
    }
}

# TICKET-DESK-V2B3：命令面板一句话说明（只加不改——descs 与 commands 并列返回，
# 不动 _COMMANDS 结构；缺说明的命令前端回退用 usage 文本）
_COMMAND_DESC = {
    "/bobo-audit": "运行 bobo 全量审计",
    "/memory-consolidate": "整理长期记忆",
    "/mode": "切换主动模式 off|subtle|full",
    "/help": "显示全部可用命令与用法",
    "/clear": "清除当前对话",
    "/undo": "回退上一步操作（可带 N 或关键词）",
    "/tools": "列出全部工具",
    "/settings": "查看当前配置",
    "/exit": "退出当前会话",
    "/sessions": "列出所有会话",
    "/duo": "双员模式：A 干活 B 验收",
    "/provider": "列出/切换提供商",
    "/auto": "AUTO MODE 开关（单独使用为翻转）",
    "/office": "OFFICE MODE 老板专用开关",
    "/scan": "侦查 tmux 内活着的 bobo/pi",
    "/connect": "连接 /scan 候选对象建立互传",
    "/disconnect": "断开当前互传通道",
}


def handle_commands_catalog(params: dict, rid: str) -> dict:
    """返回所有可用命令列表（commands 结构不变；descs 为 V2B3 新增说明字段）"""
    return ok(rid, {"commands": _COMMANDS, "descs": _COMMAND_DESC})


# ── 注册 ──

def register(reg_method, ctx):
    reg_method("approval.respond")(lambda params, rid: handle_approval_respond(params, rid, ctx))
    reg_method("prompt.submit")(lambda params, rid: handle_prompt_submit(params, rid, ctx))
    reg_method("slash.exec")(lambda params, rid: handle_slash_exec(params, rid, ctx))
    reg_method("command.dispatch")(handle_command_dispatch)
    reg_method("commands.catalog")(handle_commands_catalog)
