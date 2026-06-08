"""
obsidian_tools.py - Obsidian 笔记操作工具（修复版）
"""

import os
import re
from pathlib import Path
from config import OBSIDIAN_VAULT, BOBO_FOLDER, BLOCKED_FOLDERS


def _normalize_path(filename: str, is_destination: bool = False) -> str:
    """规范化文件路径
    
    Args:
        filename: 文件名或路径
        is_destination: 是否为目标路径（用于 move 操作）
    """
    if not filename:
        return ""
    
    if filename.startswith("/"):
        filename = filename[1:]
    if filename.startswith("./"):
        filename = filename[2:]
    
    if not is_destination and not filename.endswith(".md"):
        filename += ".md"
    
    if is_destination:
        return os.path.join(OBSIDIAN_VAULT, filename)
    
    if "/" in filename:
        return os.path.join(OBSIDIAN_VAULT, filename)
    else:
        return os.path.join(OBSIDIAN_VAULT, BOBO_FOLDER, filename)


def _is_blocked_path(path: str) -> bool:
    for blocked in BLOCKED_FOLDERS:
        if blocked in path.split(os.sep):
            return True
    return False


def search_obsidian_notes(query: str) -> str:
    if not query:
        return "❌ 请提供搜索关键词"
    
    target_dir = OBSIDIAN_VAULT
    if not os.path.exists(target_dir):
        return f"❌ Obsidian 仓库不存在: {OBSIDIAN_VAULT}"
    
    results = []
    for root, dirs, files in os.walk(target_dir):
        if _is_blocked_path(root):
            continue
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        
        for file in files:
            if file.endswith('.md'):
                filepath = os.path.join(root, file)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()
                        if query.lower() in content.lower():
                            rel_path = os.path.relpath(filepath, OBSIDIAN_VAULT)
                            results.append(f"- {rel_path}")
                except:
                    pass
    
    if not results:
        return f"📝 没有找到包含 '{query}' 的笔记"
    
    return f"📝 找到 {len(results)} 条笔记:\n" + "\n".join(results[:20])


def read_obsidian_note(filename: str) -> str:
    filepath = _normalize_path(filename, is_destination=False)
    
    if _is_blocked_path(filepath):
        return f"❌ 无权访问该文件（隐私保护）"
    
    if not os.path.exists(filepath):
        return f"我注意到 {filename} 这个文件在你的笔记库里没有找到。要不要先创建它？"
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        return content
    except Exception as e:
        return f"❌ 读取失败: {str(e)}"


def list_folder(folder_path: str = "") -> str:
    if not folder_path or folder_path.strip() == "":
        target = OBSIDIAN_VAULT
        display_name = "根目录"
    else:
        target = os.path.join(OBSIDIAN_VAULT, folder_path)
        display_name = folder_path
    
    if _is_blocked_path(target):
        return f"❌ 无权访问 '{display_name}' 文件夹（隐私保护）"
    
    if not os.path.exists(target):
        return f"我找了一下，{display_name} 文件夹不存在。你需要先创建它吗？"
    
    folders = []
    files = []
    
    for item in os.listdir(target):
        item_path = os.path.join(target, item)
        if item.startswith('.'):
            continue
        if os.path.isdir(item_path):
            if not _is_blocked_path(item_path):
                folders.append(f"📁 {item}/")
        elif item.endswith('.md'):
            files.append(f"📄 {item}")
    
    result = []
    if folders:
        result.append(f"📁 文件夹 ({len(folders)}个):")
        result.extend([f"   {f}" for f in folders])
    if files:
        result.append(f"\n📄 笔记文件 ({len(files)}个):")
        for f in files[:30]:
            result.append(f"   {f}")
        if len(files) > 30:
            result.append(f"   ... 还有 {len(files)-30} 个文件")
    
    if not result:
        return f"📭 {display_name} 为空"
    
    return "\n".join(result)


def write_obsidian_note(filename: str, content: str) -> str:
    from .file_writer import write_obsidian
    return write_obsidian(filename, content)


def append_obsidian_note(filename: str, content: str) -> str:
    from .file_writer import append_obsidian
    return append_obsidian(filename, content)


