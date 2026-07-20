"""Save code review results as structured Obsidian notes.

After reviewing a PR, LLM uses this to create a permanent review record
linked to the project knowledge graph.
"""

import os
import subprocess
from datetime import datetime
from pathlib import Path

TOOL_NAME = "review_to_obsidian"

REVIEW_FOLDER = "02_Areas/编程"


def execute(pr_number: int, project: str, title: str = "",
            findings: str = "", status: str = "待修复") -> str:
    """Save a code review as an Obsidian note.

    Args:
        pr_number: PR 编号
        project: 项目名
        title: PR 标题（可选，留空则用 pr_number）
        findings: 审查发现的问题（markdown 格式）
        status: 审查状态（待修复/已修复/已合并）
    """
    vault = os.environ.get("OBSIDIAN_VAULT", "")
    if not vault:
        return "OBSIDIAN_VAULT 未配置，无法保存审查记录"

    # project 会拼进文件路径，必须防止路径穿越
    if not project or project in (".", "..") or "/" in project or "\\" in project:
        return "❌ project 参数非法：不能为空或包含路径分隔符"

    # Try to get PR title if not provided
    pr_title = title
    if not pr_title:
        try:
            result = subprocess.run(
                ["gh", "pr", "view", str(pr_number), "--json", "title", "-q", ".title"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                pr_title = result.stdout.strip()
        except Exception:
            pass
    if not pr_title:
        pr_title = f"PR #{pr_number}"

    # Build path
    project_dir = Path(vault) / REVIEW_FOLDER / project / "Code Reviews"
    project_dir.mkdir(parents=True, exist_ok=True)

    filename = f"PR{pr_number}_{pr_title[:40].replace('/', '-')}.md"
    filepath = project_dir / filename

    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Build note
    note = (
        f"# PR #{pr_number}: {pr_title}\n\n"
        f"- 项目: {project}\n"
        f"- 审查日期: {now}\n"
        f"- 状态: {status}\n\n"
        f"---\n\n"
        f"## 审查发现\n\n"
        f"{findings.strip() if findings.strip() else '（未发现问题）'}\n\n"
        f"---\n"
        f"_由 Bobo 自动审查_\n"
    )

    try:
        filepath.write_text(note, encoding="utf-8")
    except Exception as e:
        return f"保存失败: {e}"

    rel_path = filepath.relative_to(vault)

    # Update wiki
    try:
        from tools.wiki_rebuild import execute as rebuild
        rebuild()
    except Exception:
        pass

    return (
        f"✅ 审查笔记已保存: {rel_path}\n"
        f"   状态: {status}"
    )


TOOL_FUNC = execute
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": (
            "将代码审查结果保存为 Obsidian 笔记，形成可搜索的审查历史。"
            "审查 PR 后使用此工具沉淀发现的问题。"
            ""
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pr_number": {
                    "type": "integer",
                    "description": "PR 编号"
                },
                "project": {
                    "type": "string",
                    "description": "项目名（如 'bobo-agent'）"
                },
                "title": {
                    "type": "string",
                    "description": "PR 标题（可选，留空自动获取）"
                },
                "findings": {
                    "type": "string",
                    "description": "审查发现（markdown 格式）。列出每个问题的文件、行号、严重程度、建议。"
                },
                "status": {
                    "type": "string",
                    "enum": ["待修复", "已修复", "已合并", "已关闭"],
                    "description": "审查状态（默认 '待修复'）"
                }
            },
            "required": ["pr_number", "project"]
        }
    }
}


def register(reg):
    reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA)
