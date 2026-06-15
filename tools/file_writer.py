"""
file_writer.py - 稳定的文件写入模块
支持：写入、追加、编辑，带自动备份
"""

import os
import shutil
import time
from datetime import datetime
from typing import Optional

from config import OBSIDIAN_VAULT, BOBO_FOLDER, BLOCKED_FOLDERS
from .obsidian_tools import _normalize_path

# ============================================================
# 辅助函数
# ============================================================

def _ensure_dir(filepath: str) -> bool:
    """确保目录存在"""
    dirname = os.path.dirname(filepath)
    if dirname and not os.path.exists(dirname):
        os.makedirs(dirname, exist_ok=True)
        return True
    return True


def _create_backup(filepath: str) -> Optional[str]:
    """创建备份文件"""
    if not os.path.exists(filepath):
        return None
    
    backup_dir = os.path.join(OBSIDIAN_VAULT, BOBO_FOLDER, ".backups")
    os.makedirs(backup_dir, exist_ok=True)
    
    basename = os.path.basename(filepath)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(backup_dir, f"{basename}.{timestamp}.bak")
    
    try:
        shutil.copy2(filepath, backup_path)
        return backup_path
    except Exception:
        return None


# ============================================================
# 核心写入函数
# ============================================================

def write_obsidian(filename: str, content: str, auto_backup: bool = True) -> str:
    """
    写入文件（覆盖模式）
    
    Args:
        filename: 文件名
        content: 要写入的内容
        auto_backup: 是否自动备份
    
    Returns:
        操作结果消息
    """
    if not filename or not filename.strip():
        return "❌ 文件名不能为空"
    
    if not content:
        return "❌ 内容不能为空"
    
    try:
        filepath = _normalize_path(filename)
        
        # 多个同名文件时，让用户选择
        if isinstance(filepath, str) and filepath.startswith("__MULTIPLE_MATCHES__"):
            paths = filepath.split(":", 1)[1].split("|")
            return f"找到多个同名文件，请指定具体路径:\n" + "\n".join(f"  {p}" for p in paths)
        
        # 检查是否在屏蔽文件夹中
        for blocked in BLOCKED_FOLDERS:
            blocked = blocked.strip()
            if blocked and blocked in filepath.split(os.sep):
                return f"❌ 无权写入该文件（隐私保护）"
        
        _ensure_dir(filepath)
        
        # 自动备份
        if auto_backup:
            _create_backup(filepath)
        
        # 写入文件
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return f"✅ 已写入: {filename}"
        
    except Exception as e:
        return f"❌ 写入失败: {str(e)}"


def append_obsidian(filename: str, content: str, auto_backup: bool = True) -> str:
    """追加内容到已有文件末尾。文件必须存在。"""
    if not filename or not filename.strip():
        return "❌ 文件名不能为空"
    if not content:
        return "❌ 内容不能为空"
    try:
        filepath = _normalize_path(filename, for_append=True)

        # 多个同名文件时，让用户选择
        if isinstance(filepath, str) and filepath.startswith("__MULTIPLE_MATCHES__"):
            paths = filepath.split(":", 1)[1].split("|")
            return f"找到多个同名文件，请指定具体路径:\n" + "\n".join(f"  {p}" for p in paths)

        # 检查文件是否存在
        if not os.path.exists(filepath):
            # 尝试去掉/加上 .md 再找一次
            alt_filename = filename
            if filename.endswith(".md"):
                alt_filename = filename[:-3]
            else:
                alt_filename = filename + ".md"
            alt_path = _normalize_path(alt_filename, for_append=True)
            if isinstance(alt_path, str) and not alt_path.startswith("__") and os.path.exists(alt_path):
                filepath = alt_path
            else:
                return (
                    f"❌ 文件不存在: {filename}\n"
                    f"  尝试过: {filepath}\n"
                    f"  请确认文件名是否正确，或先用 search_obsidian 搜索文件名。"
                    f"  如果要创建新文件，请用 write_obsidian。"
                )

        for blocked in BLOCKED_FOLDERS:
            blocked = blocked.strip()
            if blocked and blocked in filepath.split(os.sep):
                return "❌ 无权写入该文件（隐私保护）"

        _ensure_dir(filepath)

        if auto_backup:
            _create_backup(filepath)

        # 检查文件末尾是否有换行，没有则补一个
        needs_newline = False
        if os.path.getsize(filepath) > 0:
            with open(filepath, 'rb') as check:
                check.seek(-1, os.SEEK_END)
                needs_newline = (check.read(1) != b'\n')

        with open(filepath, 'a', encoding='utf-8') as f:
            if needs_newline:
                f.write('\n')
            f.write(content)

        return f"✅ 已追加到: {os.path.relpath(filepath, OBSIDIAN_VAULT)}"

    except Exception as e:
        return f"❌ 追加失败: {str(e)}"


def read_file(filename: str) -> str:
    """
    读取文件内容（供内部使用）
    """
    try:
        filepath = _normalize_path(filename)
        if not os.path.exists(filepath):
            return f"❌ 文件不存在: {filename}"
        
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return f"❌ 读取失败: {str(e)}"


# ============================================================
# 工具映射
# ============================================================

TOOL_MAP = {
    "write_obsidian": write_obsidian,
    "append_obsidian": append_obsidian,
}


# ============================================================
# 测试代码
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("测试 file_writer.py")
    print("=" * 60)
    
    test_file = "_test_note.md"
    
    # 测试写入
    print("\n1. 测试写入:")
    result = write_obsidian(test_file, "# 测试标题\n\n这是测试内容。", auto_backup=False)
    print(f"   {result}")
    
    # 测试追加
    print("\n2. 测试追加:")
    result = append_obsidian(test_file, "\n\n这是追加的内容。", auto_backup=False)
    print(f"   {result}")
    
    # 验证内容
    print("\n3. 验证内容:")
    content = read_file(test_file)
    print(f"   {content[:200]}...")
    
    # 清理测试文件
    filepath = _normalize_path(test_file)
    if os.path.exists(filepath):
        os.remove(filepath)
        print("\n4. 清理测试文件: ✅")
    
    print("\n✅ file_writer.py 测试完成")


def register(reg):
    pass
