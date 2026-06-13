"""Create a calendar event on macOS via AppleScript."""

import subprocess
import shlex

TOOL_NAME = "create_calendar_event"


def execute(summary: str, start_date: str = "", end_date: str = "") -> str:
    if not summary:
        return "请提供事件标题"
    safe_summary = summary.replace('"', '\\"')
    script = (
        f'tell application "Calendar" to tell calendar 1 '
        f'to make new event at end with properties {{summary:"{safe_summary}"}}'
    )
    try:
        r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            return f"✅ 已创建日历事件: {summary}"
        return f"❌ 创建失败: {r.stderr.strip()}"
    except Exception as e:
        return f"❌ 创建失败: {str(e)}"


TOOL_FUNC = execute
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": "在 macOS 日历中创建事件。",
        "parameters": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "事件标题"},
                "start_date": {"type": "string", "description": "开始时间"},
                "end_date": {"type": "string", "description": "结束时间"}
            },
            "required": ["summary"]
        }
    }
}


def register(reg):
    reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA)
