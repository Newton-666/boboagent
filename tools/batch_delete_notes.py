"""批量删除多个笔记文件"""

TOOL_NAME = "batch_delete_notes"

def execute(filenames: list) -> str:
    from .obsidian_tools import delete_note
    results = []
    success = 0
    fail = 0
    for f in filenames:
        r = delete_note(f)
        if "✅" in r:
            success += 1
            results.append(f"  ✅ {f}")
        else:
            fail += 1
            results.append(f"  ❌ {f}: {r}")
    return f"📋 批量删除：成功 {success} 个，失败 {fail} 个\n\n" + "\n".join(results)

TOOL_FUNC = execute
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": """【用途】批量删除多个笔记文件。
【适用场景】用户要求"删除这几个文件"、"清理这些笔记"。
【警告】删除后不可恢复。""",
        "parameters": {"type": "object", "properties": {"filenames": {"type": "array", "items": {"type": "string"}}}, "required": ["filenames"]}
    }
}
_check = lambda: bool(__import__('os').environ.get('OBSIDIAN_VAULT', ''))

def register(reg): reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA, check_fn=_check)
