"""core/steps/ledger_snapshot.py — 台账基线快照房间（票 O9）。

EXECUTING 前置房：工具环执行前快照台账（补账检测的前提——原 A2 FAIL 根因）。
"""
from core.steps.base import StepContext, StepResult, StepStage


class LedgerSnapshotStage(StepStage):
    name = "ledger-snapshot"

    def run(self, ctx: StepContext) -> StepResult:
        ctx.snapshot_ledger()
        return StepResult.PASS
