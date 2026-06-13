"""分析近期邮件统计"""

TOOL_NAME = "analyze_emails"

def execute(days: int = 7) -> str:
    from .email_module import EmailModule
    return EmailModule().analyze_recent(days)

TOOL_FUNC = execute
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": """【用途】统计分析近期邮件的发送者域名、类型分布等。
【适用场景】用户问"分析一下我的邮件"、"最近谁给我发邮件最多"。""",
        "parameters": {"type": "object", "properties": {"days": {"type": "integer"}}, "required": []}
    }
}
_check = lambda: __import__('os').path.exists(__import__('os').path.expanduser('~/.bobo/mail.json'))

def register(reg): reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA, check_fn=_check)
