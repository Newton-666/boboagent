"""列出文件夹内容"""

TOOL_NAME = "list_folder"

def execute(folder: str = "") -> str:
    from .obsidian_tools import list_folder
    return list_folder(folder)

TOOL_FUNC = execute
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": """【用途】查看指定文件夹下的所有子文件夹和笔记文件列表。不读取文件内容，只查看结构。
【适用场景】用户问"帮我看看有什么文件夹"、"目录结构是什么"、"列出所有文件"。""",
        "parameters": {"type": "object", "properties": {"folder": {"type": "string"}}, "required": []}
    }
}
_check = lambda: bool(__import__('os').environ.get('OBSIDIAN_VAULT', ''))

def register(reg): reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA, check_fn=_check)
