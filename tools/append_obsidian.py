"""追加内容到 Obsidian 笔记"""

TOOL_NAME = "append_obsidian"

def execute(filename: str, content: str) -> str:
    from .file_writer import append_obsidian
    return append_obsidian(filename, content, auto_backup=True)

TOOL_FUNC = execute
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": """【用途】在已有笔记末尾追加新内容，不影响原有内容。
【适用场景】用户要求"补充笔记"、"追加到笔记"、"在笔记后面加上"。
【注意】不会覆盖原有内容。""",
        "parameters": {"type": "object", "properties": {"filename": {"type": "string"}, "content": {"type": "string"}}, "required": ["filename", "content"]}
    }
}
_check = lambda: bool(__import__('os').environ.get('OBSIDIAN_VAULT', ''))

def register(reg): reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA, check_fn=_check)
