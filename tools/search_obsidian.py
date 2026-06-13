"""搜索 Obsidian 笔记内容"""

TOOL_NAME = "search_obsidian"

def execute(query: str) -> str:
    from .obsidian_tools import search_obsidian_notes
    return search_obsidian_notes(query)

TOOL_FUNC = execute
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": """【用途】在整个 Obsidian 笔记库中搜索包含特定关键词的笔记。
【适用场景】用户问"找一下关于XX的笔记"、"搜索笔记"、"有没有提到XX"、"帮我找找XX"。
【返回】匹配的笔记列表（路径和文件名）。""",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}
    }
}
_check = lambda: bool(__import__('os').environ.get('OBSIDIAN_VAULT', ''))

def register(reg): reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA, check_fn=_check)
