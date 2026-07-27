"""handlers/tools.py — 工具/文件/补全 handler。"""

from bobo_tui_gateway.server_utils import ok, err


def handle_tools_list(params: dict, rid: str) -> dict:
    from tools import TOOLS_SCHEMA
    tools = []
    for t in TOOLS_SCHEMA:
        name = t.get("function", t).get("name", "")
        desc = t.get("function", t).get("description", "")
        tools.append({"name": name, "description": desc})
    return ok(rid, {"tools": tools})


def handle_file_read(params: dict, rid: str) -> dict:
    """读取文件内容（供桌面端插件使用）"""
    filepath = params.get("filepath", "")
    if not filepath:
        return err(rid, -32000, "缺少 filepath 参数")
    try:
        from tools.read_local_file import execute as read_file
        content = read_file(filepath=filepath, max_chars=10000)
        return ok(rid, {"content": content})
    except Exception as e:
        return err(rid, -32000, str(e))


def handle_completion(params: dict, rid: str) -> dict:
    """Return autocomplete items for the current input."""
    return ok(rid, {"items": []})


# ── 注册 ──

def register(reg_method, ctx):
    reg_method("tools.list")(handle_tools_list)
    reg_method("file.read")(handle_file_read)
    reg_method("completion")(handle_completion)
