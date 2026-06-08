"""创建日历事件（Full Calendar 格式）"""

TOOL_NAME = "create_calendar_event"

def execute(user_input: str) -> str:
    from tools_legacy import create_calendar_event
    return create_calendar_event(user_input)

TOOL_FUNC = execute
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": """【用途】根据自然语言描述创建日历事件。
【适用场景】用户要求"帮我记一下XX时间做XX"、"安排一个日程"、"明天下午3点开会"。
【支持】今天、明天、后天、X月X日、X点、下午X点等表达。""",
        "parameters": {"type": "object", "properties": {"user_input": {"type": "string"}}, "required": ["user_input"]}
    }
}
def register(reg): reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA)
