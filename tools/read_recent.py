"""读取最近邮件"""

TOOL_NAME = "read_recent"

def execute(limit: int = 5) -> str:
    from .email_module import EmailModule
    return EmailModule().read_recent(limit)

TOOL_FUNC = execute
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": """【用途】读取收件箱中最近的邮件列表（主题+发件人）。
【适用场景】用户问"看看有没有新邮件"、"最近有什么邮件"。
【注意】只读不删，不会修改任何邮件。""",
        "parameters": {"type": "object", "properties": {"limit": {"type": "integer"}}, "required": []}
    }
}
_check = lambda: bool(__import__('os').environ.get('OBSIDIAN_VAULT', ''))

def register(reg): reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA, check_fn=_check)
