"""core/steps/empty_retry.py — 空响应重试房（THINKING 入口）。

flash/reasoning 模型 token 耗尽返回空 → 重试一次（depth<2）；两次仍空 → 明确报错收尾。
控制流房间：只判结果，走廊执行重试/报错动作（动 current_depth 属走廊组织动作）。
"""
from core.steps.base import StepContext, StepResult, StepStage

_ERROR_MSG = (
    "模型返回了空响应。可能原因：\n"
    "  - reasoning 模型的思考过程耗尽了 max_tokens（可调高 BOBO_MAX_TOKENS 环境变量）\n"
    "  - temperature 设置与模型要求不匹配（reasoning 模型通常需要 temperature=1.0，可设置 BOBO_TEMPERATURE）\n"
    "  - API 暂时异常"
)


class EmptyRetryStage(StepStage):
    name = "empty-retry"

    def run(self, ctx: StepContext) -> StepResult:
        if ctx.pending_content or ctx.pending_tool_calls:
            return StepResult.PASS
        if ctx.current_depth < 2:
            return StepResult.RETRY
        ctx.error_message = _ERROR_MSG
        return StepResult.RETRY
