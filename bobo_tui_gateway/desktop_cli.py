"""TICKET-DESK-CLI：`bobo desktop` 子命令 —— 拉起 Electron 桌面端。

新人 clone repo 后 `pip install -e .` 即可用 `bobo`（TUI）与 `bobo desktop`（桌面端）。
桌面端无需 Apple 证书签名：Electron 走 npm 官方签名包，用户自跑不触发 Gatekeeper。

流程：定位 repo 内 apps/desktop/ → 前置检测（node/npm 存在 + Node ≥ 18）→
依赖检测（node_modules 存在且 electron 可执行，缺失则 npm install 带进度输出）→
npm start 拉起 Electron。进程随终端 Ctrl+C 干净退出（信号透传前台进程组）。

模块独立可测：核心逻辑在 run_desktop_in()，路径可注入；测试 mock subprocess/which，
不真实安装依赖。
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

MIN_NODE_MAJOR = 18
_ENV_DESKTOP_DIR = "BOBO_DESKTOP_DIR"   # 测试/自定义注入：覆盖桌面端工程目录


def desktop_dir() -> Path:
    """定位 repo 内 apps/desktop/（pip editable 安装与 dev clone 同构）。

    本模块位于 bobo_tui_gateway/ 下，项目根在其上一级；apps/desktop 在项目根下。
    """
    override = os.environ.get(_ENV_DESKTOP_DIR)
    if override:
        return Path(override)
    root = Path(__file__).resolve().parent.parent
    return root / "apps" / "desktop"


def _node_version() -> str:
    """node --version 原样输出（如 v22.14.0）；检测失败返回空串。"""
    try:
        r = subprocess.run(["node", "--version"], capture_output=True, text=True, timeout=10)
    except Exception:
        return ""
    return (r.stdout or "").strip()


def _parse_major(ver: str) -> int:
    """'v18.20.2' → 18；无法解析返回 0。"""
    if not ver.startswith("v"):
        return 0
    try:
        return int(ver[1:].split(".")[0])
    except (ValueError, IndexError):
        return 0


def check_node() -> tuple:
    """前置检测：node/npm 存在 + Node ≥ 18。返回 (ok: bool, 人话信息: str)。

    检测失败一律返回人话提示（不抛 Python 异常、不打印 Python 栈）。
    """
    node = shutil.which("node")
    if not node:
        return False, "未检测到 Node.js。需要 Node.js ≥ 18，安装方式：brew install node 或官网 https://nodejs.org/"
    npm = shutil.which("npm")
    if not npm:
        return False, "未检测到 npm。需要 Node.js ≥ 18（自带 npm），安装方式：brew install node 或官网 https://nodejs.org/"
    ver = _node_version()
    if _parse_major(ver) < MIN_NODE_MAJOR:
        return False, (
            f"Node.js 版本过低：{ver or '未知'}。需要 Node.js ≥ {MIN_NODE_MAJOR}，"
            "升级方式：brew upgrade node 或官网 https://nodejs.org/"
        )
    return True, f"Node.js {ver} ✓"


def electron_bin(desktop: Path):
    """node_modules 内 electron 可执行文件；不存在返回 None。

    unix 下 .bin/electron（符号链接），Windows 下 .bin/electron.cmd；
    再兜底 electron/dist/electron（npm 布局差异）。
    """
    candidates = [
        desktop / "node_modules" / ".bin" / "electron",
        desktop / "node_modules" / ".bin" / "electron.cmd",
        desktop / "node_modules" / "electron" / "dist" / "electron",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def _npm_install(desktop: Path) -> int:
    """npm install（继承 stdout/stderr，进度清晰可见）；返回退出码。"""
    print("首次运行：检测到桌面端依赖未安装，正在 npm install（可能需要几分钟）…")
    print("  目录：" + str(desktop))
    try:
        r = subprocess.run(["npm", "install"], cwd=str(desktop))
        return r.returncode
    except FileNotFoundError:
        print("✗ 无法执行 npm 命令。请确认 Node.js ≥ 18 已安装：brew install node 或官网 https://nodejs.org/", file=sys.stderr)
        return 127


def run_desktop_in(desktop) -> int:
    """核心流程（路径可注入，便于测试）。desktop: Path | str。"""
    d = Path(desktop)
    if not (d / "package.json").exists():
        print(f"✗ 未找到桌面端工程（缺 package.json）：{d}", file=sys.stderr)
        print("  请确认在 bobo-agent 仓库内安装（pip install -e .），apps/desktop/ 不应缺失。", file=sys.stderr)
        return 1

    ok, msg = check_node()
    if not ok:
        print("✗ " + msg, file=sys.stderr)
        print("  安装 Node.js 后重新运行 `bobo desktop`。", file=sys.stderr)
        return 1
    print(msg)

    if electron_bin(d) is None:
        code = _npm_install(d)
        if code != 0:
            print(f"✗ npm install 失败（退出码 {code}）。", file=sys.stderr)
            print("  请检查：网络连通性 / npm 镜像源 / Node.js 版本（≥ %d）。" % MIN_NODE_MAJOR, file=sys.stderr)
            print("  可手动执行：cd apps/desktop && npm install && npm start", file=sys.stderr)
            return code
        if electron_bin(d) is None:
            print("✗ npm install 已完成但未找到 electron 可执行文件。", file=sys.stderr)
            print("  可手动执行：cd apps/desktop && npm install && npm start", file=sys.stderr)
            return 1

    print("启动 Bobo 桌面端…（Ctrl+C 干净退出）")
    # npm start 继承终端：Ctrl+C → SIGINT 发给前台进程组 → npm/electron 一起退出。
    # 本进程同时忽略 SIGINT（同 entry.py TUI 先例 SIG_IGN），避免 KeyboardInterrupt
    # traceback 污染终端；退出码原样返回。
    import signal
    old_handler = signal.signal(signal.SIGINT, signal.SIG_IGN)
    try:
        return subprocess.run(["npm", "start"], cwd=str(d)).returncode
    except FileNotFoundError:
        print("✗ 无法执行 npm 命令。请确认 Node.js ≥ 18 已安装：brew install node 或官网 https://nodejs.org/", file=sys.stderr)
        return 127
    finally:
        signal.signal(signal.SIGINT, old_handler)


def run_desktop() -> int:
    """bobo desktop 入口（entry.py 分发调用）。"""
    return run_desktop_in(desktop_dir())
