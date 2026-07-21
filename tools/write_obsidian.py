"""创建或覆盖 Obsidian 笔记"""

TOOL_NAME = "write_obsidian"

def execute(filename: str, content: str) -> str:
    from .file_writer import write_obsidian
    return write_obsidian(filename, content, auto_backup=True)

TOOL_FUNC = execute
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": """【用途】创建新笔记或覆盖已有笔记的完整内容。
【适用场景】用户要求"写个笔记"、"保存这段内容"、"创建新笔记"。
【注意】此工具会覆盖原有内容，如需追加请用 append_obsidian。

【Obsidian 语法参考 — 写入内容时可用以下特殊语法】
- 标签：文件顶部的 YAML frontmatter 中用 tags: [标签1, 标签2]，或正文中用 #标签名
- 内部链接：[[笔记文件名]] 或 [[笔记文件名|显示文字]]
- Callout 提示框：> [!note] 普通信息 / > [!warning] 警告 / > [!tip] 技巧 / > [!info] 备注
- 高亮：==要强调的文字==
- 嵌入其他笔记：![[笔记名]]
- 待办：- [ ] 未完成 / - [x] 已完成
- 引用：> 引用文字（可嵌套 >>> ）
- 代码块：```语言\n代码\n```
【不需要全部使用，根据用户意图选择合适的即可。】""",
        "parameters": {"type": "object", "properties": {"filename": {"type": "string", "description": "要创建或覆盖的笔记文件名"}, "content": {"type": "string", "description": "要写入的笔记内容"}}, "required": ["filename", "content"]}
    }
}
_check = lambda: bool(__import__('os').environ.get('OBSIDIAN_VAULT', ''))

def register(reg): reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA, check_fn=_check)
