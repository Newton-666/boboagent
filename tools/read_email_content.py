"""读取指定邮件的完整内容"""

TOOL_NAME = "read_email_content"

def execute(index: int = 1) -> str:
    from .email_module import EmailModule
    return EmailModule().read_email_content(index)

TOOL_FUNC = execute
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": """【用途】读取指定邮件的完整正文内容。
【适用场景】用户说"看看第一封邮件的内容"、"这封邮件说了什么"。
【注意】需要先知道邮件序号（从 read_recent 获取）。""",
        "parameters": {"type": "object", "properties": {"index": {"type": "integer"}}, "required": []}
    }
}
_check = lambda: __import__('os').path.exists(__import__('os').path.expanduser('~/.bobo/mail.json'))

def register(reg): reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA, check_fn=_check)
