"""获取当前日期和时间"""

from datetime import datetime

TOOL_NAME = "get_current_time"

def execute(format: str = "full") -> str:
    now = datetime.now()
    if format == "date":
        return now.strftime("%Y-%m-%d")
    elif format == "time":
        return now.strftime("%H:%M:%S")
    elif format == "weekday":
        return now.strftime("%A")
    else:
        return now.strftime("%Y-%m-%d %H:%M:%S")

TOOL_FUNC = execute
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": """【用途】获取当前日期和时间。
【适用场景】用户问"现在几点"、"今天几号"、"今天是星期几"、"当前时间"。
【参数】format: 输出格式，可选 full(完整)/date(日期)/time(时间)/weekday(星期)""",
        "parameters": {"type": "object", "properties": {"format": {"type": "string", "enum": ["full", "date", "time", "weekday"]}}, "required": []}
    }
}
def register(reg): reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA)
