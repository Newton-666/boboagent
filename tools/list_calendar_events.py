"""List calendar events from macOS Calendar via AppleScript."""

import subprocess

TOOL_NAME = "list_calendar_events"


def execute(days: int = 7) -> str:
    """List calendar events for the next N days."""
    script = (
        'tell application "Calendar" to set eventList to '
        'every event of calendar 1 whose start date is greater than '
        '(current date) and start date is less than '
        f'(current date) + {days} * days\n'
        'set output to ""\n'
        'repeat with e in eventList\n'
        'set output to output & summary of e & " [" & '
        'date string of (start date of e) & " " & '
        'time string of (start date of e) & "]" & return\n'
        'end repeat\n'
        'return output'
    )
    try:
        r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=10)
        if r.returncode == 0 and r.stdout.strip():
            items = r.stdout.strip().split('\n')
            return f"📅 未来 {days} 天的事件 ({len(items)} 个):\n" + "\n".join(f"- {item}" for item in items)
        elif r.returncode == 0:
            return f"未来 {days} 天没有日历事件"
        return f"❌ 获取失败: {r.stderr.strip()}"
    except Exception as e:
        return f"❌ 获取失败: {str(e)}"


TOOL_FUNC = execute
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": "查看 macOS 日历中未来 N 天的事件列表。",
        "parameters": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "查看未来几天的事件", "default": 7}
            },
            "required": []
        }
    }
}


def register(reg):
    reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA)
