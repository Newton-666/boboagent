"""core/steps/verifier_check.py — 验证器房（票 R3-c）。

THINKING 入口：LLM 声称完成但零工具 → 经办事窗口 check_and_inject（history 注入由
验证器内部完成，走廊仅清态回走）。"干完活正常收尾不误伤"语义保留在 Verifier 内。
"""
from core.steps.base import StepContext, StepResult, StepStage


class VerifierCheckStage(StepStage):
    name = "verifier"

    def run(self, ctx: StepContext) -> StepResult:
        content = ctx.pending_content
        if not content or ctx.pending_tool_calls:
            return StepResult.PASS
        if ctx.verifier_check(content):
            return StepResult.VERIFY_REINJECT
        return StepResult.PASS
