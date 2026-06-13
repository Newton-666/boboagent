"""系统通知工具"""

import subprocess

TOOL_NAME = "notification"

NOTIFICATION_TIMEOUT = 5  # 通知超时时间（秒）

def send(title: str, message: str) -> str:
    """发送系统通知"""
    try:
        # 转义双引号，防止破坏 AppleScript 语法
        title_escaped = title.replace('"', '\\"')
        message_escaped = message.replace('"', '\\"')

        subprocess.run(
            ['osascript', '-e', f'display notification "{message_escaped}" with title "{title_escaped}"'],
            capture_output=True,
            timeout=NOTIFICATION_TIMEOUT
        )
        return f"已发送通知: {title}"
    except subprocess.TimeoutExpired:
        return "发送通知超时"
    except:
        return "发送通知失败"

_check = lambda: __import__('sys').platform == 'darwin'

def register(reg):
    reg("send_notification", send, {
        "type": "function",
        "function": {
            "name": "send_notification",
            "description": "发送 macOS 系统通知。适用场景：用户要求'提醒我'、'通知我'。",
            "parameters": {"type": "object", "properties": {"title": {"type": "string"}, "message": {"type": "string"}}, "required": ["title", "message"]}
        }
    }, check_fn=_check)
