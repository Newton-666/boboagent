"""core/steps/sediment_dispatch.py — 沉淀派发房间（票 PERF-1 事故 1 要求 b）。

fire-and-forget：只判"要不要沉淀"，起线程走走廊办事窗口（_dispatch_sedimentation）。
失败只留事件不影响回合（notes.error）。
"""
from core.steps.base import StepContext, StepResult, StepStage


class SedimentDispatchStage(StepStage):
    name = "sediment"

    def run(self, ctx: StepContext) -> StepResult:
        content = ctx.pending_content
        if not content or ctx.proactive_off:
            return StepResult.PASS
        ctx.dispatch_sedimentation(content)
        return StepResult.PASS
