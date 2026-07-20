"""Batch move notes — use existing move_note function for each file."""

TOOL_NAME = "batch_move_notes"


def execute(filenames: list, destination: str) -> str:
    from .obsidian_tools import move_note

    if not filenames:
        return "请提供要移动的文件列表"

    results = []
    success = 0
    fail = 0
    for f in filenames:
        r = move_note(f, destination)
        if "✅" in r:
            success += 1
        else:
            fail += 1
        results.append(f"  {f}: {r}")

    summary = f"批量移动完成: {success} 成功, {fail} 失败"
    return summary + "\n" + "\n".join(results)


TOOL_FUNC = execute
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": "【用途】一次性移动多个笔记文件到指定文件夹。",
        "parameters": {
            "type": "object",
            "properties": {
                "filenames": {"type": "array", "description": "要移动的笔记文件名列表", "items": {"type": "string"}},
                "destination": {"type": "string", "description": "目标文件夹路径"}
            },
            "required": ["filenames", "destination"]
        }
    }
}
_check = lambda: bool(__import__('os').environ.get('OBSIDIAN_VAULT', ''))

def register(reg):
    reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA, check_fn=_check)
