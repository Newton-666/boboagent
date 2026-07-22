"""Bobo TUI Gateway 入口"""

import json
import logging
import os
import signal
import sys

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from bobo_tui_gateway.server import dispatch
from bobo_tui_gateway.transport import write_json

logger = logging.getLogger(__name__)


def _shutdown(signum, frame):
    """SIGINT/SIGTERM 处理：保存会话后退出"""
    from bobo_tui_gateway.server import shutdown_sessions
    shutdown_sessions()
    sys.exit(0)


signal.signal(signal.SIGINT, _shutdown)
signal.signal(signal.SIGTERM, _shutdown)


def resolve_skin() -> dict:
    """返回 TUI 皮肤配置（Bobo 品牌）"""
    return {
        "colors": {
            "ui_primary": "#FFD700",
            "ui_accent": "#FFBF00",
            "ui_border": "#CD7F32",
            "ui_text": "#FFF8DC",
            "banner_title": "#FFD700",
            "banner_accent": "#FFBF00",
            "banner_dim": "#CC9B1F",
            "banner_border": "#CD7F32",
        },
        "branding": {
            "agent_name": "Bobo Agent",
            "prompt_symbol": ">",
            "icon": "",
            "welcome": "你好！我是 Bobo，你的智能助手。",
            "goodbye": "再见！",
            "help_header": "Bobo 命令帮助",
        },
        "banner_logo": "",
        "banner_hero": "",
        "tool_prefix": "|",
    }


def main():
    # 当用户直接运行 `bobo` 命令时，启动 TUI 前端
    import signal
    import subprocess
    import sys
    from pathlib import Path

    # 如果已经是 TUI 的后端进程，直接进入后端逻辑
    if os.environ.get("BOBO_BACKEND"):
        _run_backend()
        return

    # 查找 TUI 文件
    candidates = [
        Path(__file__).parent / "static" / "entry.js",        # pip installed
        Path(__file__).parent.parent / "ui-tui" / "dist" / "entry.js",  # dev clone
        Path.cwd() / "ui-tui" / "dist" / "entry.js",         # cwd
    ]
    tui_path = None
    for p in candidates:
        if p.exists():
            tui_path = p
            break

    if tui_path:
        # 忽略 Ctrl+C — 让 TUI 前端处理中断
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        env = os.environ.copy()
        env["BOBO_BACKEND"] = "1"
        # SIG_IGN 会被 Node 子进程继承，导致 Apple Terminal 上中文 IME
        # 组合事件异常（光标跳、文字重叠、多换行）。preexec_fn 在子进程
        # exec 前恢复 SIGINT 为默认——父进程仍然忽略 Ctrl+C。
        proc = subprocess.Popen(["node", str(tui_path)], env=env,
                                preexec_fn=lambda: signal.signal(signal.SIGINT, signal.SIG_DFL))
        proc.wait()
        return

    # 找不到 TUI
    print("=" * 60)
    print("  Bobo Agent")
    print("=" * 60)
    print()
    print("  TUI not found. Build it first:")
    print("    cd ui-tui && npm install && npm run build")
    print()
    print("  Or run the Python backend directly:")
    print("    BOBO_BACKEND=1 python -m bobo_tui_gateway.entry")
    print("=" * 60)


def _run_backend():
    """Run as TUI backend process (stdin/stdout JSON-RPC)."""

    from pathlib import Path

    # 扫描 Obsidian vault 目录，返回文件树结构
    def _scan_vault_tree(root):
        max_depth = 4
        tree = []
        root_path = Path(root)
        try:
            for entry in sorted(root_path.iterdir(), key=lambda x: (not x.is_dir(), x.name)):
                if entry.name.startswith('.'):
                    continue
                if len(tree) >= 100:
                    break
                if entry.is_dir():
                    subtree = _scan_vault_tree(entry) if max_depth > 0 else []
                    tree.append({"name": entry.name, "type": "folder", "children": subtree})
                elif entry.name.endswith(('.md', '.txt', '.json')):
                    tree.append({"name": entry.name, "type": "file", "path": str(entry)})
        except PermissionError:
            pass
        return tree

    import signal
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    # 发送 ready 事件（包含皮肤配置）
    if not write_json({
        "jsonrpc": "2.0",
        "method": "event",
        "params": {
            "type": "gateway.ready",
            "payload": {"skin": resolve_skin()}
        },
    }):
        sys.exit(0)

    # 检查 API Key — 如果缺失，gateway.ready 已发送，TUI 会显示设置界面
    from config import API_KEY
    if not API_KEY:
        # TUI 会调用 setup.status 检测到未配置，显示 /setup 界面
        logger.warning("DEEPSEEK_API_KEY 未配置，等待用户在 TUI 中设置")

    # 扫描 Obsidian vault，发射笔记文件树
    try:
        vault = os.environ.get("OBSIDIAN_VAULT", "")
        if vault and os.path.isdir(vault):
            notebook_tree = _scan_vault_tree(vault)
            write_json({
                "jsonrpc": "2.0",
                "method": "event",
                "params": {"type": "notes.tree", "payload": {"tree": notebook_tree}}
            })
    except Exception:
        pass

    # 读取并处理请求
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue

        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            write_json({
                "jsonrpc": "2.0",
                "error": {"code": -32700, "message": "parse error"},
                "id": None,
            })
            continue

        resp = dispatch(req)
        if resp is not None:
            if not write_json(resp):
                break  # stdout 写入失败，TUI 已断开

    # stdin 关闭（TUI 断开），保存所有活跃会话
    from bobo_tui_gateway.server import shutdown_sessions
    shutdown_sessions()


if __name__ == "__main__":
    # 如果是从 cron 调用的定时任务，直接执行
    if "--run-schedule" in sys.argv:
        idx = sys.argv.index("--run-schedule")
        if idx + 1 < len(sys.argv):
            name = sys.argv[idx + 1]
            from tools.bobo_schedule import _load_schedules
            schedules = _load_schedules()
            for s in schedules:
                if s["name"] == name:
                    print(f"执行定时任务: {s['name']}")
                    # Load engine and run the task description
                    from config import API_KEY, API_BASE_URL, API_MODEL_NAME
                    from core.llm_caller import create_llm_caller
                    from core.tool_executor import execute_tool
                    from core.engine import Engine
                    from tools import TOOLS_SCHEMA
                    caller = create_llm_caller(API_KEY, API_BASE_URL, API_MODEL_NAME, TOOLS_SCHEMA)
                    engine = Engine(caller, execute_tool)
                    engine.run(s["task"])
                    print(engine.history[-1]["content"] if engine.history else "完成")
                    break
        sys.exit(0)

    main()
