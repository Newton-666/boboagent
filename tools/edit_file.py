"""edit_file.py — 精确字符串替换（不改架构，只加一个工具）

用法：
    edit_file(file_path="/path/to/file.py",
              old_string="bug line here",
              new_string="fixed line here")

特点：
    - old_string 必须在文件中恰好出现一次（防止误改）
    - 写入前自动备份到 ~/.bobo/trash/
    - 替换后自动捕获 git diff 注入下一轮 LLM 调用
"""

import os
import time
from pathlib import Path
from core.file_safety import is_write_denied


TRASH_DIR = Path.home() / ".bobo" / "trash"


def _backup(file_path: Path) -> str | None:
    """将文件备份到回收站，返回备份文件名。失败返回 None。"""
    if not file_path.exists():
        return None
    try:
        TRASH_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        backup_name = f"{file_path.name}_{timestamp}"
        backup_path = TRASH_DIR / backup_name
        backup_path.write_text(file_path.read_text(encoding="utf-8"), encoding="utf-8")
        return backup_name
    except Exception:
        return None


def _find_similar_lines(content: str, old_string: str, max_hints: int = 5) -> list[tuple[int, str]]:
    """在文件内容中搜索与 old_string 最相似的行，返回 [(行号, 行内容), ...]。

    策略（按优先级）：
      1. 用 old_string 的第一行做精确子串搜索
      2. 提取 old_string 中的关键词（3 个字符以上的标识符），
         搜索包含所有关键词的行
      3. 都没找到则返回空列表
    """
    lines = content.split("\n")
    if not old_string.strip():
        return []

    # 策略 1：提取 old_string 第一行，去掉首尾空白做子串搜索
    first_line = old_string.strip().split("\n")[0].strip()
    if len(first_line) >= 6:
        candidates = []
        for i, line in enumerate(lines):
            if first_line in line:
                candidates.append((i + 1, line))
                if len(candidates) >= max_hints:
                    return candidates
        if candidates:
            return candidates

    # 策略 2：提取 old_string 中的关键词，每个关键词独立搜索，
    # 匹配行数最多的优先返回
    import re
    keywords = re.findall(r"[a-zA-Z_]\w{2,}|\S{3,}", old_string)
    keywords = list(dict.fromkeys(keywords))[:5]  # 去重，最多 5 个
    if not keywords:
        return []

    # 按匹配关键词数量降序排列候选行
    scored = []
    for i, line in enumerate(lines):
        score = sum(1 for kw in keywords if kw in line)
        if score > 0:
            scored.append((score, i + 1, line))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [(ln, txt) for _, ln, txt in scored[:max_hints]]


def execute(file_path: str, old_string: str, new_string: str) -> str:
    """精确替换文件中第一次（且唯一一次）出现的 old_string。"""

    path = Path(file_path).expanduser().resolve()

    # ── 安全检查 ──
    denied, reason = is_write_denied(str(path))
    if denied:
        return f"错误: {reason}"

    # ── 存在性检查 ──
    if not path.exists():
        hint = ""
        parent = path.parent
        if parent.exists():
            try:
                siblings = [p.name for p in parent.iterdir() if p.is_file()]
                if siblings:
                    hint = f"\n  目录 {parent} 下的文件: {', '.join(siblings[:10])}"
            except Exception:
                pass
        return f"错误: 文件不存在: {path}{hint}"

    if not path.is_file():
        return f"错误: 路径不是文件: {path}"

    # ── 读取 ──
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return f"错误: 无法以 UTF-8 编码读取文件: {path}"

    # ── 匹配检查 ──
    count = content.count(old_string)
    if count == 0:
        # 自动搜索文件中与 old_string 相似的行，帮助 LLM 一次纠正
        preview = old_string[:80].replace("\n", "\\n")
        hints = _find_similar_lines(content, old_string)
        hint_block = ""
        if hints:
            hint_block = "\n  文件中相似的行:\n" + "\n".join(
                f"    L{ln}: {txt[:120]}" for ln, txt in hints
            )
        return (
            f"错误: 未找到要替换的文本。\n"
            f"  文件: {path} ({len(content)} 字符, {content.count(chr(10)) + 1} 行)\n"
            f"  查找内容: {preview}...\n"
            f"  请检查 old_string 是否与文件内容完全一致（包括缩进和空白字符）。"
            f"{hint_block}"
        )

    if count > 1:
        # 取第一个匹配位置，展示前后文让 LLM 确认
        idx = content.index(old_string)
        line_start = content.rfind('\n', 0, idx) + 1 if '\n' in content[:idx] else 0
        line_end = content.find('\n', idx + len(old_string))
        if line_end == -1:
            line_end = len(content)
        before = content[max(0, line_start-60):line_start].strip()
        after = content[line_end:min(len(content), line_end+60)].strip()
        preview = content[line_start:line_end][:200].replace('\n', '\\n')
        return (
            f"old_string 在文件中出现了 {count} 次。取第一个匹配位置：\n"
            f"  ┌─ 上文: ...{before[-40:]}\n"
            f"  │  {preview}\n"
            f"  └─ 下文: {after[:40]}...\n"
            f"这是你要修改的位置吗？如果确认，加参数 confirm=true 执行替换。"
        )

    # ── 备份 ──
    backup_name = _backup(path)

    # ── 替换 ──
    new_content = content.replace(old_string, new_string, 1)
    try:
        path.write_text(new_content, encoding="utf-8")
    except Exception as e:
        return f"错误: 写入失败: {e}"

    old_lines = content.count("\n") + 1
    new_lines = new_content.count("\n") + 1
    backup_info = f"\n  备份: ~/.bobo/trash/{backup_name}" if backup_name else ""

    return (
        f"已替换: {path}\n"
        f"  文件大小: {len(content)} → {len(new_content)} 字符\n"
        f"  行数: {old_lines} → {new_lines} 行{backup_info}"
    )


def register(reg):
    reg("edit_file", execute, {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": (
                "精确替换文件中的一段文本。old_string 必须在文件中恰好出现一次。"
                "适用于修改函数定义、修复 bug、重构代码等场景。"
                "不要用于创建新文件——创建新文件用 file_writer。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "要编辑的文件路径（绝对路径或相对路径）"
                    },
                    "old_string": {
                        "type": "string",
                        "description": "要被替换的文本，必须与文件内容完全一致（含缩进、空格、换行）。文件中必须恰好出现一次。"
                    },
                    "new_string": {
                        "type": "string",
                        "description": "替换后的文本"
                    }
                },
                "required": ["file_path", "old_string", "new_string"]
            }
        }
    })
