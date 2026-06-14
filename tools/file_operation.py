"""文件操作工具 - 带读取缓存，支持批量写入"""

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
    except Exception:
        return None

def _write_single_file(path: str, content: str) -> str:
    """写入单个文件"""
    full_path = os.path.expanduser(path)
    try:
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)
        _read_cache.pop(full_path, None)
        return f"已写入: {path}"
    except Exception as e:
        return f"写入失败 {path}: {e}"

def execute(action: str, path: str = None, content: str = None, files: list = None) -> str:
    """执行文件操作
    
    action: read, write, delete, exists, batch_write
    """
    if action == "batch_write":
        if not files:
            return "错误: batch_write 需要提供 files 参数"
        results = []
        for f in files:
            f_path = f.get("path", "")
            f_content = f.get("content", "")
            result = _write_single_file(f_path, f_content)
            results.append(f"  {result}")
        success_count = sum(1 for r in results if not r.startswith("  写入失败"))
        fail_count = len(results) - success_count
        summary = f"批量写入完成: {success_count} 个成功"
        if fail_count:
            summary += f", {fail_count} 个失败"
        return f"{summary}\n" + "\n".join(results)
    
    full_path = os.path.expanduser(path) if path else ""
    
    if action == "read":
        cache_key = full_path
        if cache_key in _read_cache:
            cached_time, cached_content = _read_cache[cache_key]
            current_hash = _get_file_hash(full_path)
            if current_hash == cached_time:
                return f"文件内容（缓存）:\n{cached_content}"
        
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                content = f.read()
            file_hash = _get_file_hash(full_path)
            _read_cache[cache_key] = (file_hash, content)
            return f"文件内容:\n{content}"
        except Exception as e:
            return f"读取失败: {e}"
    
    elif action == "write":
        return _write_single_file(path, content)
    
    elif action == "delete":
        try:
            os.remove(full_path)
            _read_cache.pop(full_path, None)
            return f"已删除: {path}"
        except Exception as e:
            return f"删除失败: {e}"
    
    elif action == "exists":
        exists = os.path.exists(full_path)
        return f"文件{'存在' if exists else '不存在'}: {path}"
    
    else:
        return f"未知操作: {action}"

TOOL_FUNC = execute
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": "文件操作：read（读取，有缓存）、write（写入）、delete（删除）、exists（检查存在）、batch_write（批量写入）",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["read", "write", "delete", "exists", "batch_write"]},
                "path": {"type": "string"},
                "content": {"type": "string"},
                "files": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "content": {"type": "string"}
                        }
                    }
                }
            },
            "required": ["action"]
        }
    }
}

def register(reg):
    reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA)

def clear_cache():
    global _read_cache
    _read_cache = {}
