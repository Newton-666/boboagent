"""core/steps/promise_gate.py — 承诺检测房间（票Z 缝2 + 票 R3-d + 熔断）。

从 engine._step 内联版迁移（行为逐字节一致，行为基线 diff=0 验收）。
原共享 _ledger_reinject_count：经 ctx 白名单窗口读写（保持共享语义，防行为漂移；
台账闸搬入后如需拆分计数器，属显式行为变更，另议）。
"""
import re

from core.event_bus import event_bus
from core.steps.base import StepContext, StepResult, StepStage

_COMPLETION_WORDS = {"已完成", "全部完成", "测试通过", "已交付", "已全部完成"}
_PROMISE_RE = re.compile(
    r'(我将|我会|让我|接下来|下一步|稍后|一会|待会).{0,10}(继续|执行|运行|跑|处理|完成|修复|修改|测试)'
    r'|(现在|马上|这就).{0,6}(跑|执行|运行|开始)'
)

_REINJECT_MSG = "检测到未完成的承诺。请继续执行，不要说明、不要道歉，直接继续。"


class PromiseGateStage(StepStage):
    name = "promise"  # 保持原内联版状态原因 "promise re-injection" 逐字节一致

    def run(self, ctx: StepContext) -> StepResult:
        content = ctx.pending_content
        if not content:
            return StepResult.PASS
        if any(w in content for w in _COMPLETION_WORDS):
            return StepResult.PASS
        if not _PROMISE_RE.search(content):
            return StepResult.PASS
        has_pending = any(e.get("status") != "done" for e in ctx.task_ledger)
        if not (has_pending or not ctx.task_ledger):
            return StepResult.PASS
        # 命中：未来时承诺 + 账不平/无账
        event_bus.write("goal_gate.promise_detected", {
            "session_id": ctx.sid,
            "content_snippet": content[:100],
        })
        # 票 R3-d：熔断前开确认通道——施工证据（写类工具/多次工具执行）直接放行
        if ctx.round_had_write_tool or ctx.round_tool_exec_count >= 3:
            event_bus.write("goal_gate.released", {
                "session_id": ctx.sid,
                "reason": "construction_evidence",
                "tool_exec_count": ctx.round_tool_exec_count,
            })
            ctx.append_warning("\n\n⚠️ 施工证据已确认，引擎放行")
            return StepResult.PASS
        # 回注（共享计数器熔断 2 次）
        if ctx.ledger_reinject_count() < 2:
            ctx.inc_ledger_reinject_count()
            ctx.request_reinjection(_REINJECT_MSG)
            return StepResult.REINJECT
        # 熔断上限：放行 + 附一句
        event_bus.write("goal_gate.released", {
            "session_id": ctx.sid,
            "reason": "promise_exhausted",
            "reinject_count": ctx.ledger_reinject_count(),
        })
        ctx.append_warning("\n\n⚠️ 承诺检测达熔断上限，引擎放行")
        return StepResult.PASS
