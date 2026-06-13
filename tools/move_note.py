"""移动单个笔记文件"""

TOOL_NAME = "move_note"

def execute(source: str, destination: str) -> str:
    from .obsidian_tools import move_note
    return move_note(source, destination)

TOOL_FUNC = execute
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": """【用途】将单个笔记文件移动到另一个文件夹。
【适用场景】用户要求"移动这个文件"、"把这个笔记归类到XX文件夹"。
【注意】如需批量移动，请使用 batch_move_notes。""",
        "parameters": {"type": "object", "properties": {"source": {"type": "string"}, "destination": {"type": "string"}}, "required": ["source", "destination"]}
    }
}
_check = lambda: bool(__import__('os').environ.get('OBSIDIAN_VAULT', ''))

def register(reg): reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA, check_fn=_check)
