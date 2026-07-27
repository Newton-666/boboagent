"""创建或覆盖 Obsidian 笔记（含 inline diff）"""

import os

TOOL_NAME = "write_obsidian"


def execute(filename: str, content: str) -> str:
    """写入文件（覆盖模式），返回结果含 inline diff。

    委托 file_writer.write_obsidian 执行实际写入，本层负责：
      - 写前读取旧内容
      - 生成 make_inline_diff(old, new, filename)
    """
    from .file_writer import write_obsidian as _write
    from tools.obsidian_tools import _normalize_path

    # ── 写前读旧内容（用于 diff） ──
    old_content = ""
    try:
        filepath = _normalize_path(filename)
        if isinstance(filepath, str) and not filepath.startswith("__") and os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                old_content = f.read()
    except Exception:
        pass

    result = _write(filename, content, auto_backup=True)

    # ── 附加 inline diff ──
    from core.diff_utils import make_inline_diff
    diff = make_inline_diff(old_content, content, filename)
    if diff:
        result += "\n" + diff

    return result


TOOL_FUNC = execute
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": """【用途】创建新笔记或覆盖已有笔记的完整内容。
【适用场景】用户要求"写个笔记"、"保存这段内容"、"创建新笔记"。
【注意】此工具会覆盖原有内容，如需追加请用 append_obsidian。返回结果含 inline diff 显示改动。""",
        "parameters": {
            "type": "object",
            "properties": {
                "filename": {"type": "string", "description": "要创建或覆盖的笔记文件名"},
                "content": {"type": "string", "description": "要写入的笔记内容"}
            },
            "required": ["filename", "content"]
        }
    }
}
_check = lambda: bool(__import__('os').environ.get('OBSIDIAN_VAULT', ''))


def register(reg):
    reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA, check_fn=_check)
