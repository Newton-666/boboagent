"""删除文件夹"""

TOOL_NAME = "delete_folder"

def execute(folder_name: str, force: bool = False) -> str:
    from .obsidian_tools import delete_folder
    return delete_folder(folder_name, force)

TOOL_FUNC = execute
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": """【用途】删除空文件夹。
【适用场景】用户要求"删除文件夹"。
【注意】只能删除空文件夹，force=true 可强制删除非空文件夹。""",
        "parameters": {"type": "object", "properties": {"folder_name": {"type": "string"}, "force": {"type": "boolean"}}, "required": ["folder_name"]}
    }
}
_check = lambda: bool(__import__('os').environ.get('OBSIDIAN_VAULT', ''))

def register(reg): reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA, check_fn=_check)
