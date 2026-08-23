"""core/steps/auto_suggest.py — 全绿销账建议房间（票 L1，建议性可推翻）。

EXECUTING 段观察房：检测 run_tests 全绿强完成信号 → 经办事窗口把建议追加到
最后一条 user 消息（COST-7/LEDGER-400：不插 system 消息防 DeepSeek 400）。
只建议不改账（铁律：台账由模型执笔）。
"""
import re

from core.event_bus import event_bus
from core.steps.base import StepContext, StepResult, StepStage

_ALL_GREEN = re.compile(r"\d+\s+passed")
_ANY_FAIL = re.compile(r"[1-9]\d*\s+failed")


class AutoSuggestStage(StepStage):
    name = "auto-suggest"

    def run(self, ctx: StepContext) -> StepResult:
        if not ctx.tool_results or not ctx.task_ledger:
            return StepResult.PASS
        pending_cnt = sum(1 for e in ctx.task_ledger if e.get("status") != "done")
        if not pending_cnt:
            return StepResult.PASS
        for _tr in ctx.tool_results:
            if not isinstance(_tr, dict):
                continue
            _c = _tr.get("content") or ""
            if isinstance(_c, list):
                _c = " ".join(str(x.get("text", "")) for x in _c if isinstance(x, dict))
            _c = str(_c)
            if _ALL_GREEN.search(_c) and not _ANY_FAIL.search(_c):
                suggest = (
                    "💡 检测到测试全绿强完成信号（run_tests）。"
                    f"台账仍有 {pending_cnt} 项 pending：若对应工作已由测试"
                    "验证完成，请用 task_ledger update 标 done（带 evidence："
                    "测试数字/文件路径）；否则忽略本条建议（模型可推翻）。"
                )
                ctx.append_suggestion_to_history(suggest)
                event_bus.write("ledger.auto_suggest", {
                    "session_id": ctx.sid,
                    "pending_count": pending_cnt,
                })
                break
        return StepResult.PASS
