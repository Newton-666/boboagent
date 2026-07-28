"""task_ledger — 任务台账工具（票 K v2）

LLM 的手：创建/更新/查看任务台账。
台账由 Engine 在收工闸中强制执行，不由模型嘴决定是否收工。

用法：
  task_ledger(action="create", items=[{"id": "1", "title": "修复 bug", "status": "pending"}, ...])
  task_ledger(action="update", items=[{"id": "1", "status": "done"}])
  task_ledger(action="list")
"""

import json
import logging
import time

from core.event_bus import event_bus

logger = logging.getLogger("bobo.task_ledger")

TOOL_NAME = "task_ledger"

# ── 台账上限 ──
_MAX_ITEMS = 20
_VALID_STATUSES = {"pending", "in_progress", "done"}

# ── 模块级状态（Engine 在每轮工具执行后同步到 self.task_ledger） ──
_TASK_LEDGER: list[dict] = []


def _validate_item(item: dict) -> str | None:
    """校验单条台账项，返回错误信息或 None。"""
    if not isinstance(item, dict):
        return "每项必须是一个字典"
    if "id" not in item or "title" not in item:
        return "缺少 id 或 title"
    if not isinstance(item["id"], str) or not item["id"].strip():
        return "id 必须为非空字符串"
    if not isinstance(item["title"], str) or not item["title"].strip():
        return "title 必须为非空字符串"
    status = item.get("status", "pending")
    if status not in _VALID_STATUSES:
        return f"status 必须是以下之一: {', '.join(sorted(_VALID_STATUSES))}"
    return None


def _write_event(action: str, item_id: str, title: str, status: str):
    """写 task.check 事件到事件总线。"""
    event_bus.write("task.check", {
        "action": action,
        "item_id": item_id,
        "title": title,
        "status": status,
    })


def _get_ledger() -> list[dict]:
    """返回当前台账（供 Engine 同步用）。"""
    return _TASK_LEDGER


def _set_ledger(ledger: list[dict]):
    """设置模块级台账（供 Engine 恢复用）。"""
    global _TASK_LEDGER
    _TASK_LEDGER = ledger


def execute(action: str = "list", items: list = None) -> str:
    """管理任务台账。

    Args:
        action: "create"（整本替换建账）, "update"（按 id 改 status）, "list"（查账）
        items: 台账项列表，每项格式 {"id": str, "title": str, "status": "pending"|"in_progress"|"done"}
               create 时必填；update 时传要更新的项（至少含 id + status）；list 时忽略。
    """
    global _TASK_LEDGER

    if action == "create":
        if not items:
            return "❌ create 操作需要提供 items 参数"
        if not isinstance(items, list):
            return "❌ items 必须是列表"
        if len(items) > _MAX_ITEMS:
            return f"❌ 台账项数不能超过 {_MAX_ITEMS}（当前 {len(items)}）"

        # 逐项校验
        for i, item in enumerate(items):
            err = _validate_item(item)
            if err:
                return f"❌ 第 {i + 1} 项校验失败: {err}"

        # 去重检查：id 必须唯一
        ids = [item["id"] for item in items]
        if len(ids) != len(set(ids)):
            return "❌ 台账项 id 必须唯一"

        # 建账
        _TASK_LEDGER = []
        for item in items:
            entry = {
                "id": item["id"],
                "title": item["title"],
                "status": item.get("status", "pending"),
            }
            _TASK_LEDGER.append(entry)
            _write_event("create", entry["id"], entry["title"], entry["status"])

        summary = ", ".join(f'{e["title"][:20]}({e["status"]})' for e in _TASK_LEDGER)
        return f"✅ 台账已创建（{len(_TASK_LEDGER)} 项）: {summary}"

    elif action == "update":
        if not items:
            return "❌ update 操作需要提供 items 参数"
        if not isinstance(items, list):
            return "❌ items 必须是列表"

        if not _TASK_LEDGER:
            return "❌ 台账为空，无法更新。请先创建台账。"

        updated = []
        not_found = []
        for item in items:
            item_id = item.get("id", "")
            new_status = item.get("status", "")
            if not item_id:
                return "❌ update 每项必须提供 id"
            if new_status not in _VALID_STATUSES:
                return f"❌ status 必须是以下之一: {', '.join(sorted(_VALID_STATUSES))}（收到: {new_status}）"

            found = False
            for entry in _TASK_LEDGER:
                if entry["id"] == item_id:
                    old_status = entry["status"]
                    entry["status"] = new_status
                    _write_event("update", entry["id"], entry["title"], entry["status"])
                    updated.append(f'{entry["title"][:20]}: {old_status} → {new_status}')
                    found = True
                    break
            if not found:
                not_found.append(item_id)

        parts = []
        if updated:
            parts.append(f"✅ 已更新 {len(updated)} 项: {', '.join(updated)}")
        if not_found:
            parts.append(f"⚠️ 未找到: {', '.join(not_found)}")

        # 全 done 提示
        pending = [e for e in _TASK_LEDGER if e["status"] != "done"]
        if not pending:
            parts.append("🎉 所有任务已完成！")
        else:
            parts.append(f"⏳ 剩余 {len(pending)} 项未完成")

        return "\n".join(parts)

    elif action == "list":
        if not _TASK_LEDGER:
            return "📋 台账为空"

        lines = ["📋 任务台账:"]
        for i, entry in enumerate(_TASK_LEDGER, 1):
            icon = {"pending": "⬜", "in_progress": "🔄", "done": "✅"}.get(entry["status"], "⬜")
            lines.append(f"  {i}. {icon} [{entry['id']}] {entry['title'][:40]} ({entry['status']})")

        done_count = sum(1 for e in _TASK_LEDGER if e["status"] == "done")
        lines.append(f"--- {done_count}/{len(_TASK_LEDGER)} done ---")
        return "\n".join(lines)

    else:
        return f"❌ 不支持的操作: {action}（支持: create, update, list）"


TOOL_FUNC = execute
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": "创建、更新、查看任务台账。多步任务开工先建账，完成一项立即销账。引擎会检查台账：未完成项存在时不会收工。",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["create", "update", "list"],
                    "description": "create=整本替换建账, update=按 id 更新 status, list=查看当前台账",
                },
                "items": {
                    "type": "array",
                    "description": "台账项列表。create 时必填（整本替换）；update 时传要更新的项（至少 id+status），只更新匹配 id 的项；list 时忽略。每项格式: {\"id\": str, \"title\": str, \"status\": \"pending\"|\"in_progress\"|\"done\"}",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string", "description": "唯一标识"},
                            "title": {"type": "string", "description": "任务标题"},
                            "status": {"type": "string", "enum": ["pending", "in_progress", "done"], "description": "状态"},
                        },
                        "required": ["id", "title"],
                    },
                },
            },
            "required": ["action"],
        },
    },
}


def register(reg):
    reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA)
