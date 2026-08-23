"""core/steps/ledger_sync.py — 台账同步+补账嫌疑评估房间（票 K v2/L + O8-2）。

EXECUTING 中段房：工具环后同步 task_ledger（线程上下文回填）+ 重评补账嫌疑。
必须早于历史落账与销账建议执行（时序铁律）。
"""
from core.steps.base import StepContext, StepResult, StepStage


class LedgerSyncStage(StepStage):
    name = "ledger-sync"

    def run(self, ctx: StepContext) -> StepResult:
        tcs = ctx.pending_tool_calls or []
        ctx.sync_ledger_and_eval_suspect(
            [tc.get("function", {}).get("name", "") for tc in tcs]
        )
        return StepResult.PASS
