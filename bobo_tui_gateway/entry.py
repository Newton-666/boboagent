"""Bobo TUI Gateway 入口"""

import json
import logging
import os
import signal
import sys
import threading
import time
import atexit
import faulthandler  # TICKET-E1b：环形快照 dump 用（模块顶层，函数内 import 会变局部变量）
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from bobo_tui_gateway.server import dispatch
from bobo_tui_gateway.transport import write_json

# ── 持久运行日志（崩溃根因调查基础设施，2026-07-27）──────────────
_LOG_DIR = os.path.join(_project_root, "data", "logs")
os.makedirs(_LOG_DIR, exist_ok=True)

_handler = TimedRotatingFileHandler(
    os.path.join(_LOG_DIR, "bobo.log"),
    when="midnight", interval=1, backupCount=7, encoding="utf-8"
)
_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s:%(lineno)d %(threadName)s %(message)s"
))
_handler.setLevel(logging.DEBUG)

_root_logger = logging.getLogger()
_root_logger.addHandler(_handler)
_root_logger.setLevel(logging.DEBUG)

# 线程异常捕获：任何线程的未处理异常写日志
_original_thread_excepthook = threading.excepthook

def _log_thread_exception(args):
    logger.critical("线程异常: %s", args.exc_type.__name__ if args.exc_type else "unknown",
                     exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
    _original_thread_excepthook(args)

threading.excepthook = _log_thread_exception

# 系统异常捕获
def _log_sys_exception(exc_type, exc_value, exc_traceback):
    logger.critical("进程异常: %s", exc_type.__name__, exc_info=(exc_type, exc_value, exc_traceback))
    sys.__excepthook__(exc_type, exc_value, exc_traceback)

sys.excepthook = _log_sys_exception

# ── TICKET-E1b：stack_dump 环形快照（log 卫生）──────────────
# 默认模式：每 120s 覆盖写一屏（w 模式），文件恒定只留最新一屏。
# BOBO_STACK_DUMP=1：保留旧版 repeat 追加模式（全量连拍，战时排查用）。
_DUMP_INTERVAL = 120


def _snapshot_loop(dump_path: str, interval: float):
    """环形快照循环：每 interval 秒覆盖写一屏（daemon 线程运行）。"""
    while True:
        time.sleep(interval)
        try:
            with open(dump_path, "w", encoding="utf-8", errors="replace") as fd:
                faulthandler.dump_traceback(file=fd)
        except Exception:
            pass  # 快照失败静默降级，不影响主流程


def _setup_stack_dump(log_dir: str) -> str:
    """配置 stack_dump 快照，返回模式名（'ring' 环形 / 'append' 连拍）。"""
    dump_path = os.path.join(log_dir, "stack_dump.log")
    if os.environ.get("BOBO_STACK_DUMP") == "1":
        # 战时模式：全量连拍，追加写，与旧版行为一致
        fd = open(dump_path, "a")
        faulthandler.dump_traceback_later(120, repeat=True, file=fd)
        atexit.register(lambda: fd.close())
        return "append"
    # 默认环形快照：daemon 后台线程每 120s 覆盖写最新一屏
    threading.Thread(
        target=_snapshot_loop,
        args=(dump_path, _DUMP_INTERVAL),
        daemon=True,
        name="stack-dump-snapshot",
    ).start()
    return "ring"


try:
    _setup_stack_dump(_LOG_DIR)
except Exception:
    pass

logger = logging.getLogger(__name__)


def _shutdown(signum, frame):
    """SIGINT/SIGTERM 处理：保存会话后退出"""
    logger.critical("gateway 退出: 收到信号 %s", signum)
    from bobo_tui_gateway.server import shutdown_sessions
    shutdown_sessions()
    sys.exit(0)


signal.signal(signal.SIGINT, _shutdown)
signal.signal(signal.SIGTERM, _shutdown)


# ── TICKET-030：启动计时 + 工具预热（守卫已拆除，auto-exit 接管叠罗汉治理）──
_BACKEND_T0: "float | None" = None   # _run_backend 入口的 monotonic 时间
_READY_EMITTED = False               # 启动打点每进程只发一次


def resolve_skin() -> dict:
    """返回 TUI 皮肤配置（Bobo 品牌）"""
    return {
        "colors": {
            "ui_primary": "#C88E8E",
            "ui_accent": "#8AAAA0",
            "ui_border": "#8CB8A0",
            "ui_text": "#F8F2E8",
            "ui_ok": "#8AAAA0",
            "ui_label": "#B09AAA",
            "ui_warn": "#D4A9A0",
            "prompt": "#EEEEEE",
            "shell_dollar": "#7EBF9A",
            "banner_title": "#C88E8E",
            "banner_accent": "#8AAAA0",
            "banner_dim": "#C4B8AE",
            "banner_border": "#C4B8AE",
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
        try:
            proc = subprocess.Popen(["node", str(tui_path)], env=env,
                                    preexec_fn=lambda: signal.signal(signal.SIGINT, signal.SIG_DFL))
        except FileNotFoundError:
            print("=" * 60)
            print("  未检测到 Node.js — Bobo TUI 依赖 Node.js 运行")
            print("=" * 60)
            print()
            print("  macOS:  brew install node")
            print("  Ubuntu: sudo apt install nodejs npm")
            print("  或下载: https://nodejs.org")
            print()
            print("  安装 Node.js 后重新运行 bobo。")
            print("=" * 60)
            sys.exit(1)
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


def _scan_vault_tree(root):
    """扫描 Obsidian vault 目录，返回文件树结构"""
    from pathlib import Path
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


def _serve_connection(lines_iter):
    """服务一条连接（stdio 或 socket）：发 ready → 笔记树 → RPC 主循环。

    返回退出原因："eof" / "write_broken"。不保存会话、不退出进程——
    调用方决定连接结束后怎么办（stdio 模式退出；socket 模式等待重连）。
    """
    # 发送 ready 事件（包含皮肤配置）
    if not write_json({
        "jsonrpc": "2.0",
        "method": "event",
        "params": {
            "type": "gateway.ready",
            "payload": {"skin": resolve_skin()}
        },
    }):
        return "write_broken"

    # TICKET-026：启动就绪打点（每进程只打一次；socket 重连不重复计数）
    global _READY_EMITTED
    if not _READY_EMITTED and _BACKEND_T0 is not None:
        _READY_EMITTED = True
        ready_ms = int((time.monotonic() - _BACKEND_T0) * 1000)
        logger.critical("gateway 启动就绪: 耗时 %dms（pid=%s）", ready_ms, os.getpid())
        try:
            from core.event_bus import event_bus as _bus
            _bus.write("gateway.startup", {"ready_ms": ready_ms, "pid": os.getpid()})
        except Exception:
            pass

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
    for raw in lines_iter:
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
        # 票 W：gateway 入口登记——每条 RPC 都留痕，TUI 是否背地里
        # 发过消息（无声死亡案的盲点）从此可查
        try:
            logger.debug("rpc.recv method=%s id=%s", req.get("method"), req.get("id"))
        except Exception:
            pass
        if resp is not None:
            if not write_json(resp):
                logger.warning("写入失败，前端已断开（rpc=%s）", req.get("method"))
                return "write_broken"

    return "eof"


def _run_socket_backend(sock_path: str):
    """TICKET-018：unix socket 服务端模式——gateway 自己的命自己扛。

    python bind/listen，TUI（Node）作为客户端连接。前端侧任何故障
    （fd 被原生层误关、Node 崩溃、管道被掐）都只表现为"客户端断开"，
    gateway 进程不退出、会话状态全保留，回到 accept 等待重连。

    TICKET-027：前端断开后若超过 BOBO_GW_IDLE_TIMEOUT 秒（默认 60）
    无重连，则自动退出，根治多次重启导致的 gateway 叠罗汉。
    设为 0 恢复旧行为（永不自动退出）。
    """
    import socket as _socket

    from bobo_tui_gateway.transport import SocketTransport, set_transport

    _IDLE_TIMEOUT = 60
    try:
        _IDLE_TIMEOUT = int(os.environ.get("BOBO_GW_IDLE_TIMEOUT", "60"))
    except (ValueError, TypeError):
        pass

    try:
        os.unlink(sock_path)
    except FileNotFoundError:
        pass

    srv = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
    srv.bind(sock_path)
    os.chmod(sock_path, 0o600)
    srv.listen(1)
    if _IDLE_TIMEOUT > 0:
        srv.settimeout(1.0)  # 每 1 秒检查空闲超时
    logger.critical("gateway socket 模式: 监听 %s（前端断开不再致命，等待重连）", sock_path)

    _idle_since: float = time.monotonic()  # TICKET-030：初始化为 listen 时刻，堵住"从未连接的孤儿永不退出"盲区
    while True:
        try:
            conn, _ = srv.accept()
        except _socket.timeout:
            if _IDLE_TIMEOUT > 0 and _idle_since is not None:
                if time.monotonic() - _idle_since > _IDLE_TIMEOUT:
                    logger.critical("gateway socket: 空闲 %ds 无重连，自动退出", _IDLE_TIMEOUT)
                    break
            continue
        except OSError as e:
            logger.critical("gateway socket: accept 异常 %r，继续监听", e)
            continue

        _idle_since = None  # 有连接，重置空闲计时
        logger.critical("gateway socket: 前端已连接")
        set_transport(SocketTransport(conn))
        try:
            reader = conn.makefile("r", encoding="utf-8", newline="\n")
            reason = _serve_connection(reader)
            if _idle_since is None:
                _idle_since = time.monotonic()
            if _IDLE_TIMEOUT > 0:
                logger.critical("gateway socket: 前端断开（原因=%s），%ds 内无重连将自动退出", reason, _IDLE_TIMEOUT)
            else:
                logger.critical("gateway socket: 前端断开（原因=%s），进程保持存活，等待重连", reason)
        except OSError as e:
            if _idle_since is None:
                _idle_since = time.monotonic()
            logger.critical("gateway socket: 连接异常 %r，%ds 内无重连将自动退出", e, _IDLE_TIMEOUT)
        finally:
            try:
                conn.close()
            except OSError:
                pass

    # 空闲超时退出：保存所有活跃会话
    from bobo_tui_gateway.server import shutdown_sessions
    shutdown_sessions()
    logger.critical("gateway socket: 进程正常退出")


def _run_backend():
    """Run as TUI backend process (JSON-RPC over stdio pipes or unix socket)."""

    import signal
    signal.signal(signal.SIGINT, signal.SIG_IGN)

    # TICKET-030：启动计时起点（守卫已拆除，auto-exit 接管叠罗汉治理）
    global _BACKEND_T0
    _BACKEND_T0 = time.monotonic()

    # TICKET-027：后台预热工具导入——避免堵在 session.create 关键路径，
    # 消除 TUI 长时间卡在 "summoning hermes…" 的体验。
    def _preload_tools():
        try:
            from tools import TOOLS_SCHEMA  # noqa: F811 — 仅触发缓存
            logger.debug("工具预热完成: %d 个工具", len(TOOLS_SCHEMA))
        except Exception:
            logger.warning("工具预热失败（不影响启动）", exc_info=True)
    threading.Thread(target=_preload_tools, daemon=True, name="tool-preloader").start()

    # TICKET-018：socket 模式——前端故障不再杀死 gateway
    sock_path = os.environ.get("BOBO_GW_SOCKET", "").strip()
    if sock_path:
        _run_socket_backend(sock_path)
        return

    reason = _serve_connection(sys.stdin)

    # 主循环正常结束：登记死因（EOF 或 stdout 断裂）
    if reason == "write_broken":
        logger.critical("gateway 退出: stdout 断裂")
    else:
        logger.critical("gateway 退出: stdin EOF（父进程关闭了管道）")
    logger.critical("gateway 退出: 主循环结束")

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
