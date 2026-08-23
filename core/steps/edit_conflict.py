"""core/steps/edit_conflict.py — 编辑冲突检测房间（审计 #：多编辑同文件同段）。

EXECUTING 段前置房：多个编辑操作命中同一文件 → 拦下（回注 assistant 消息，
走廊执行重走动作）。检测为纯本地解析（JSON 参数 + 文件名聚合），零 LLM。
"""
import json

from core.steps.base import StepContext, StepResult, StepStage

_EDIT_TOOLS = {"edit_file", "file_operation"}


class EditConflictStage(StepStage):
    name = "edit-conflict"

    def run(self, ctx: StepContext) -> StepResult:
        tcs = ctx.pending_tool_calls or []
        if len(tcs) <= 1:
            return StepResult.PASS
        edits_by_file = {}
        conflicts = []
        for tc in tcs:
            fn = tc.get("function", {})
            name = fn.get("name", "")
            if name not in _EDIT_TOOLS:
                continue
            try:
                args = json.loads(fn.get("arguments", "{}")) if isinstance(fn.get("arguments", ""), str) else fn.get("arguments", {})
                path = args.get("file_path", "") or args.get("path", "")
                if path:
                    if path in edits_by_file and edits_by_file[path]:
                        conflicts.append(f"{path}（被多个编辑操作命中）")
                    edits_by_file[path] = edits_by_file.get(path, 0) + 1
            except Exception:
                pass
        if conflicts:
            ctx.request_reinjection(
                f"检测到编辑冲突: {'; '.join(conflicts)}。请调整计划，先改一个文件，结果返回后再改另一个。"
            )
            return StepResult.REINJECT
        return StepResult.PASS
