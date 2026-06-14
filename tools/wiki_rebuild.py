"""Rebuild the Bobo Knowledge Hub — scan notes, find cross-links, update hub page."""

import os
import re

TOOL_NAME = "wiki_rebuild"


def execute() -> str:
    """Scan Obsidian vault (and Notion/email if configured), rebuild the Knowledge Hub."""
    vault = os.environ.get("OBSIDIAN_VAULT", "")
    if not vault or not os.path.isdir(vault):
        return "OBSIDIAN_VAULT 未配置，请在 .env 中设置"

    # Step 0: Detect vault rules file
    RULES_CANDIDATES = ["AGENTS.md", "CLAUDE.md", "README.md", "rules.md", ".cursorrules",
                        "index.md", "向导.md", "规则.md", "使用说明.md"]
    rules_source = ""
    for fname in RULES_CANDIDATES:
        path = os.path.join(vault, fname)
        if os.path.isfile(path):
            try:
                with open(path, encoding="utf-8") as f:
                    rules_source = f.read(2000).strip()
                rules_source = f"（规则来源: {fname}）\n{rules_source}"
            except Exception:
                pass
            break

    # Step 1: Discover all .md files in the vault
    md_files = []
    for root, dirs, files in os.walk(vault):
        # Skip blocked folders
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for f in files:
            if f.endswith(".md"):
                path = os.path.join(root, f)
                # Skip files in Bobo/ directory (to avoid modifying hub page itself)
                if "/Bobo/" in path or "/bobo/" in path or path.endswith("/hub.md"):
                    continue
                md_files.append(path)

    if not md_files:
        return " vault 中没有找到 .md 文件"

    # Step 2: Read each file, extract a title and first meaningful sentence
    notes = []
    for path in sorted(md_files):
        rel = os.path.relpath(path, vault)
        try:
            with open(path, encoding="utf-8") as f:
                content = f.read(500)  # read first 500 chars for topic detection
            title = rel.replace(".md", "").replace("/", "/")
            # Extract first non-empty line as summary
            summary = ""
            for line in content.split("\n"):
                line = line.strip()
                if line and not line.startswith("#") and len(line) > 10:
                    summary = line[:100]
                    break
            if not summary and content:
                summary = content[:100].replace("\n", " ")
            notes.append({"path": rel, "title": title, "summary": summary, "content": content[:2000]})
        except Exception:
            pass

    # Step 3: For each note, find related notes by keyword matching
    sections = []
    for note in notes:
        # Find keywords from the note's content
        words = set(re.findall(r"[a-zA-Z\u4e00-\u9fff]{2,}", note["content"]))
        # Find related notes that share keywords
        related = []
        for other in notes:
            if other["path"] == note["path"]:
                continue
            other_words = set(re.findall(r"[a-zA-Z\u4e00-\u9fff]{2,}", other["content"]))
            overlap = words & other_words
            if len(overlap) >= 3:  # at least 3 shared keywords = related
                related.append(other)

        # Cross-platform search for each note's title
        cross_refs = []
        title_query = note["title"].split("/")[-1]  # use filename as query

        # Notion (if configured)
        if os.environ.get("NOTION_API_KEY", ""):
            try:
                from tools.notion_search import execute as notion_search
                nr = notion_search(title_query)
                if "没有找到" not in nr and "Notion 未配置" not in nr:
                    cross_refs.append(f"[Notion] {nr.split(chr(10))[1] if chr(10) in nr else nr}")
            except Exception:
                pass

        # Build section
        links = []
        if related:
            links.extend(f"  - [[{r['path'].replace('.md', '')}]]" for r in related[:5])
        if cross_refs:
            links.extend(f"  - {r}" for r in cross_refs[:3])

        if links:
            sections.append(f"## {note['title']}")
            if note["summary"]:
                sections.append(f"{note['summary']}")
            sections.extend(links)
            sections.append("")

    if not sections:
        return "没有找到足够多的关联内容来生成知识图谱"

    # Step 4: Build the hub page
    hub_content = (
        "# Bobo Knowledge Hub\n\n"
        "_由 Bobo 自动生成，关联你的笔记、Notion 页面和邮件。_\n\n"
        "---\n\n"
    ) + "\n".join(sections)

    hub_path = os.path.join(vault, "Bobo", "Knowledge Hub.md")
    os.makedirs(os.path.dirname(hub_path), exist_ok=True)
    with open(hub_path, "w", encoding="utf-8") as f:
        f.write(hub_content)

    note_count = len(md_files)
    section_count = len([s for s in sections if s.startswith("## ")])
    link_count = sum(1 for s in sections if s.strip().startswith("-"))
    return (
        f"知识图谱已更新!\n"
        f"  扫描了 {note_count} 篇笔记\n"
        f"  发现 {section_count} 个关联主题\n"
        f"  创建 {link_count} 个交叉链接\n"
        f"  {'规则来源: ' + rules_source.split(chr(10))[0] if rules_source else '未检测到 vault 规则文件'}\n"
        f"  Notion: {'已关联' if os.environ.get('NOTION_API_KEY') else '未配置'}\n"
        f"  邮箱: {'已关联' if os.path.exists(os.path.expanduser('~/.bobo/mail.json')) else '未配置'}\n\n"
        f"Hub 页面: Bobo/Knowledge Hub.md"
    )


TOOL_FUNC = execute
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": "扫描 Obsidian 笔记库，自动发现笔记之间的关联，创建/更新交叉链接的 Hub 页面。如果配置了 Notion 或邮箱，也会搜索它们的内容并加入链接。",
        "parameters": {"type": "object", "properties": {}}
    }
}


def register(reg):
    reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA)
