# memory.py — 票 P0-1：Memory 模块 RPC（六类分组 / 删除 / 改 type）
# 前端 Memory 面板数据源。删除与改 type 均写审计日志（负面通道，P0-5 衔接）。

import logging

from bobo_tui_gateway.server_utils import err, ok

logger = logging.getLogger(__name__)


def handle_memory_list(params: dict, rid: str, ctx) -> dict:
    """memory.list：六类分组 + 统计（供 Memory 面板渲染）。"""
    try:
        from tools.v5_memory import list_memories
        return ok(rid, list_memories())
    except Exception as e:
        logger.warning("memory.list 失败: %s", e, exc_info=True)
        return err(rid, -32000, f"memory.list 失败: {e}")


def handle_memory_delete(params: dict, rid: str, ctx) -> dict:
    """memory.delete：删除条目 + 审计日志。

    reason 校验对齐 delete_entry（absorbed/stale/user_request），前端传
    user_request（用户手动删除）。审计日志写 data/logs/memory_audit.log。
    """
    entry_id = params.get("entry_id")
    if entry_id is None:
        return err(rid, -32000, "缺少 entry_id")
    try:
        from tools.v5_memory import delete_memory
        r = delete_memory(int(entry_id), reason=params.get("reason", "user_request"))
        if "error" in r:
            return err(rid, -32000, r["error"])
        return ok(rid, r)
    except Exception as e:
        logger.warning("memory.delete 失败: %s", e, exc_info=True)
        return err(rid, -32000, f"memory.delete 失败: {e}")


def handle_memory_update(params: dict, rid: str, ctx) -> dict:
    """memory.update：改条目 type（六类枚举校验）+ 审计日志。

    验收 d 需要（改 type 重新分组）。仅允许改 type，文本改动留给 P0-5。
    """
    entry_id = params.get("entry_id")
    new_type = params.get("type")
    if entry_id is None or not new_type:
        return err(rid, -32000, "缺少 entry_id 或 type")
    try:
        from tools.v5_memory import update_memory_type
        r = update_memory_type(int(entry_id), str(new_type))
        if "error" in r:
            return err(rid, -32000, r["error"])
        return ok(rid, r)
    except Exception as e:
        logger.warning("memory.update 失败: %s", e, exc_info=True)
        return err(rid, -32000, f"memory.update 失败: {e}")


def handle_memory_verify_links(params: dict, rid: str, ctx) -> dict:
    """memory.verify_links：指针可达性校验（失效降权/标记）。"""
    try:
        from tools.v5_memory import verify_memory_links
        return ok(rid, verify_memory_links())
    except Exception as e:
        logger.warning("memory.verify_links 失败: %s", e, exc_info=True)
        return err(rid, -32000, f"memory.verify_links 失败: {e}")


def register(reg_method, ctx):
    reg_method("memory.list")(lambda params, rid: handle_memory_list(params, rid, ctx))
    reg_method("memory.delete")(lambda params, rid: handle_memory_delete(params, rid, ctx))
    reg_method("memory.update")(lambda params, rid: handle_memory_update(params, rid, ctx))
    reg_method("memory.verify_links")(lambda params, rid: handle_memory_verify_links(params, rid, ctx))
