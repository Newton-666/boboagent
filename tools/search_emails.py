"""搜索邮件"""

TOOL_NAME = "search_emails"

def execute(keyword: str) -> str:
    from .email_module import EmailModule
    return EmailModule().search_emails(keyword)

TOOL_FUNC = execute
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": """【用途】在邮件中搜索包含特定关键词的内容。
【适用场景】用户要求"搜索邮件中的XX"、"找一下关于XX的邮件"。""",
        "parameters": {"type": "object", "properties": {"keyword": {"type": "string"}}, "required": ["keyword"]}
    }
}
_check = lambda: __import__('os').path.exists(__import__('os').path.expanduser('~/.bobo/mail.json'))

def register(reg): reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA, check_fn=_check)
