"""将笔记文件移动到指定的文件夹"""

TOOL_NAME = "move_to_folder"

def execute(source: str, folder: str) -> str:
    from .obsidian_tools import move_to_folder
    return move_to_folder(source, folder)

TOOL_FUNC = execute
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": """【用途】将笔记文件移动到指定的文件夹。
【适用场景】用户要求"把这个笔记移到XX文件夹"。
【参数】source: 源文件名，folder: 目标文件夹名称。""",
        "parameters": {"type": "object", "properties": {"source": {"type": "string"}, "folder": {"type": "string"}}, "required": ["source", "folder"]}
    }
}
_check = lambda: bool(__import__('os').environ.get('OBSIDIAN_VAULT', ''))

def register(reg): reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA, check_fn=_check)
