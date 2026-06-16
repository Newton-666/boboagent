"""Save code decisions and architecture notes to Obsidian vault.

After making code changes, LLM uses this to document what was done and why.
Creates a living knowledge graph of project decisions over time.
"""

import os
import re
from datetime import datetime
from pathlib import Path

TOOL_NAME = "code_to_obsidian"

# Where code knowledge notes live inside the vault
CODE_KNOWLEDGE_FOLDER = "02_Areas/编程"


def _sanitize_filename(name: str) -> str:
    """Turn a project or module name into a safe filename."""
    name = name.strip().replace("/", "-").replace("\\", "-")
    name = re.sub(r"[^\w\-\.\s]", "", name)[:60]
    return name


def execute(project: str, topic: str, content: str,
            tags: str = "", related: str = "") -> str:
    """Save a code decision, design note, or implementation summary to Obsidian.

    Args:
        project: 项目名（如 'bobo-agent'）
        topic: 主题（如 'auth模块', 'API设计', '性能优化'）
        content: 笔记正文（markdown）
        tags: 逗号分隔的标签（如 'auth,jwt,security'）
        related: 关联笔记的 [[wikilink]]（如 '[[安全策略]] [[上次重构]]'）
    """
    vault = os.environ.get("OBSIDIAN_VAULT", "")
    if not vault:
        return "OBSIDIAN_VAULT 未配置，无法保存代码知识"

    # Build path: vault/02_Areas/编程/project/topic.md
    project_dir = Path(vault) / CODE_KNOWLEDGE_FOLDER / _sanitize_filename(project)
    project_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{_sanitize_filename(topic)}.md"
    filepath = project_dir / filename

    # Build note with metadata
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    tag_list = " ".join(f"#{t.strip()}" for t in tags.split(",") if t.strip())
    related_section = f"\n## 关联\n{related.strip()}\n" if related.strip() else ""

    note = (
        f"# {topic}\n\n"
        f"- 项目: {project}\n"
        f"- 日期: {now}\n"
        f"- 标签: {tag_list}\n\n"
        f"---\n\n"
        f"{content.strip()}\n"
        f"{related_section}\n"
        f"---\n"
        f"_由 Bobo 自动生成_\n"
    )

    try:
        filepath.write_text(note, encoding="utf-8")
    except Exception as e:
        return f"保存失败: {e}"

    rel_path = filepath.relative_to(vault)

    # Optionally trigger wiki_rebuild to update cross-links
    rebuild_msg = ""
    try:
        from tools.wiki_rebuild import execute as rebuild
        rebuild()
        rebuild_msg = "\n✅ 知识图谱已更新"
    except Exception:
        pass

    return (
        f"✅ 代码知识已保存: {rel_path}\n"
        f"   {len(content)} 字符{rebuild_msg}"
    )


TOOL_FUNC = execute
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": (
            "将代码决策、设计说明、实现总结保存到 Obsidian 知识库。"
            "修改代码后使用此工具沉淀关键决策（选择了什么方案、为什么）。"
            "下次打开项目时，这些笔记会自动出现在知识图谱中。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "project": {
                    "type": "string",
                    "description": "项目名（如 'bobo-agent'）"
                },
                "topic": {
                    "type": "string",
                    "description": "主题（如 'auth模块', 'JWT鉴权实现', '性能优化方案'）"
                },
                "content": {
                    "type": "string",
                    "description": "笔记正文（markdown 格式）。应包含：做了什么、为什么这样做、考虑了哪些替代方案。"
                },
                "tags": {
                    "type": "string",
                    "description": "逗号分隔的标签（如 'auth,jwt,security'）"
                },
                "related": {
                    "type": "string",
                    "description": "关联笔记的 wikilink（如 '[[安全策略]] [[API设计]]'）"
                }
            },
            "required": ["project", "topic", "content"]
        }
    }
}


def register(reg):
    reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA)
