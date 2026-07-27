"""共享 inline diff 生成器 — edit_file / file_operation / obsidian 工具共用。"""

import difflib


def make_inline_diff(old_text: str, new_text: str, path_hint: str = "",
                     append_mode: bool = False) -> str:
    """生成 <<<INLINE_DIFF>>>...<<<END_INLINE_DIFF>>> 块。

    Args:
        old_text: 旧内容（新建时传 ""）
        new_text: 新内容
        path_hint: 文件路径（仅用于显示，不参与 diff）
        append_mode: True 时只显示追加的差异段（全 + 行）

    Returns:
        空字符串（无差异时）或带分隔符的 diff 块。
    """
    old_lines = old_text.splitlines(keepends=True) if old_text else []
    new_lines = new_text.splitlines(keepends=True) if new_text else []

    if append_mode and old_lines:
        # append 模式：只取新增部分的行
        new_lines = new_lines[len(old_lines):]

    diff_lines = list(difflib.unified_diff(
        old_lines if not append_mode else [],
        new_lines if not append_mode else new_lines,
        fromfile=path_hint or "a",
        tofile=path_hint or "b",
    ))
    # 去掉 ---/+++ 路径行
    diff_lines = [l for l in diff_lines if not l.startswith("--- ") and not l.startswith("+++ ")]

    if not diff_lines:
        return ""

    # 截断
    diff_truncated = False
    if len(diff_lines) > 40:
        head = diff_lines[:20]
        tail = diff_lines[-20:]
        omitted = len(diff_lines) - 40
        diff_lines = head + [f"... (省略 {omitted} 行)\n"] + tail
        diff_truncated = True

    added = sum(1 for l in diff_lines if l.startswith("+") and not l.startswith("+++"))
    removed = sum(1 for l in diff_lines if l.startswith("-") and not l.startswith("---"))
    header = f"⎿  +{added} −{removed}"
    if diff_truncated:
        header += f" (截断)"

    return f"<<<INLINE_DIFF>>>\n{header}\n{''.join(diff_lines)}<<<END_INLINE_DIFF>>>"