def move_note(source: str, destination: str) -> str:
    src = _normalize_path(source, is_destination=False)
    dst = _normalize_path(destination, is_destination=True)
    
    if _is_blocked_path(src) or _is_blocked_path(dst):
        return "❌ 无权操作该文件（隐私保护）"
    
    if not os.path.exists(src):
        return f"我注意到你提到的 {source} 这个文件没有找到。要不要先创建它？"
    
    dst_dir = os.path.dirname(dst)
    if dst_dir and not os.path.exists(dst_dir):
        os.makedirs(dst_dir, exist_ok=True)
    
    try:
        import shutil
        shutil.move(src, dst)
        return f"✅ 已移动: {source} -> {destination}"
    except Exception as e:
        return f"❌ 移动失败: {str(e)}"


def delete_note(filename: str) -> str:
    filepath = _normalize_path(filename, is_destination=False)
    
    if _is_blocked_path(filepath):
        return "❌ 无权删除该文件（隐私保护）"
    
    if not os.path.exists(filepath):
        return f"我注意到 {filename} 这个文件在你的笔记库里没有找到。要不要先创建它？"
    
    try:
        os.remove(filepath)
        return f"✅ 已删除: {filename}"
    except Exception as e:
        return f"❌ 删除失败: {str(e)}"


def rename_note(old_name: str, new_name: str) -> str:
    old_path = _normalize_path(old_name, is_destination=False)
    new_path = _normalize_path(new_name, is_destination=False)
    
    if _is_blocked_path(old_path):
        return "❌ 无权操作该文件（隐私保护）"
    
    if not os.path.exists(old_path):
        return f"我注意到 {old_name} 这个文件不存在。请检查文件名。"
    
    try:
        os.rename(old_path, new_path)
        return f"✅ 已重命名: {old_name} -> {new_name}"
    except Exception as e:
        return f"❌ 重命名失败: {str(e)}"


def create_folder(folder_name: str) -> str:
    folder_path = os.path.join(OBSIDIAN_VAULT, BOBO_FOLDER, folder_name)
    
    if os.path.exists(folder_path):
        return f"❌ 文件夹已存在: {folder_name}"
    
    try:
        os.makedirs(folder_path, exist_ok=True)
        return f"✅ 已创建文件夹: {folder_name}"
    except Exception as e:
        return f"❌ 创建失败: {str(e)}"


def delete_folder(folder_name: str, force: bool = False) -> str:
    folder_path = os.path.join(OBSIDIAN_VAULT, BOBO_FOLDER, folder_name)
    
    if _is_blocked_path(folder_path):
        return "❌ 无权删除该文件夹（隐私保护）"
    
    if not os.path.exists(folder_path):
        return f"我找了一下，{folder_name} 文件夹不存在。你需要先创建它吗？"
    
    try:
        if force:
            import shutil
            shutil.rmtree(folder_path)
        else:
            os.rmdir(folder_path)
        return f"✅ 已删除文件夹: {folder_name}"
    except Exception as e:
        return f"❌ 删除失败: {str(e)}"


def move_to_folder(source: str, folder: str) -> str:
    return move_note(source, os.path.join(folder, os.path.basename(source)))


TOOL_MAP = {
    "search_obsidian": search_obsidian_notes,
    "read_obsidian": read_obsidian_note,
    "write_obsidian": write_obsidian_note,
    "append_obsidian": append_obsidian_note,
    "move_note": move_note,
    "delete_note": delete_note,
    "rename_note": rename_note,
    "create_folder": create_folder,
    "delete_folder": delete_folder,
    "list_folder": list_folder,
    "move_to_folder": move_to_folder,
}


# 添加标准导出格式
TOOL_NAME = "obsidian_tools"
TOOL_FUNC = None  # obsidian_tools 是多个工具的组合，不单独注册

def register(reg):
    """注册所有 obsidian 子工具"""
    from .list_folder import TOOL_FUNC as list_folder_func, TOOL_NAME as list_folder_name
    from .search_obsidian import TOOL_FUNC as search_obsidian_func, TOOL_NAME as search_obsidian_name
    from .read_obsidian import TOOL_FUNC as read_obsidian_func, TOOL_NAME as read_obsidian_name
    from .write_obsidian import TOOL_FUNC as write_obsidian_func, TOOL_NAME as write_obsidian_name
    from .move_note import TOOL_FUNC as move_note_func, TOOL_NAME as move_note_name
    from .delete_note import TOOL_FUNC as delete_note_func, TOOL_NAME as delete_note_name
    
    reg(list_folder_name, list_folder_func, {})
    reg(search_obsidian_name, search_obsidian_func, {})
    reg(read_obsidian_name, read_obsidian_func, {})
    reg(write_obsidian_name, write_obsidian_func, {})
    reg(move_note_name, move_note_func, {})
    reg(delete_note_name, delete_note_func, {})
