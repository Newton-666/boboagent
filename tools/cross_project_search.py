"""Search across multiple local projects simultaneously.

Finds code patterns, functions, or text across all your local repos at once.
"""

import os
import re
from pathlib import Path
from typing import Optional

TOOL_NAME = "cross_project_search"

# Default search roots — common project locations
DEFAULT_ROOTS = [
    "~/Desktop",
    "~/Documents",
    "~/Projects",
    "~/Developer",
    "~/Code",
]

# Directories to skip during search
SKIP_DIRS = {
    "__pycache__", ".git", ".venv", "venv", "node_modules",
    "dist", "build", ".next", "coverage", ".tox",
    ".mypy_cache", ".pytest_cache",
}

# Extensions to search
CODE_EXTS = {".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".sh",
             ".md", ".txt", ".json", ".yaml", ".yml"}


def execute(query: str, roots: str = "", file_exts: str = "",
            max_results: int = 30) -> str:
    """Search for a pattern across multiple project directories.

    Args:
        query: 搜索关键词或正则表达式
        roots: 逗号分隔的搜索根目录（默认搜索 Desktop/Documents/Projects/Developer/Code）
        file_exts: 逗号分隔的文件扩展名（默认 .py,.js,.ts,.go,.rs,.md 等）
        max_results: 最多返回多少条结果
    """
    if not query.strip():
        return "请输入搜索关键词"

    # Determine search roots
    if roots:
        search_roots = [Path(r).expanduser() for r in roots.split(",")]
    else:
        search_roots = [Path(r).expanduser() for r in DEFAULT_ROOTS]
    search_roots = [r for r in search_roots if r.exists()]

    if not search_roots:
        return f"未找到任何可搜索的目录。请用 roots 参数指定。"

    # File extensions
    if file_exts:
        exts = {e.strip() for e in file_exts.split(",") if e.strip()}
    else:
        exts = CODE_EXTS

    # Compile regex
    try:
        pattern = re.compile(re.escape(query), re.IGNORECASE)
    except re.error:
        return f"无效的搜索模式: {query}"

    results = []
    files_scanned = 0

    for root in search_roots:
        # Only go 3 levels deep to avoid searching entire home dir
        max_depth = 3
        for dirpath, dirnames, filenames in os.walk(root):
            depth = len(Path(dirpath).relative_to(root).parts)
            if depth > max_depth:
                dirnames[:] = []
                continue

            dirnames[:] = [d for d in dirnames
                          if d not in SKIP_DIRS and not d.startswith(".")]

            for fname in filenames:
                ext = os.path.splitext(fname)[1].lower()
                if ext not in exts:
                    continue

                filepath = os.path.join(dirpath, fname)
                files_scanned += 1

                try:
                    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                        for lineno, line in enumerate(f, 1):
                            if pattern.search(line):
                                results.append({
                                    "file": os.path.relpath(filepath, root.parent),
                                    "line": lineno,
                                    "text": line.strip()[:120],
                                    "root": root.name,
                                })
                                if len(results) >= max_results:
                                    break
                        if len(results) >= max_results:
                            break
                except Exception:
                    continue

            if len(results) >= max_results:
                break

    if not results:
        roots_list = ", ".join(r.name for r in search_roots)
        return f"在 {roots_list} 中未找到 '{query}'"

    # Format output grouped by root
    from collections import defaultdict
    by_root = defaultdict(list)
    for r in results:
        by_root[r["root"]].append(r)

    lines = [f"跨项目搜索 '{query}' — {len(results)} 条结果 ({files_scanned} 文件):\n"]
    for root_name, items in sorted(by_root.items()):
        lines.append(f"## {root_name}")
        for item in items:
            lines.append(f"  {item['file']}:{item['line']}")
            lines.append(f"    {item['text']}")
        lines.append("")

    return "\n".join(lines)


TOOL_FUNC = execute
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": (
            "跨项目搜索——同时在多个目录中搜索代码。"
            "适用场景：'之前哪个项目做过文件上传进度条？'、'找一下 JWT 相关实现'。"
            "默认搜索 Desktop/Documents/Projects/Developer/Code 下的所有项目。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索关键词（精确匹配）"
                },
                "roots": {
                    "type": "string",
                    "description": "逗号分隔的搜索根目录（默认 Desktop,Documents,Projects 等）"
                },
                "file_exts": {
                    "type": "string",
                    "description": "逗号分隔的文件扩展名（默认 .py,.js,.ts,.go,.rs,.md）"
                },
                "max_results": {
                    "type": "integer",
                    "description": "最多返回条数（默认 30）"
                }
            },
            "required": ["query"]
        }
    }
}


def register(reg):
    reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA)
