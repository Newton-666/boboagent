"""提醒工具 - 支持自然语言时间"""

import threading
import time
import re
from datetime import datetime, timedelta

TOOL_NAME = "reminder"

_active_reminders = []


def _escape_applescript(text: str) -> str:
    """转义 AppleScript 字符串中的特殊字符，防止注入"""
    return text.replace('\\', '\\\\').replace('"', '\\"')


def parse_time(text: str) -> tuple:
    text_lower = text.lower()
    now = datetime.now()
    
    if "明天" in text_lower:
        target = now + timedelta(days=1)
        time_match = re.search(r'(\d{1,2})点', text_lower)
        if time_match:
            hour = int(time_match.group(1))
            target = target.replace(hour=hour, minute=0, second=0, microsecond=0)
        else:
            target = target.replace(hour=9, minute=0, second=0, microsecond=0)
        seconds = int((target - now).total_seconds())
        return seconds, target.strftime("%Y-%m-%d %H:%M")
    
    time_match = re.search(r'(\d{1,2})点', text_lower)
    if time_match:
        hour = int(time_match.group(1))
        target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        if target < now:
            target += timedelta(days=1)
        seconds = int((target - now).total_seconds())
        return seconds, target.strftime("%Y-%m-%d %H:%M")
    
    minute_match = re.search(r'(\d+)\s*分钟', text_lower)
    if minute_match:
        seconds = int(minute_match.group(1)) * 60
        return seconds, f"{seconds//60}分钟后"
    
    second_match = re.search(r'(\d+)\s*秒', text_lower)
    if second_match:
        seconds = int(second_match.group(1))
        return seconds, f"{seconds}秒后"
    
    return 5, "5秒后"


def execute(message: str) -> str:
    """设置提醒"""
    seconds, time_desc = parse_time(message)
    
    def remind():
        time.sleep(seconds)
        print(f"\n🔔 提醒: {message}")
        try:
            import subprocess
            safe_msg = _escape_applescript(message)
            subprocess.run(
                ['osascript', '-e', f'display notification "{safe_msg}" with title "Bobo\u63d0\u9192"'],
                capture_output=True,
                timeout=5
            )
        except Exception:
            pass
    
    thread = threading.Thread(target=remind, daemon=True)
    thread.start()
    _active_reminders.append({"message": message, "seconds": seconds})
    
    return f"✅ 已设置提醒: {time_desc}后提醒「{message}」"


def list_reminders() -> str:
    if not _active_reminders:
        return "📭 当前没有活跃的提醒"
    result = f"📋 活跃提醒 ({len(_active_reminders)}个):\n"
    for i, r in enumerate(_active_reminders, 1):
        result += f"  {i}. {r['message']}\n"
    return result


_check = lambda: __import__('sys').platform == 'darwin'

def register(reg):
    reg("set_reminder", execute, {
        "type": "function",
        "function": {
            "name": "set_reminder",
            "description": """【用途】设置**临时提醒**，到时间弹窗通知。

【适用场景】用户要求记住：
- 有时间限制的事情（如"明天开会"、"5分钟后喝水"）
- 待办事项、日程提醒

【不适用场景】用户要求记住：
- 永久性知识（如"Python语法"）→ 请用 save_memory
- 个人偏好（如"我喜欢咖啡"）→ 请用 save_memory

【示例】"提醒我明天下午3点开会" → 设置提醒
       "5分钟后提醒我喝水" → 设置提醒
       "提醒我明天吃西瓜" → 设置提醒

【注意】此工具保存的是**临时提醒**，会过期，不是永久记忆。""",
            "parameters": {"type": "object", "properties": {"message": {"type": "string"}}, "required": ["message"]}
        }
    }, check_fn=_check)
    
    reg("list_reminders", list_reminders, {
        "type": "function",
        "function": {"name": "list_reminders", "description": "列出所有活跃的提醒", "parameters": {"type": "object", "properties": {}, "required": []}}
    }, check_fn=_check)
