"""project_info.py - 获取项目结构和文件信息"""

import os
from pathlib import Path

TOOL_NAME = "project_info"

def execute(path: str = ".", info_type: str = "structure", max_depth: int = 3) -> str:
    """获取项目信息
    
    Args:
        path: 项目路径
        info_type: structure(目录结构), files(文件列表), summary(摘要)
        max_depth: 最大深度
    """
    target = os.path.expanduser(path)
    if not os.path.exists(target):
        return f"路径不存在: {path}"
    
    if info_type == "structure":
        return _get_directory_structure(target, max_depth)
    elif info_type == "files":
        return _get_file_list(target)
    else:
        return _get_project_summary(target)


def _get_directory_structure(path, max_depth=3, current_depth=0, prefix=""):
    if current_depth >= max_depth:
        return ""
    result = []
    try:
        items = sorted(os.listdir(path))
        for i, item in enumerate(items):
            if item.startswith('.'):
                continue
            item_path = os.path.join(path, item)
            is_last = (i == len(items) - 1)
            connector = "└── " if is_last else "├── "
            result.append(f"{prefix}{connector}{item}")
            if os.path.isdir(item_path):
                extension = "    " if is_last else "│   "
                sub = _get_directory_structure(item_path, max_depth, current_depth + 1, prefix + extension)
                if sub:
                    result.append(sub)
    except PermissionError:
        pass
    return '\n'.join(result) if isinstance(result, list) else result


def _get_file_list(path):
    files = []
    for root, dirs, filenames in os.walk(path):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for f in filenames:
            if not f.startswith('.'):
                files.append(os.path.relpath(os.path.join(root, f), path))
    if not files:
        return "目录中没有文件"
    return '\n'.join(files[:50]) + ("\n... 还有更多" if len(files) > 50 else "")


def _get_project_summary(path):
    total_files = 0
    total_size = 0
    file_types = {}
    
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for f in files:
            if f.startswith('.'):
                continue
            total_files += 1
            try:
                size = os.path.getsize(os.path.join(root, f))
                total_size += size
            except Exception:
                pass
            ext = os.path.splitext(f)[1] or "no_ext"
            file_types[ext] = file_types.get(ext, 0) + 1
    
    result = f"项目摘要:\n"
    result += f"  总文件数: {total_files}\n"
    result += f"  总大小: {total_size // 1024} KB\n"
    result += f"  文件类型分布:\n"
    for ext, count in sorted(file_types.items(), key=lambda x: -x[1])[:10]:
        result += f"    {ext}: {count} 个\n"
    return result


TOOL_FUNC = execute
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": "获取项目信息，包括目录结构、文件列表或项目摘要。用于了解代码库结构。",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "项目路径，默认当前目录"},
                "info_type": {"type": "string", "enum": ["structure", "files", "summary"], "description": "信息类型"},
                "max_depth": {"type": "integer", "description": "最大深度，默认3"}
            },
            "required": []
        }
    }
}


def register(reg):
    reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA)
