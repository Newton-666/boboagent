"""handlers/misc.py — 杂项 handler（shell/图片/粘贴/终端/拖放/项目根目录）。"""

import os

from bobo_tui_gateway.server_utils import ok, err, emit


def handle_shell_exec(params: dict, rid: str) -> dict:
    import subprocess
    command = params.get("command", "")
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=10)
        # shell=True 仅用于 TUI 斜杠命令，引擎内的 execute_terminal 有安全分级
        output = result.stdout or result.stderr or "(无输出)"
        return ok(rid, {"output": output.strip()})
    except Exception as e:
        return ok(rid, {"output": f"错误: {e}"})


def handle_image_attach(params: dict, rid: str) -> dict:
    return ok(rid, {"attached": True})


def handle_paste_collapse(params: dict, rid: str) -> dict:
    return ok(rid, {"path": None})


def handle_terminal_resize(params: dict, rid: str) -> dict:
    return ok(rid, {"resized": True})


def handle_input_detect_drop(params: dict, rid: str) -> dict:
    return ok(rid, {"dropped": False})


def _scan_directory(path: str, max_depth: int = 4) -> list:
    """递归扫描目录，返回文件树结构"""
    tree = []
    try:
        for entry in sorted(os.scandir(path), key=lambda e: (not e.is_dir(), e.name)):
            if entry.name.startswith('.'):
                continue
            if len(tree) >= 100:
                break
            if entry.is_dir():
                if max_depth > 0:
                    children = _scan_directory(entry.path, max_depth - 1)
                else:
                    children = []
                tree.append({"name": entry.name, "type": "folder", "children": children})
            else:
                ext = os.path.splitext(entry.name)[1].lower()
                if ext in ('.py', '.js', '.ts', '.jsx', '.tsx', '.html', '.css', '.json', '.md', '.txt', '.c', '.h', '.go', '.rs', '.rb', '.yaml', '.yml', '.toml', '.sh', '.env', '.gitignore', '.cfg', '.ini', '.conf', '.sql', '.java', '.swift', '.kt'):
                    tree.append({"name": entry.name, "type": "file", "path": entry.path})
    except PermissionError:
        pass
    return tree


def handle_project_set_root(params: dict, rid: str, ctx) -> dict:
    """设置项目根目录，扫描并发射文件树"""
    root = params.get("path", "")
    if not root or not os.path.isdir(root):
        return err(rid, -32000, "路径不存在或不是目录")
    tree = _scan_directory(root)
    emit("project.tree", "", {"tree": tree, "root": root})
    # 注入 system 消息到当前会话，通知 Bobo 项目路径
    sid = params.get("session_id", "")
    if sid and sid in ctx.sessions:
        with ctx.sessions_lock:
            session = ctx.sessions.get(sid)
            if session:
                session.setdefault("messages", []).append({
                    "role": "system",
                    "content": f"📁 已导入项目: {root}。问及文件时，优先从该项目目录查找。"
                })
    return ok(rid, {"root": root, "count": len(tree)})


# ── 注册 ──

def register(reg_method, ctx):
    reg_method("shell.exec")(handle_shell_exec)
    reg_method("image.attach")(handle_image_attach)
    reg_method("paste.collapse")(handle_paste_collapse)
    reg_method("terminal.resize")(handle_terminal_resize)
    reg_method("input.detect_drop")(handle_input_detect_drop)
    reg_method("project.set_root")(lambda params, rid: handle_project_set_root(params, rid, ctx))
