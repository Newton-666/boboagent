"""重命名笔记文件"""

TOOL_NAME = "rename_note"

def execute(old_name: str, new_name: str) -> str:
    from .obsidian_tools import rename_note
    return rename_note(old_name, new_name)

TOOL_FUNC = execute
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": """【用途】修改笔记文件的名称。
【适用场景】用户要求"重命名"、"改个名字"。
【参数】old_name: 原文件名，new_name: 新文件名。""",
        "parameters": {"type": "object", "properties": {"old_name": {"type": "string"}, "new_name": {"type": "string"}}, "required": ["old_name", "new_name"]}
    }
}
_check = lambda: bool(__import__('os').environ.get('OBSIDIAN_VAULT', ''))

def register(reg): reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA, check_fn=_check)
