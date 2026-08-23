"""core/steps/base.py — 墙的接口：StepContext（简报+办事窗口）+ StepResult + StepStage。

房间（Stage）铁规矩：
- 只读简报（pending_content / task_ledger / 轮次统计），不能直接翻 engine 的抽屉；
- 回话三种：PASS（放行）/ REINJECT（拦下，带消息）/ append_warning（放行附一句）；
- 想动走廊的计数器 → 走白名单办事窗口（记录在案），不直接改；
- 房间出异常由走廊兜底（记 notes.error 后放行，房间故障不卡走廊）。
"""
import enum


class StepResult(enum.Enum):
    PASS = 0             # 放行，叫下一间
    REINJECT = 1         # 拦下：走廊回入口重走一轮（ctx.reinject_msg 带给模型）
    RETRY = 2            # 入口房：空响应重试（depth<2 重试；ctx.error_message 非空则报错收尾）
    VERIFY_REINJECT = 3  # 入口房：验证器命中（history 已注入，走廊仅清态回走）


class StepContext:
    """走廊递给房间的只读简报 + 白名单办事窗口。"""

    def __init__(self, engine):
        self._engine = engine
        self.warnings: list[str] = []         # 附一句（放行但加提醒，走廊最后拼进回复）
        self.reinject_msg: str | None = None  # 拦下时带给模型的话
        self.tool_results: list = None        # EXECUTING 段走廊注入（销账建议房读取）
        self.recon_text: str = ""            # RESPONDING 段观察房产出（对账文本，走廊并入 history）
        self.error_message: str | None = None  # 入口房：空响应耗尽时走廊用作回复内容
        self.final_content: str = ""            # 出口房：终稿组装产出（走廊 notify 用）

    # ── 只读简报 ──
    @property
    def pending_content(self):
        return self._engine._pending_content

    @property
    def pending_tool_calls(self):
        return self._engine._pending_tool_calls

    @property
    def task_ledger(self):
        return self._engine.task_ledger

    @property
    def round_tool_exec_count(self):
        return self._engine._round_tool_exec_count

    @property
    def round_had_write_tool(self):
        return self._engine._round_had_write_tool

    @property
    def sid(self):
        return getattr(self._engine, "sid", "")

    @property
    def last_reasoning(self):
        return getattr(self._engine, "_last_reasoning", "") or ""

    # ── 白名单办事窗口（房间不能直接碰走廊的抽屉）──
    def append_warning(self, text: str) -> None:
        self.warnings.append(text)

    def request_reinjection(self, msg: str) -> None:
        self.reinject_msg = msg

    def ledger_reinject_count(self) -> int:
        return self._engine._ledger_reinject_count

    def inc_ledger_reinject_count(self) -> int:
        self._engine._ledger_reinject_count += 1
        return self._engine._ledger_reinject_count

    def reply_quality_reinject_count(self) -> int:
        return self._engine._reply_quality_reinject_count

    def inc_reply_quality_reinject_count(self) -> int:
        self._engine._reply_quality_reinject_count += 1
        return self._engine._reply_quality_reinject_count

    # ── 台账闸系办事窗口（R4/R5/R6）──
    def auto_active(self) -> bool:
        getter = self._engine._auto_mode_getter
        return getter is not None and bool(getter())

    @property
    def ledger_backfill_suspect(self) -> bool:
        return bool(getattr(self._engine, "_ledger_backfill_suspect", False))

    def ledger_field_issues(self):
        return self._engine._ledger_field_issues()

    def ledger_field_deny_count(self) -> int:
        return self._engine._ledger_field_deny_count

    def inc_ledger_field_deny_count(self) -> int:
        self._engine._ledger_field_deny_count += 1
        return self._engine._ledger_field_deny_count

    @property
    def current_tool_round(self) -> int:
        return self._engine.current_tool_round

    # ── 沉淀派发（R1）──
    @property
    def proactive_off(self) -> bool:
        return getattr(self._engine.proactive, "mode", "off") == "off"

    @property
    def test_mode(self) -> bool:
        return bool(getattr(self._engine, "test_mode", False))

    def dispatch_sedimentation(self, content: str) -> None:
        """办事窗口：起沉淀线程属走廊组织动作，房间只申请。"""
        self._engine._dispatch_sedimentation(content)

    # ── 销账建议（E4）：改历史经办事窗口（COST-7/LEDGER-400：只扩最后一条 user 消息，不插 system）──
    @property
    def current_depth(self) -> int:
        return self._engine.current_depth

    def verifier_check(self, content: str) -> bool:
        """办事窗口：验证器（R3-c）——claims-completion-without-tools 注入。"""
        return self._engine.verifier.check_and_inject(
            self._engine.history, content,
            tool_exec_count=self._engine._round_tool_exec_count,
        )

    def snapshot_ledger(self) -> None:
        """办事窗口：E2 工具环前快照台账基线（O9，_prev_ledger 存走廊侧）。"""
        self._engine._prev_ledger = list(self._engine.task_ledger)

    def sync_ledger_and_eval_suspect(self, tc_names: list) -> None:
        """办事窗口：E3 工具环后同步台账 + 评估补账嫌疑（O8-2）。"""
        try:
            from tools.task_ledger import current_engine_var, _current_ledger
            if current_engine_var.get() is not None:
                self._engine.task_ledger = list(_current_ledger())
        except Exception:
            pass
        if "task_ledger" in tc_names:
            self._engine._ledger_backfill_suspect = self._engine._detect_ledger_backfill(
                self._engine._prev_ledger, tc_names
            )

    def assemble_final_output(self) -> str:
        """办事窗口：终稿组装（E5）——台账尾注/交接/format/思考块在走廊侧执行。"""
        return self._engine._assemble_final_output()

    def fetch_workspace_recon(self) -> str:
        """办事窗口：只读 git 对账（L1），房间不直接跑 shell。"""
        return self._engine._workspace_recon()

    def append_suggestion_to_history(self, text: str) -> None:
        _appended = False
        for _m in reversed(self._engine.history):
            if _m.get("role") == "user":
                _m["content"] = (_m.get("content") or "") + "\n\n" + text
                _appended = True
                break
        if not _appended:
            self._engine.history.append({"role": "system", "content": text})


class StepStage:
    """房间基类：只做判断，通过 ctx 回话。"""

    name = "unnamed"

    def run(self, ctx: StepContext) -> StepResult:
        raise NotImplementedError
