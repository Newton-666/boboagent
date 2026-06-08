# v5_memory.py — 知识库记忆系统（增强版：容量限制 + 原子写入）

import json
import os
import tempfile
import shutil
from datetime import datetime

MEMORY_DB = "knowledge_base.json"
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
        except:
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
        except:
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
            
            # 重新计算总容量
            entries = data['entries']
            total_chars = _get_total_chars(entries)
            if total_chars > MAX_TOTAL_CHARS:
                # 回滚
                e['text'] = old_text
                return {"error": f"更新后记忆超限 ({total_chars}/{MAX_TOTAL_CHARS})，请先删除一些旧记忆"}
            
            _save(data)
            return {"success": True, "entry": e}
    return {"error": f"未找到 ID: {entry_id}"}


def search_knowledge_base(query):
    entries = get_entries()
    results = []
    for e in entries:
        if query.lower() in e.get('text', '').lower():
            preview = e['text'][:80] + "..." if len(e['text']) > 80 else e['text']
            results.append(f"- [{e.get('folder', '根目录')}] {preview}")
    
    if not results:
        return f"📝 知识库中没找到与 '{query}' 相关的内容。"
    
    stats = get_memory_stats()
    return f"📝 找到 {len(results)} 条记忆 (共 {stats['total_entries']} 条, {stats['usage_percent']}% 容量):\n" + "\n".join(results[:10])


def save_to_knowledge_base(content, entry_type="general"):
    if not content or not content.strip():
        return "❌ 内容不能为空"
    entry = add_entry(content.strip(), entry_type)
    if entry is None:
        stats = get_memory_stats()
        return f"❌ 记忆已满 ({stats['total_chars']}/{stats['max_chars']} 字符)，请删除一些旧记忆"
    return "✅ 已保存到知识库"


if __name__ == "__main__":
    print("=" * 60)
    print("测试 v5_memory.py（容量限制版）")
    print("=" * 60)
    
    stats = get_memory_stats()
    print(f"\n📊 记忆统计:")
    print(f"   条目数: {stats['total_entries']}")
    print(f"   字符数: {stats['total_chars']}/{stats['max_chars']} ({stats['usage_percent']}%)")
    print(f"   单条限制: {stats['max_entry_chars']} 字符")
    
    # 测试添加
    print("\n--- 测试添加记忆 ---")
    entry = add_entry("测试记忆：这是一个容量限制测试", entry_type="test")
    if entry:
        print(f"   ✅ 添加成功，ID: {entry['id']}")
    else:
        print(f"   ⚠️ 添加失败（可能已满）")
    
    # 显示最新统计
    stats = get_memory_stats()
    print(f"\n📊 最新统计: {stats['total_entries']} 条, {stats['total_chars']} 字符")
    
    print("\n✅ v5_memory.py 测试完成")


def register(reg):
    pass
