"""core/steps/backfill_gate.py — 补账检测房间（票 O8-2）。

从 engine._step 内联版迁移。auto 模式专用（office 已拆，gate_label 固定 AUTO MODE）。
嫌疑 flag 由 EXECUTING 段设置（经 ctx 只读），本房只判不设。
"""
from core.event_bus import event_bus
from core.steps.base import StepContext, StepResult, StepStage

_GATE_LABEL = "AUTO MODE"


class BackfillGateStage(StepStage):
    name = "ledger-backfill"  # 保持原内联版状态原因 "ledger backfill deny" 语义

    def run(self, ctx: StepContext) -> StepResult:
        if not ctx.auto_active():
            return StepResult.PASS
        if not ctx.ledger_backfill_suspect:
            return StepResult.PASS
        rej_msg = (
            f"{_GATE_LABEL} 收工拒绝（补账检测）：台账 {len(ctx.task_ledger)} 项在本轮"
            "批量创建且全部/大部直接标 done，无中间施工轮次——视为事后补登记。"
            "请用 task_ledger update 将未完成项改为 pending 并列出下一步真实待办"
            "（verify/evidence 按字段闸要求补齐），然后继续。不要说明、不要道歉，直接做。"
        )
        event_bus.write("goal_gate.deny", {
            "session_id": ctx.sid,
            "reason": "ledger_backfill",
            "items": len(ctx.task_ledger),
        })
        ctx.request_reinjection(rej_msg)
        return StepResult.REINJECT
