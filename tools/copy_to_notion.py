"""Copy an Obsidian note to a new Notion page."""

import os

TOOL_NAME = "copy_to_notion"


def execute(filepath: str, title: str = "") -> str:
    """Copy an Obsidian note to Notion."""
    # Read the Obsidian file
    filepath = filepath.strip()
    vault = os.environ.get("OBSIDIAN_VAULT", "")
    if not vault:
        return "OBSIDIAN_VAULT 未配置"

    full_path = os.path.join(vault, filepath)
    if not full_path.endswith(".md"):
        # Try with .md
        if os.path.exists(full_path + ".md"):
            full_path = full_path + ".md"

    # 防止路径穿越：读取范围必须限制在 vault 内
    vault_real = os.path.realpath(vault)
    if not os.path.realpath(full_path).startswith(vault_real + os.sep):
        return "❌ 拒绝访问: 路径不在笔记库范围内（路径穿越防护）"

    if not os.path.exists(full_path):
        return f"文件不存在: {filepath}"

    with open(full_path, "r", encoding="utf-8") as f:
        content = f.read()

    if not content.strip():
        return "文件内容为空"

    # Determine title from first heading or filename
    if not title:
        for line in content.split("\n"):
            if line.startswith("# "):
                title = line.lstrip("# ").strip()
                break
        if not title:
            title = os.path.splitext(os.path.basename(full_path))[0]

    # Create Notion page
    from tools.notion_create_page import execute as notion_create
    result = notion_create(title, content)

    if result.startswith("页面已创建"):
        return f"{result}\n内容已从 Obsidian 复制到 Notion: {title}"
    return result


TOOL_FUNC = execute
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": "将 Obsidian 笔记复制到 Notion。Obsidian 专有格式（wikilinks, tags）会降级为纯文本。",
        "parameters": {
            "type": "object",
            "properties": {
                "filepath": {"type": "string", "description": "Obsidian 文件路径（相对 vault 根目录）"},
                "title": {"type": "string", "description": "Notion 页面标题（可选，默认使用文件第一行标题）"}
            },
            "required": ["filepath"]
        }
    }
}

def register(reg):
    reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA)
