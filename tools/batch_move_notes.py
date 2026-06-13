"""批量移动多个笔记文件"""

TOOL_NAME = "batch_move_notes"

def execute(filenames: list, destination: str) -> str:
    from tools_legacy import batch_move_notes
    return batch_move_notes(filenames, destination)

TOOL_FUNC = execute
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": """【用途】一次性移动多个笔记文件到指定文件夹。这是整理文件的首选工具。
【适用场景】用户要求"批量移动"、"整理所有XX文件"、"把这些笔记都移到XX文件夹"、"执行整理计划"。
【优势】比多次调用 move_note 更高效，一次性完成所有移动。""",
        "parameters": {"type": "object", "properties": {"filenames": {"type": "array", "items": {"type": "string"}}, "destination": {"type": "string"}}, "required": ["filenames", "destination"]}
    }
}
_check = lambda: bool(__import__('os').environ.get('OBSIDIAN_VAULT', ''))

def register(reg): reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA, check_fn=_check)
