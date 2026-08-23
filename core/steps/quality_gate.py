"""core/steps/quality_gate.py — 答复质量房间（票 R2b + R3-b）。

从 engine._step 内联版迁移（行为逐字节一致）。判断便宜（开头词+长度启发式，
不请 LLM）；自持打回计数（经 ctx 窗口，每回合至多 1 次）。
"""
from core.steps.base import StepContext, StepResult, StepStage

_REJECT_MSG = (
    "你的最终回复没有直接回答用户的问题：台账/清单腔过重，或思考里的分析结论"
    "没落到回复上。请先直接回答用户当前问题、把分析结论的实质内容写到回复里，"
    "台账状态只能作为附属段落跟在答复之后，然后收工。"
)


class QualityGateStage(StepStage):
    name = "reply-quality"  # 保持原内联版状态原因 "reply-quality re-injection" 逐字节一致

    def run(self, ctx: StepContext) -> StepResult:
        content = ctx.pending_content
        # 原内联守卫：有草稿 + 本回合未打回过 + 非写类施工 + 工具次数 <3
        if (not content or ctx.reply_quality_reinject_count()
                or ctx.round_had_write_tool or ctx.round_tool_exec_count >= 3):
            return StepResult.PASS
        _len = len(content)
        _stripped = content.strip()
        _quality_hit = False
        # 台账/清单腔：开头即台账段/清单/纯清单腔
        _ledgerish_head = (
            _stripped.startswith("📋")
            or _stripped.startswith("任务台账")
            or _stripped.startswith("待人工执行清单")
            or _stripped.startswith("台账")
            or _stripped.startswith("完成项")
        )
        if _ledgerish_head and _len < 120:
            _quality_hit = True
        # 思考落纸：thinking 分析 ≥60 字但回复 <80 字
        _r = ctx.last_reasoning.strip()
        if not _quality_hit and len(_r) >= 60 and _len < 80:
            _quality_hit = True
        if not _quality_hit:
            return StepResult.PASS
        ctx.inc_reply_quality_reinject_count()
        ctx.request_reinjection(_REJECT_MSG)
        return StepResult.REINJECT
