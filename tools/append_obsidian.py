"""追加内容到 Obsidian 笔记（含 inline diff）"""

TOOL_NAME = "append_obsidian"


def execute(filename: str, content: str) -> str:
    """追加内容到已有文件末尾，返回结果含 inline diff。

    委托 file_writer.append_obsidian 执行实际追加，本层负责：
      - 生成 make_inline_diff("", new, filename)——追加段全 + 行
    """
    from .file_writer import append_obsidian as _append

    result = _append(filename, content, auto_backup=True)

    # ── 追加段 diff（纯 + 行） ──
    from core.diff_utils import make_inline_diff
    diff = make_inline_diff("", content, filename)
    if diff:
        result += "\n" + diff

    return result


TOOL_FUNC = execute
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": """【用途】在已有笔记末尾追加新内容，不影响原有内容。
【适用场景】用户要求"补充笔记"、"追加到笔记"、"在笔记后面加上"。
【注意】不会覆盖原有内容。返回结果含 inline diff 显示新增段。""",
        "parameters": {
            "type": "object",
            "properties": {
                "filename": {"type": "string", "description": "要追加内容的笔记文件名"},
                "content": {"type": "string", "description": "要追加到文件末尾的内容"}
            },
            "required": ["filename", "content"]
        }
    }
}
_check = lambda: bool(__import__('os').environ.get('OBSIDIAN_VAULT', ''))


def register(reg):
    reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA, check_fn=_check)
