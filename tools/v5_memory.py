# v5_memory.py — 知识库记忆系统（增强版：容量限制 + 原子写入）
# 数据存储在 ~/.bobo_v2/ 下，不在项目目录中

import json
import os
import tempfile
import shutil
from datetime import datetime
from pathlib import Path

# 数据存储目录：用户目录下的 .bobo_v2，不在项目目录中
_MEMORY_DIR = Path.home() / ".bobo_v2"
_MEMORY_DIR.mkdir(parents=True, exist_ok=True)
MEMORY_DB = str(_MEMORY_DIR / "knowledge_base.json")

MAX_TOTAL_CHARS = 100000  # 总记忆字符限制（约 36k tokens）
MAX_SINGLE_ENTRY_CHARS = 5000  # 单条记忆字符限制


def _atomic_save(data):
    """原子写入 JSON 文件（防止写入中断导致损坏）"""
    dirname = os.path.dirname(MEMORY_DB)
    if dirname:
        os.makedirs(dirname, exist_ok=True)
    
    fd, tmp_path = tempfile.mkstemp(dir=dirname or '.', suffix='.tmp', prefix='.mem_')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        shutil.move(tmp_path, MEMORY_DB)
    except Exception:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
        raise


def _load():
    if os.path.exists(MEMORY_DB):
        try:
            with open(MEMORY_DB, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if 'entries' not in data:
                    data = {'entries': [], 'folders': []}
                return data
        except Exception:
            pass
    return {'entries': [], 'folders': []}


def _get_total_chars(entries):
    """计算所有记忆的总字符数"""
    total = 0
    for entry in entries:
        total += len(entry.get("text", ""))
    return total


def _save(data):
    _atomic_save(data)


def add_entry(text, entry_type="general", tags=None, folder=""):
    """添加记忆条目（带容量检查）"""
    if not text or not text.strip():
        return None
    
    # 单条记忆长度检查
    if len(text) > MAX_SINGLE_ENTRY_CHARS:
        print(f"⚠️ 记忆太长 ({len(text)} 字符)，已截断至 {MAX_SINGLE_ENTRY_CHARS}")
        text = text[:MAX_SINGLE_ENTRY_CHARS] + "\n...[截断]"
    
    data = _load()
    entries = data.get('entries', [])
    
    # 检查是否已存在相同内容
    for e in entries:
        if e.get("text", "").strip() == text.strip():
            return e
    
    # 容量检查
    current_chars = _get_total_chars(entries)
    new_chars = current_chars + len(text)
    
    if new_chars > MAX_TOTAL_CHARS:
        print(f"⚠️ 记忆已满 ({current_chars}/{MAX_TOTAL_CHARS} 字符)，无法添加新记忆")
        print(f"   💡 请删除一些旧记忆后再试")
        return None
    
    entry = {
        "id": len(entries) + 1,
        "text": text,
        "type": entry_type,
        "tags": tags or [],
        "folder": folder,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M")
    }
    entries.append(entry)
    data['entries'] = entries
    _save(data)
    return entry


def delete_entry(entry_id, reason=None):
    """删除记忆条目（要求说明原因）"""
    if reason not in ["absorbed", "stale", "user_request"]:
        return {"error": "请说明删除原因: absorbed/stale/user_request"}
    
    data = _load()
    entries = data.get('entries', [])
    
    for i, e in enumerate(entries):
        if e.get('id') == entry_id:
            removed = entries.pop(i)
            data['entries'] = entries
            _save(data)
            return {"success": True, "removed": removed, "reason": reason}
    
    return {"error": f"未找到 ID: {entry_id}"}


def get_memory_stats():
    """获取记忆统计信息"""
    data = _load()
    entries = data.get('entries', [])
    total_chars = _get_total_chars(entries)
    return {
        "total_entries": len(entries),
        "total_chars": total_chars,
        "max_chars": MAX_TOTAL_CHARS,
        "usage_percent": round(total_chars / MAX_TOTAL_CHARS * 100, 1) if MAX_TOTAL_CHARS > 0 else 0,
        "max_entry_chars": MAX_SINGLE_ENTRY_CHARS
    }


def get_all():
    return _load()


def get_entries():
    return _load()['entries']


def get_folders():
    return _load().get('folders', [])


def add_folder(name):
    data = _load()
    if name not in data.get('folders', []):
        data['folders'].append(name)
        _save(data)
    return name


def rename_folder(old_name, new_name):
    data = _load()
    if old_name in data.get('folders', []):
        data['folders'].remove(old_name)
        data['folders'].append(new_name)
    for e in data['entries']:
        if e.get('folder') == old_name:
            e['folder'] = new_name
    _save(data)
    return new_name


def delete_folder(name):
    data = _load()
    if name in data.get('folders', []):
        data['folders'].remove(name)
    for e in data['entries']:
        if e.get('folder') == name:
            e['folder'] = ""
    _save(data)


def move_to_folder(entry_id, folder_name):
    data = _load()
    for e in data['entries']:
        if e.get('id') == entry_id:
            e['folder'] = folder_name
            _save(data)
            return True
    return False


def update_entry(entry_id, new_text):
    """更新条目内容（带容量检查）"""
    if len(new_text) > MAX_SINGLE_ENTRY_CHARS:
        return {"error": f"更新内容太长 ({len(new_text)} 字符)，超过限制 {MAX_SINGLE_ENTRY_CHARS}"}
    
    data = _load()
    for e in data['entries']:
        if e.get('id') == entry_id:
            old_text = e['text']
            e['text'] = new_text
            e['timestamp'] = datetime.now().strftime("%Y-%m-%d %H:%M")
            
            # 重新计算总字符数
            entries = data['entries']
            total = _get_total_chars(entries)
            if total > MAX_TOTAL_CHARS:
                e['text'] = old_text
                return {"error": f"更新后记忆总容量 ({total}) 超过限制 ({MAX_TOTAL_CHARS})"}
            
            _save(data)
            return {"success": True, "entry": e}
    
    return {"error": f"未找到 ID: {entry_id}"}


def search_knowledge_base(query):
    """搜索知识库"""
    data = _load()
    entries = data.get('entries', [])
    query_lower = query.lower()
    
    results = []
    for e in entries:
        text = e.get("text", "")
        if query_lower in text.lower():
            results.append(e)
    
    if not results:
        return "未找到相关记忆"
    
    output = f"找到 {len(results)} 条相关记忆:\n"
    for e in results:
        text = e['text'][:100]
        output += f"  [{e['id']}] {text}\n"
    return output


def save_to_knowledge_base(content, entry_type="general"):
    """保存内容到知识库（供工具调用）"""
    entry = add_entry(content, entry_type)
    if entry:
        return f"已保存到知识库 (ID: {entry['id']})"
    return "保存失败"


def save_user_profile(key: str, value: str) -> str:
    """Save or update a user profile entry."""
    data = _load()
    if "profile" not in data:
        data["profile"] = {}
    data["profile"][key] = {"value": value, "updated": datetime.now().isoformat()}
    _save(data)
    return f"用户资料已更新: {key} = {value}"


def get_user_profile() -> dict:
    """Return all user profile entries."""
    data = _load()
    return data.get("profile", {})


def format_user_profile() -> str:
    """Format user profile for system prompt injection."""
    profile = get_user_profile()
    if not profile:
        return ""
    lines = []
    for key, entry in sorted(profile.items()):
        lines.append(f"  {key}: {entry['value']}")
    return "用户资料:\n" + "\n".join(lines)


def register(reg):
    reg("save_memory", save_to_knowledge_base, {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": "Save info to memory (target=memory) or user profile (target=profile, memory_type=key).\nExamples:\n- save fact -> target=memory\n- save user name -> target=profile, memory_type=name",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string"},
                    "memory_type": {"type": "string", "description": "memory type or profile key name"},
                    "target": {"type": "string", "enum": ["memory", "profile"], "default": "memory"}
                },
                "required": ["content"]
            }
        }
    })

    reg("search_memory", search_knowledge_base, {
        "type": "function",
        "function": {
            "name": "search_memory",
            "description": "Search saved memories or user profile.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"]
            }
        }
    })
