"""describe_tool — 取件通道（TICKET-E2b · Harness 重构唯一新基建）。

按名返回工具 schema 摘要（description + parameters，截断 ~800 字符），
并在命中时把工具名注册进 engine._extra_tools（会话级只增集合，
与 _session_written_files 同纪律——压缩/塌缩不清空）。

设计意图：LLM 在分类裁剪场景下看不到被裁工具 → 用 describe_tool 取件，
取件即注册 → 下一轮 _get_filtered_tools 把 _extra_tools union 进允许集。
"""

import difflib
import json

from tools import TOOLS_SCHEMA, ALL_TOOLS_SCHEMA

TOOL_NAME = "describe_tool"

# 返回摘要的截断上限（票文要求 ~800 字符）
_SUMMARY_MAX_CHARS = 800


def _find_schema(tool_name: str) -> dict | None:
    """从 TOOLS_SCHEMA 按 function.name 精确查找。

    票 TOOL-PARK-1：仓内工具 schema 不进 TOOLS_SCHEMA（不 advertised），
    但 describe_tool 是它们的取件入口——未命中时回退 ALL_TOOLS_SCHEMA（全量快照）。
    """
    for tool in TOOLS_SCHEMA:
        if tool.get("function", {}).get("name", "") == tool_name:
            return tool
    for tool in ALL_TOOLS_SCHEMA:
        if tool.get("function", {}).get("name", "") == tool_name:
            return tool
    return None


def _build_summary(schema: dict) -> str:
    """组装 schema 摘要：description + parameters 扁平化，截断 ~800 字符。"""
    fn = schema.get("function", {})
    lines = []
    desc = fn.get("description", "")
    if desc:
        lines.append(f"描述: {desc}")
    params = fn.get("parameters", {}) or {}
    props = params.get("properties", {}) or {}
    if props:
        prop_lines = []
        for pname, pmeta in props.items():
            ptype = pmeta.get("type", "?")
            pdesc = (pmeta.get("description", "") or "").strip()
            if pdesc:
                prop_lines.append(f"  {pname} ({ptype}): {pdesc}")
            else:
                prop_lines.append(f"  {pname} ({ptype})")
        lines.append("参数:")
        lines.extend(prop_lines)
    req = params.get("required", [])
    if req:
        lines.append(f"必填: {', '.join(req)}")
    summary = "\n".join(lines)
    if len(summary) > _SUMMARY_MAX_CHARS:
        summary = summary[:_SUMMARY_MAX_CHARS] + "\n…（摘要截断）"
    return summary


def describe_tool(tool_name: str, _engine=None) -> str:
    """按名返回工具 schema 摘要；命中即注册进 engine._extra_tools。

    参数:
        tool_name: 要查询的工具名。
        _engine: 内部路由注入（同 task_ledger 纪律），不暴露给 LLM schema。
    """
    tool_name = (tool_name or "").strip()
    schema = _find_schema(tool_name)

    # 事件字段公共部分（sid 走 getattr 防御，无会话时为空串）
    try:
        sid = getattr(_engine, "sid", "")
    except Exception:
        sid = ""

    if schema is None:
        # 未知名 → difflib 最接近 3 个建议（含仓内工具名，全量去重）
        all_names = sorted({t.get("function", {}).get("name", "")
                            for t in list(TOOLS_SCHEMA) + list(ALL_TOOLS_SCHEMA)})
        suggestions = difflib.get_close_matches(tool_name, all_names, n=3)
        try:
            from core.event_bus import event_bus
            event_bus.write("tool.describe", {
                "sid": sid,
                "tool_name": tool_name,
                "found": False,
                "suggestions": suggestions,
            })
        except Exception:
            pass  # 事件写失败静默降级，不影响工具执行
        if suggestions:
            return f"错误: 未知工具 '{tool_name}'。最接近的建议: {', '.join(suggestions)}"
        return f"错误: 未知工具 '{tool_name}'。没有找到近似工具。"

    # 命中 → 注册进 _extra_tools（会话级只增）
    if _engine is not None:
        try:
            extra = getattr(_engine, "_extra_tools", None)
            if extra is None:
                extra = set()
                _engine._extra_tools = extra
            extra.add(tool_name)
        except Exception:
            pass  # 注册失败不影响返回摘要
    try:
        from core.event_bus import event_bus
        event_bus.write("tool.describe", {
            "sid": sid,
            "tool_name": tool_name,
            "found": True,
        })
    except Exception:
        pass

    return f"工具 {tool_name} 的 schema 摘要:\n{_build_summary(schema)}"


TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": (
            "按名查询任意工具的 schema 摘要（描述 + 参数，约 800 字符）。"
            "适用场景：当前上下文中的工具列表被分类裁剪、你看不到某个工具，"
            "或想了解某个工具的完整参数——调用本工具取件。"
            "取件成功后该工具会被加入后续可调用集合（会话级，压缩不清空）。"
            "若工具名拼写有误，会返回最接近的 3 个建议。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "tool_name": {
                    "type": "string",
                    "description": "要查询的工具名（如 'grep_code'）",
                },
            },
            "required": ["tool_name"],
        },
    },
}


def register(reg):
    reg(TOOL_NAME, describe_tool, TOOL_SCHEMA)
