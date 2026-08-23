"""core/steps/ledger_gate.py — 台账未销账房间（票 K v2 + R3-d + 熔断 + R2a）。

从 engine._step 内联版迁移。无条件运行（不依赖 auto）。共享 _ledger_reinject_count
经 ctx 窗口读写（与承诺房共享 2 次熔断预算，保持原语义）。
"""
from core.event_bus import event_bus
from core.steps.base import StepContext, StepResult, StepStage


class LedgerGateStage(StepStage):
    name = "ledger"  # 保持原内联版状态原因 "ledger re-injection" 逐字节一致

    def run(self, ctx: StepContext) -> StepResult:
        pending_items = [e for e in ctx.task_ledger if e.get("status") != "done"]
        if pending_items:
            # R3-d：施工证据 → 放行 + 附一句
            if ctx.round_had_write_tool or ctx.round_tool_exec_count >= 3:
                pending_titles = ", ".join(
                    f'"{e["title"][:30]}"' for e in pending_items
                )
                event_bus.write("goal_gate.released", {
                    "session_id": ctx.sid,
                    "reason": "construction_evidence",
                    "tool_exec_count": ctx.round_tool_exec_count,
                    "pending_items": len(pending_items),
                })
                ctx.append_warning(
                    f"\n\n⚠️ 施工证据已确认，引擎放行（台账 {len(pending_items)} 项未销账：{pending_titles}）"
                )
                return StepResult.PASS
            # 回注（共享熔断 2 次）
            if ctx.ledger_reinject_count() < 2:
                ctx.inc_ledger_reinject_count()
                titles = ", ".join(f'"{e["title"][:30]}"' for e in pending_items)
                rej_msg = (
                    f"任务台账还有 {len(pending_items)} 项未完成：{titles}。"
                    "请继续执行，不要说明、不要道歉，直接继续。"
                )
                ctx.request_reinjection(rej_msg)
                return StepResult.REINJECT
            # 熔断上限 → 放行 + 附一句 + 事件
            pending_titles = ", ".join(
                f'"{e["title"][:30]}"' for e in pending_items
            )
            ctx.append_warning(f"\n\n⚠️ 台账 {len(pending_items)} 项未销账，引擎放行：{pending_titles}")
            event_bus.write("goal_gate.released", {
                "session_id": ctx.sid,
                "reason": "ledger_exhausted",
                "reinject_count": ctx.ledger_reinject_count(),
                "pending_items": len(pending_items),
            })
            return StepResult.PASS
        # R2a：无账软放行（事件记录，不拦截）
        if not ctx.task_ledger:
            event_bus.write("task.no_ledger", {
                "session_id": ctx.sid,
                "reason": "no ledger (soft limit, R2a)",
                "tool_round": ctx.current_tool_round,
            })
        return StepResult.PASS
