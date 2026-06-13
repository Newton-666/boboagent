"""删除笔记文件"""

TOOL_NAME = "delete_note"

def execute(filename: str) -> str:
    from .obsidian_tools import delete_note
    return delete_note(filename)

TOOL_FUNC = execute
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": """【用途】永久删除笔记文件。此操作不可恢复。
【适用场景】用户明确要求"删除这个笔记"、"清理这个文件"。
【警告】谨慎使用，删除后无法恢复。""",
        "parameters": {"type": "object", "properties": {"filename": {"type": "string"}}, "required": ["filename"]}
    }
}
_check = lambda: bool(__import__('os').environ.get('OBSIDIAN_VAULT', ''))

def register(reg): reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA, check_fn=_check)
