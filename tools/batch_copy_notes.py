"""批量复制多个笔记文件"""

TOOL_NAME = "batch_copy_notes"

def execute(filenames: list, destination: str) -> str:
    from tools_legacy import batch_copy_notes
    return batch_copy_notes(filenames, destination)

TOOL_FUNC = execute
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": """【用途】批量复制多个笔记文件到目标文件夹。
【适用场景】用户要求"复制这几个文件"、"备份这些笔记"。""",
        "parameters": {"type": "object", "properties": {"filenames": {"type": "array", "items": {"type": "string"}}, "destination": {"type": "string"}}, "required": ["filenames", "destination"]}
    }
}
_check = lambda: bool(__import__('os').environ.get('OBSIDIAN_VAULT', ''))

def register(reg): reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA, check_fn=_check)
