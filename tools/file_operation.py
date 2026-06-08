"""文件操作工具 - 带读取缓存"""

import os
import hashlib
from pathlib import Path

TOOL_NAME = "file_operation"

# 全局读取缓存（会话级别）
_read_cache = {}

def _get_file_hash(filepath: str) -> str:
    """获取文件内容的哈希值"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return hashlib.md5(f.read().encode()).hexdigest()
    except:
        return None

def execute(action: str, path: str, content: str = None) -> str:
    """执行文件操作
    
    action: read, write, delete, exists
    """
    full_path = os.path.expanduser(path)
    
    if action == "read":
        # 检查缓存
        cache_key = full_path
        if cache_key in _read_cache:
            cached_time, cached_content = _read_cache[cache_key]
            # 检查文件是否被修改
            current_hash = _get_file_hash(full_path)
            if current_hash == cached_time:
                return f"📄 文件内容（缓存）:\n{cached_content}"
        
        # 读取文件
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                content = f.read()
            # 存入缓存
            file_hash = _get_file_hash(full_path)
            _read_cache[cache_key] = (file_hash, content)
            return f"📄 文件内容:\n{content}"
        except Exception as e:
            return f"❌ 读取失败: {e}"
    
    elif action == "write":
        try:
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(content)
            # 清除该文件的读缓存
            _read_cache.pop(full_path, None)
            return f"✅ 已写入: {path}"
        except Exception as e:
            return f"❌ 写入失败: {e}"
    
    elif action == "delete":
        try:
            os.remove(full_path)
            _read_cache.pop(full_path, None)
            return f"✅ 已删除: {path}"
        except Exception as e:
            return f"❌ 删除失败: {e}"
    
    elif action == "exists":
        exists = os.path.exists(full_path)
        return f"文件{'存在' if exists else '不存在'}: {path}"
    
    else:
        return f"❌ 未知操作: {action}"

TOOL_FUNC = execute
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": "文件操作：read（读取，有缓存）、write（写入）、delete（删除）、exists（检查存在）",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["read", "write", "delete", "exists"]},
                "path": {"type": "string"},
                "content": {"type": "string"}
            },
            "required": ["action", "path"]
        }
    }
}

def register(reg):
    reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA)

# 导出清除缓存的函数（供外部使用）
def clear_cache():
    global _read_cache
    _read_cache = {}
