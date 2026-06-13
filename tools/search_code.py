"""代码搜索工具 - 在项目中搜索关键词，返回匹配的文件和行"""

import os
import re

TOOL_NAME = "search_code"

# 默认搜索目录（项目根目录）
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 跳过不需要搜索的目录
SKIP_DIRS = {"__pycache__", ".git", ".vscode", "node_modules", "projects", "__pycache__"}
SKIP_EXTS = {".pyc", ".pyo", ".bak", ".backup"}


def _should_skip(path: str) -> bool:
    """判断是否应该跳过该文件或目录"""
    name = os.path.basename(path)
    if name in SKIP_DIRS:
        return True
    if name.startswith('.'):
        return True
    ext = os.path.splitext(name)[1].lower()
    if ext in SKIP_EXTS:
        return True
    return False


def execute(keyword: str, directory: str = None, file_pattern: str = "*.py", max_results: int = 20) -> str:
    """
    在项目中搜索关键词，返回匹配的文件和行。

    Args:
        keyword: 要搜索的关键词（支持正则表达式）
        directory: 搜索目录，默认为项目根目录
        file_pattern: 文件匹配模式，如 *.py, *.md, *.json
        max_results: 最大返回结果数
    """
    search_dir = directory or PROJECT_ROOT

    if not os.path.exists(search_dir):
        return f"错误: 目录不存在: {search_dir}"

    # 将 file_pattern 转为正则（如 *.py → .*\.py$）
    pattern_re = file_pattern.replace(".", "\\.").replace("*", ".*") + "$"

    try:
        regex = re.compile(keyword, re.IGNORECASE)
    except re.error as e:
        return f"错误: 正则表达式无效: {e}"

    results = []
    file_count = 0

    for root, dirs, files in os.walk(search_dir):
        # 跳过不需要的目录
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

    if not results:
        return f"未找到匹配 '{keyword}' 的内容（搜索目录: {search_dir}）"

    # 格式化输出
    output = []
    output.append(f"搜索 '{keyword}' 找到 {len(results)} 处匹配:")
    output.append("")

    current_file = None
    for filepath, line_no, line in results:
        if filepath != current_file:
            rel_path = os.path.relpath(filepath, search_dir)
            output.append(f"  {rel_path}")
            current_file = filepath
        output.append(f"    L{line_no}: {line[:120]}")

    return "\n".join(output)


TOOL_FUNC = execute
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": "在项目中搜索关键词，返回匹配的文件和行号。支持正则表达式。适用场景：查找函数定义、查找所有引用某个变量的地方。",
        "parameters": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "要搜索的关键词，支持正则表达式"},
                "directory": {"type": "string", "description": "搜索目录，默认为项目根目录"},
                "file_pattern": {"type": "string", "description": "文件匹配模式，如 *.py, *.md, *.json，默认为 *.py"},
                "max_results": {"type": "integer", "description": "最大返回结果数，默认 20"}
            },
            "required": ["keyword"]
        }
    }
}


def register(reg):
    reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA)
