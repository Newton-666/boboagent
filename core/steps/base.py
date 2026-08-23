"""core/steps/base.py — 墙的接口：StepContext（简报+办事窗口）+ StepResult + StepStage。

房间（Stage）铁规矩：
- 只读简报（pending_content / task_ledger / 轮次统计），不能直接翻 engine 的抽屉；
- 回话三种：PASS（放行）/ REINJECT（拦下，带消息）/ append_warning（放行附一句）；
- 想动走廊的计数器 → 走白名单办事窗口（记录在案），不直接改；
- 房间出异常由走廊兜底（记 notes.error 后放行，房间故障不卡走廊）。
"""
import enum


class StepResult(enum.Enum):
    PASS = 0      # 放行，叫下一间
    REINJECT = 1  # 拦下：走廊回入口重走一轮（ctx.reinject_msg 带给模型）


class StepContext:
    """走廊递给房间的只读简报 + 白名单办事窗口。"""

    def __init__(self, engine):
        self._engine = engine
        self.warnings: list[str] = []         # 附一句（放行但加提醒，走廊最后拼进回复）
        self.reinject_msg: str | None = None  # 拦下时带给模型的话

    # ── 只读简报 ──
    @property
    def pending_content(self):
        return self._engine._pending_content

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


class StepStage:
    """房间基类：只做判断，通过 ctx 回话。"""

    name = "unnamed"

    def run(self, ctx: StepContext) -> StepResult:
        raise NotImplementedError
