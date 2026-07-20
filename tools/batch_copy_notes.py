"""Batch copy notes within Obsidian vault."""

import os
import shutil

TOOL_NAME = "batch_copy_notes"


def _within_vault(vault: str, path: str) -> bool:
    """realpath 之后必须仍位于 vault 内（防止 .. / 绝对路径逃逸）。"""
    vault_real = os.path.realpath(vault)
    path_real = os.path.realpath(path)
    return path_real == vault_real or path_real.startswith(vault_real + os.sep)


def execute(filenames: list, destination: str) -> str:
    vault = os.environ.get("OBSIDIAN_VAULT", "")
    if not vault:
        return "OBSIDIAN_VAULT 未配置"
    if not filenames:
        return "请提供要复制的文件列表"

    dst_dir = os.path.join(vault, destination.lstrip("/"))
    if not _within_vault(vault, dst_dir):
        return f"❌ 拒绝访问: 目标目录 '{destination}' 不在笔记库范围内（路径穿越防护）"
    if not os.path.exists(dst_dir):
        try:
            os.makedirs(dst_dir, exist_ok=True)
        except Exception as e:
            return f"❌ 无法创建目标目录: {str(e)}"

    results = []
    success = 0
    fail = 0
    for f in filenames:
        if not isinstance(f, str):
            results.append(f"  {str(f)[:50]}: ❌ 无效文件名")
            fail += 1
            continue
        src = os.path.join(vault, f.lstrip("/"))
        if not _within_vault(vault, src):
            results.append(f"  {f}: ❌ 路径越界，已拒绝")
            fail += 1
            continue
        if not os.path.exists(src):
            results.append(f"  {f}: ❌ 文件不存在")
            fail += 1
            continue
        try:
            shutil.copy2(src, dst_dir)
            results.append(f"  {f}: ✅ 已复制")
            success += 1
        except Exception as e:
            results.append(f"  {f}: ❌ {str(e)}")
            fail += 1

    summary = f"批量复制完成: {success} 成功, {fail} 失败"
    return summary + "\n" + "\n".join(results)


TOOL_FUNC = execute
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": "【用途】批量复制多个笔记文件到目标文件夹。",
        "parameters": {
            "type": "object",
            "properties": {
                "filenames": {"type": "array", "items": {"type": "string"}},
                "destination": {"type": "string"}
            },
            "required": ["filenames", "destination"]
        }
    }
}
_check = lambda: bool(__import__('os').environ.get('OBSIDIAN_VAULT', ''))

def register(reg):
    reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA, check_fn=_check)
