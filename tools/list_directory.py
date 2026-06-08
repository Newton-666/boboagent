"""列出目录内容（带安全检查）"""

import os
from pathlib import Path

TOOL_NAME = "list_directory"

# 敏感路径前缀（需要确认）
SENSITIVE_PATHS = [
    "/etc", "/System", "/Library", "/usr",
    "~/.ssh", "~/.gnupg", "~/.aws"
]

def is_sensitive_path(path: str) -> bool:
    """检查路径是否敏感"""
    expanded = os.path.expanduser(path)
    for sensitive in SENSITIVE_PATHS:
        if expanded.startswith(os.path.expanduser(sensitive)):
            return True
    return False

def execute(path: str = ".", show_hidden: bool = False, max_items: int = 50) -> str:
    """列出目录内容
    
    Args:
        path: 目录路径，默认为当前目录
        show_hidden: 是否显示隐藏文件
        max_items: 最多显示项目数
    """
    try:
        target = os.path.expanduser(path)
        
        if not os.path.exists(target):
            return f"路径不存在: {path}"
        
        if not os.path.isdir(target):
            return f"不是目录: {path}"
        
        items = []
        for item in os.listdir(target):
            if not show_hidden and item.startswith('.'):
                continue
            item_path = os.path.join(target, item)
            if os.path.isdir(item_path):
                items.append(f"📁 {item}/")
            else:
                size = os.path.getsize(item_path)
                if size < 1024:
                    size_str = f"{size}B"
                elif size < 1024 * 1024:
                    size_str = f"{size // 1024}KB"
                else:
                    size_str = f"{size // (1024 * 1024)}MB"
                items.append(f"📄 {item} ({size_str})")
        
        items = items[:max_items]
        
        if not items:
            return f"目录为空: {path}"
        
        result = f"目录: {os.path.abspath(target)}\n"
        result += "\n".join(items)
        
        if len(items) >= max_items:
            result += f"\n... 还有更多文件（限制显示{max_items}项）"
        
        return result
        
    except PermissionError:
        return f"权限不足，无法读取: {path}"
    except Exception as e:
        return f"读取失败: {str(e)}"


TOOL_FUNC = execute
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": """【用途】列出目录内容。
【适用场景】用户问"有什么文件"、"当前目录有什么"、"浏览文件夹"等。
【注意】访问系统敏感目录时需要用户确认。""",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "目录路径，默认为当前目录"
                },
                "show_hidden": {
                    "type": "boolean",
                    "description": "是否显示隐藏文件，默认false"
                },
                "max_items": {
                    "type": "integer",
                    "description": "最多显示项目数，默认50"
                }
            },
            "required": []
        }
    }
}


def register(reg):
    reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA)
