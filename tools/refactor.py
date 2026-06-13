"""批量重构工具 - 搜索关键词 → 读取文件 → 生成修改 → 批量写入"""

import os
import re
from pathlib import Path

TOOL_NAME = "refactor"

# 默认搜索目录（项目根目录）
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 跳过不需要搜索的目录
SKIP_DIRS = {"__pycache__", ".git", ".vscode", "node_modules", "projects"}
SKIP_EXTS = {".pyc", ".pyo", ".bak", ".backup"}


def _should_skip(path: str) -> bool:
    name = os.path.basename(path)
    if name in SKIP_DIRS:
        return True
    if name.startswith('.'):
        return True
    ext = os.path.splitext(name)[1].lower()
    if ext in SKIP_EXTS:
        return True
    return False


def _search_files(keyword: str, directory: str, file_pattern: str, max_results: int) -> list:
    """搜索文件，返回 (filepath, line_no, line) 列表"""
    pattern_re = file_pattern.replace(".", "\\.").replace("*", ".*") + "$"
    try:
        regex = re.compile(keyword, re.IGNORECASE)
    except re.error:
        return []

    results = []
    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if not _should_skip(os.path.join(root, d))]
        for filename in files:
            if _should_skip(filename):
                continue
            if not re.match(pattern_re, filename):
                continue
            filepath = os.path.join(root, filename)
            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    for line_no, line in enumerate(f, 1):
                        if regex.search(line):
                            results.append((filepath, line_no, line.strip()))
                            if len(results) >= max_results:
                                break
                    if len(results) >= max_results:
                        break
            except:
                continue
        if len(results) >= max_results:
            break
    return results


def _read_file_content(filepath: str) -> str:
    """读取文件内容"""
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()
    except:
        return ""


def _write_file(filepath: str, content: str) -> str:
    """写入文件"""
    try:
        full_path = os.path.expanduser(filepath)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"已写入: {filepath}"
    except Exception as e:
        return f"写入失败 {filepath}: {e}"


def execute(keyword: str, directory: str = None, file_pattern: str = "*.py",
            max_results: int = 20, new_content: str = None,
            files: list = None) -> str:
    """
    批量重构工具：搜索关键词 → 显示匹配 → 批量写入。

    两种使用方式：
    1. 只搜索（不传 new_content 和 files）：
       refactor("_confirm") → 搜索并显示所有匹配位置
    2. 搜索并修改（传 files）：
       refactor("_confirm", files=[{"path": "a.py", "content": "..."}, ...])

    Args:
        keyword: 要搜索的关键词
        directory: 搜索目录，默认为项目根目录
        file_pattern: 文件匹配模式，默认 *.py
        max_results: 最大返回结果数，默认 20
        new_content: （已废弃，请用 files 参数）
        files: 要写入的文件列表 [{"path": "...", "content": "..."}]
    """
    search_dir = directory or PROJECT_ROOT

    if not os.path.exists(search_dir):
        return f"错误: 目录不存在: {search_dir}"

    # 第一步：搜索
    results = _search_files(keyword, search_dir, file_pattern, max_results)

    if not results:
        return f"未找到匹配 '{keyword}' 的内容"

    # 如果有 files 参数，执行批量写入
    if files:
        write_results = []
        for f in files:
            f_path = f.get("path", "")
            f_content = f.get("content", "")
            result = _write_file(f_path, f_content)
            write_results.append(f"  {result}")

        success_count = sum(1 for r in write_results if "已写入" in r)
        fail_count = len(write_results) - success_count

        output = []
        output.append(f"搜索 '{keyword}' 找到 {len(results)} 处匹配，已修改 {success_count} 个文件")
        if fail_count:
            output.append(f"失败: {fail_count} 个")
        output.append("")
        output.extend(write_results)
        return "\n".join(output)

    # 没有 files 参数，只返回搜索结果
    output = []
    output.append(f"搜索 '{keyword}' 找到 {len(results)} 处匹配:")
    output.append("")

    current_file = None
    for filepath, line_no, line in results:
        if filepath != current_file:
            rel_path = os.path.relpath(filepath, search_dir)
            output.append(f"  📄 {rel_path}")
            # 同时显示文件内容摘要
            content = _read_file_content(filepath)
            if content:
                lines = content.split('\n')
                output.append(f"     共 {len(lines)} 行")
            current_file = filepath
        output.append(f"    L{line_no}: {line[:120]}")

    output.append("")
    output.append("提示: 确认修改后，使用 files 参数执行批量写入")
    output.append('示例: refactor("_confirm", files=[{"path": "core/engine.py", "content": "..."}])')

    return "\n".join(output)


TOOL_FUNC = execute
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": "批量重构工具：搜索关键词并显示匹配位置，然后批量写入修改后的文件。先搜索查看结果，再传入 files 执行写入。",
        "parameters": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "要搜索的关键词，支持正则表达式"},
                "directory": {"type": "string", "description": "搜索目录，默认为项目根目录"},
                "file_pattern": {"type": "string", "description": "文件匹配模式，默认 *.py"},
                "max_results": {"type": "integer", "description": "最大返回结果数，默认 20"},
                "files": {
                    "type": "array",
                    "description": "要写入的文件列表，每个元素包含 path 和 content",
                    "items": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "content": {"type": "string"}
                        }
                    }
                }
            },
            "required": ["keyword"]
        }
    }
}


def register(reg):
    reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA)
