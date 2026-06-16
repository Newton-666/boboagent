"""grep_code.py — 代码库内容搜索（正则 + 文件名过滤 + 上下文行）

用法：
    grep_code(pattern="TODO", path="src/", file_types=".py,.js", context=2)

特点：
    - 优先使用 ripgrep (rg)，回退到 Python Path.rglob
    - 支持正则表达式
    - 按文件类型过滤
    - 可选的上下文行（匹配行前后各 N 行）
    - 结果自动截断（最多 50 条匹配，每条最多 500 字符）
"""

import os
import re
import subprocess
from pathlib import Path


MAX_MATCHES = 50
MAX_LINE_LENGTH = 500


def _search_python(search_dir: Path, pattern: str, file_types: list[str],
                   context: int) -> list[dict]:
    """Python 原生搜索（ripgrep 不可用时的回退方案）。"""
    results = []
    try:
        compiled = re.compile(pattern)
    except re.error as e:
        return [{"error": f"正则表达式无效: {e}"}]

    for file_path in search_dir.rglob("*"):
        if not file_path.is_file():
            continue
        if file_types and file_path.suffix not in file_types:
            continue
        # 跳过常见非代码目录
        parts = file_path.parts
        if any(p.startswith(".") and p not in (".", "..") for p in parts):
            continue
        if any(p in ("node_modules", "__pycache__", ".git", ".venv", "venv",
                     "dist", "build", ".next", "coverage") for p in parts):
            continue

        try:
            lines = file_path.read_text(encoding="utf-8").split("\n")
        except Exception:
            continue

        for i, line in enumerate(lines):
            if compiled.search(line):
                start = max(0, i - context)
                end = min(len(lines), i + context + 1)
                snippet = []
                for j in range(start, end):
                    prefix = ">" if j == i else " "
                    snippet.append(f"{prefix}{j + 1}: {lines[j][:MAX_LINE_LENGTH]}")
                results.append({
                    "file": str(file_path.relative_to(search_dir)),
                    "line": i + 1,
                    "snippet": "\n".join(snippet),
                })
                if len(results) >= MAX_MATCHES:
                    return results
    return results


def _search_ripgrep(search_dir: Path, pattern: str, file_types: list[str],
                    context: int) -> list[dict] | None:
    """使用 ripgrep 搜索。失败返回 None（回退到 Python 搜索）。"""
    try:
        cmd = ["rg", "--line-number", "--no-heading", "--color", "never"]
        if context:
            cmd.extend(["--context", str(context)])
        if file_types:
            for ft in file_types:
                cmd.extend(["--glob", f"*{ft}"])
        cmd.append(pattern)
        cmd.append(str(search_dir))

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if result.returncode not in (0, 1):
            return None  # 非零且非 1 = 真正的错误

        lines = result.stdout.strip().split("\n")
        matches = []
        for line in lines[:MAX_MATCHES * (context * 2 + 1) * 2]:
            if not line.strip() or line == "--":
                # 保留 "--" 作为分隔符（rg 在有上下文时输出）
                matches.append({"separator": True})
                continue
            # rg 输出格式:  file:line:content  或  file-line-content (带上下文)
            m = re.match(r'^(.+?)[:-](\d+)[:-](.*)', line)
            if m:
                matches.append({
                    "file": m.group(1),
                    "line": int(m.group(2)),
                    "content": m.group(3)[:MAX_LINE_LENGTH],
                })

        # 转成统一格式
        results = []
        current_file = None
        current_snippet = []
        current_line = 0
        for m in matches:
            if m.get("separator"):
                if current_snippet:
                    results.append({
                        "file": current_file,
                        "line": current_line,
                        "snippet": "\n".join(current_snippet),
                    })
                    current_snippet = []
                continue
            current_file = m.get("file") or current_file
            current_line = current_line or m["line"]
            current_snippet.append(f"{m['line']}: {m['content']}")
        if current_snippet:
            results.append({
                "file": current_file or "",
                "line": current_line,
                "snippet": "\n".join(current_snippet),
            })

        return results[:MAX_MATCHES]
    except Exception:
        return None


def execute(pattern: str, path: str = ".", file_types: str = "",
            context: int = 1) -> str:
    """在代码库中搜索正则表达式。

    Args:
        pattern: 正则表达式模式（例如 "TODO|FIXME", "def test_\\w+", "import os"）
        path: 搜索目录（默认当前目录）
        file_types: 逗号分隔的文件扩展名（例如 ".py,.js,.ts"）
        context: 每个匹配行前后显示的额外行数
    """
    if not pattern or not pattern.strip():
        return "错误: 请提供搜索模式"

    search_dir = Path(path).expanduser().resolve()
    if not search_dir.exists():
        return f"错误: 目录不存在: {search_dir}"
    if not search_dir.is_dir():
        # 可能是文件——搜索该文件
        if search_dir.is_file():
            search_dir = search_dir.parent
        else:
            return f"错误: 路径不是目录: {search_dir}"

    types = [ft.strip() for ft in file_types.split(",") if ft.strip()] if file_types else []

    # 优先 ripgrep，回退 Python
    results = _search_ripgrep(search_dir, pattern, types, context)
    if results is None:
        results = _search_python(search_dir, pattern, types, context)

    if not results:
        return f"未找到匹配 '{pattern}' 的内容 ({search_dir})"

    # 去重：按 (file, line) 去重
    seen = set()
    unique = []
    for r in results:
        if "error" in r:
            return r["error"]
        key = (r.get("file", ""), r.get("line", 0))
        if key not in seen:
            seen.add(key)
            unique.append(r)

    lines = [
        f"搜索 '{pattern}' 在 {search_dir} 中找到 {len(unique)} 处匹配:\n"
    ]
    # 按文件分组
    by_file: dict[str, list] = {}
    for r in unique:
        by_file.setdefault(r["file"], []).append(r)

    total = 0
    for fname, matches in by_file.items():
        lines.append(f"\n── {fname} ──")
        for m in matches:
            lines.append(m["snippet"])
            lines.append("")
            total += 1
        if total >= MAX_MATCHES:
            break

    if len(unique) >= MAX_MATCHES:
        lines.append(f"\n(仅显示前 {MAX_MATCHES} 条匹配，请缩小搜索范围)")

    return "\n".join(lines)


def register(reg):
    reg("grep_code", execute, {
        "type": "function",
        "function": {
            "name": "grep_code",
            "description": (
                "在代码库中搜索正则表达式模式。"
                "适用于搜索函数定义、TODO 注释、导入语句、特定字符串等。"
                "与 list_directory 搭配使用：先用 grep_code 定位，再用 edit_file 或 read_local_file 操作。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "正则表达式搜索模式（例如 'def test_', 'TODO|FIXME', 'import os'）"
                    },
                    "path": {
                        "type": "string",
                        "description": "搜索路径（目录或文件）。默认为当前工作目录。"
                    },
                    "file_types": {
                        "type": "string",
                        "description": "逗号分隔的文件扩展名过滤（例如 '.py,.js,.ts'）。留空表示不过滤。"
                    },
                    "context": {
                        "type": "integer",
                        "description": "每个匹配行前后显示的额外行数。默认 1。"
                    }
                },
                "required": ["pattern"]
            }
        }
    })
