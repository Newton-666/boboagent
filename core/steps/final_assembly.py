"""core/steps/final_assembly.py — 出口组装房（E5，票 K v2/AUTO-D/票 P）。

RESPONDING 段：终稿组装（台账尾注 + 交接清单 + format + 思考块展示）。
组装经走廊办事窗口 _assemble_final_output（逻辑在走廊侧，房间只申请产出）。
"""
from core.steps.base import StepContext, StepResult, StepStage


class FinalAssemblyStage(StepStage):
    name = "final-assembly"

    def run(self, ctx: StepContext) -> StepResult:
        return StepResult.PASS
