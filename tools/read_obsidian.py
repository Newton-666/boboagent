"""读取 Obsidian 笔记完整内容"""

TOOL_NAME = "read_obsidian"

def execute(filename: str) -> str:
    from .obsidian_tools import read_obsidian_note
    return read_obsidian_note(filename)

TOOL_FUNC = execute
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": """【用途】读取并返回 Obsidian 笔记的完整内容。
【适用场景】用户问"帮我看看这个笔记写了什么"、"打开某某笔记"、"笔记里有没有提到XX"。
【注意】此工具只读取，不修改任何文件。""",
        "parameters": {"type": "object", "properties": {"filename": {"type": "string"}}, "required": ["filename"]}
    }
}
_check = lambda: bool(__import__('os').environ.get('OBSIDIAN_VAULT', ''))

def register(reg): reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA, check_fn=_check)
