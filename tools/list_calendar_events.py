"""列出日历事件"""

TOOL_NAME = "list_calendar_events"

def execute(days: int = 30) -> str:
    from tools_legacy import list_calendar_events
    return list_calendar_events(days)

TOOL_FUNC = execute
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": """【用途】列出未来一段时间内的日历事件。
【适用场景】用户问"最近有什么安排"、"看看日程"、"今天有什么计划"。
【参数】days: 查询未来多少天，默认30天。""",
        "parameters": {"type": "object", "properties": {"days": {"type": "integer"}}, "required": []}
    }
}
def register(reg): reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA)
