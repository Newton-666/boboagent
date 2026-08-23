"""core/steps/field_gate.py — 台账字段闸房间（票 C + 票 L1 pass-with-note）。

从 engine._step 内联版迁移。auto 模式专用。L1：缺字段不再强制全上下文重跑——
本轮放行 + 执法记录照留（goal_gate.deny + 计数），补正指令随终稿带出。
"""
from core.event_bus import event_bus
from core.steps.base import StepContext, StepResult, StepStage

_GATE_LABEL = "AUTO MODE"


class FieldGateStage(StepStage):
    name = "field-gate"

    def run(self, ctx: StepContext) -> StepResult:
        if not ctx.auto_active():
            return StepResult.PASS
        field_issues = ctx.ledger_field_issues()
        if not field_issues:
            return StepResult.PASS
        ctx.inc_ledger_field_deny_count()
        _parts = "; ".join(
            f'{i["id"]} 缺 {", ".join(i["missing"])}' for i in field_issues
        )
        event_bus.write("goal_gate.deny", {
            "session_id": ctx.sid,
            "reason": "ledger_field_missing",
            "field_issues": field_issues,
            "deny_count": ctx.ledger_field_deny_count(),
            "mode": "pass_with_note",  # L1：本轮放行 + 执法记录照留
        })
        ctx.append_warning(
            f"\n\n⚠️ {_GATE_LABEL} 字段闸记录（第 {ctx.ledger_field_deny_count()} 次，"
            f"本轮放行）：台账 {len(field_issues)} 项缺字段（{_parts}）。"
            "收工汇报需给出补正计划：补齐 verify（怎么算做完/怎么验证）与 done 项的 "
            "evidence（完成证据），或写明卡点转 pending 交接/上报调度员。"
        )
        return StepResult.PASS
