"""创建文件夹"""

TOOL_NAME = "create_folder"

def execute(folder_name: str) -> str:
    from .obsidian_tools import create_folder
    return create_folder(folder_name)

TOOL_FUNC = execute
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": """【用途】在 Bobo 数据库中创建新文件夹。
【适用场景】用户要求"创建文件夹"、"新建目录"、"建一个分类文件夹"。""",
        "parameters": {"type": "object", "properties": {"folder_name": {"type": "string"}}, "required": ["folder_name"]}
    }
}
_check = lambda: bool(__import__('os').environ.get('OBSIDIAN_VAULT', ''))

def register(reg): reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA, check_fn=_check)
