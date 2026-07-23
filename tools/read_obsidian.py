"""读取 Obsidian 笔记完整内容"""

TOOL_NAME = "read_obsidian"

def execute(filename: str, section: int = 0) -> str:
    from .obsidian_tools import read_obsidian_note
    # LLM 可能传字符串类型，强制转换防止 TypeError
    try:
        section = int(section)
    except (ValueError, TypeError):
        section = 0
    return read_obsidian_note(filename, section)

TOOL_FUNC = execute
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": """【用途】读取并返回 Obsidian 笔记的完整内容。
【适用场景】用户问"帮我看看这个笔记写了什么"、"打开某某笔记"、"笔记里有没有提到XX"。
【注意】此工具只读取，不修改任何文件。长文会分章节（8000 字/章），返回章节索引和摘要。""",
        "parameters": {"type": "object", "properties": {
            "filename": {"type": "string", "description": "Obsidian 笔记的文件名（含 .md 扩展名或不含均可）"},
            "section": {"type": "integer", "description": "章节编号（长文分章后指定读取第几章），0 表示全文或摘要"}
        }, "required": ["filename"]}
    }
}
_check = lambda: bool(__import__('os').environ.get('OBSIDIAN_VAULT', ''))

def register(reg): reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA, check_fn=_check)
