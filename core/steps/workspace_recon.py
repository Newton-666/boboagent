"""core/steps/workspace_recon.py — 收工工作区对账房间（票 L1 + LEDGER-1B）。

RESPONDING 段观察房：有工具轮时经办事窗口取只读 git 实况；对账文本只并入
history（模型写汇报时对账用），不上用户可见终稿。工作区干净 → 空串零注入。
"""
from core.steps.base import StepContext, StepResult, StepStage


class WorkspaceReconStage(StepStage):
    name = "workspace-recon"

    def run(self, ctx: StepContext) -> StepResult:
        if ctx.current_tool_round > 0:
            ctx.recon_text = ctx.fetch_workspace_recon()
        return StepResult.PASS
