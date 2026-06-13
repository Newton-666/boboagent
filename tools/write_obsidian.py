"""创建或覆盖 Obsidian 笔记"""

TOOL_NAME = "write_obsidian"

def execute(filename: str, content: str) -> str:
    from .file_writer import write_obsidian
    return write_obsidian(filename, content, auto_backup=True)

TOOL_FUNC = execute
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": """【用途】创建新笔记或覆盖已有笔记的完整内容。
【适用场景】用户要求"写个笔记"、"保存这段内容"、"创建新笔记"。
【注意】此工具会覆盖原有内容，如需追加请用 append_obsidian。""",
        "parameters": {"type": "object", "properties": {"filename": {"type": "string"}, "content": {"type": "string"}}, "required": ["filename", "content"]}
    }
}
_check = lambda: bool(__import__('os').environ.get('OBSIDIAN_VAULT', ''))

def register(reg): reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA, check_fn=_check)
