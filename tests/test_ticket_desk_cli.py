"""TICKET-DESK-CLI 回归测试 — bobo desktop 子命令 + 新人上手路径。

覆盖（owner 圈定）：
- CLI-1 子命令路由：`bobo desktop` argv → 分发到 desktop_cli.run_desktop（不碰 TUI 主流程）
- CLI-2 node 缺失人话提示：无 node/npm 时打印"Node.js ≥ 18 + brew install node"，无 Python 栈
- CLI-3 node_modules 缺失触发 npm install（mock npm，不真实安装）→ 安装成功后再 npm start
- CLI-4 electron 已存在跳过安装 → 直接 npm start
- CLI-5 npm install 失败 → 引导信息 + 返回退出码
- CLI-6 桌面工程缺失（无 package.json）→ 人话报错
- CLI-7 TUI 既有行为零改动：entry.py 分发分支不触碰 BOBO_BACKEND/TUI 启动逻辑；pyproject 入口未变
"""

import os
import shutil
import subprocess
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ENTRY = ROOT / "bobo_tui_gateway" / "entry.py"
DESKTOP_CLI = ROOT / "bobo_tui_gateway" / "desktop_cli.py"
PYPROJECT = ROOT / "pyproject.toml"
README = ROOT / "README.md"


def _patch_subprocess(monkeypatch, fake_run):
    """替换 desktop_cli 模块级 subprocess 名（不碰全局 subprocess，防误伤 pytest 内部）。"""
    import bobo_tui_gateway.desktop_cli as dc
    monkeypatch.setattr(dc, "subprocess", types.SimpleNamespace(run=fake_run))


def _patch_which(monkeypatch, fake_which):
    """替换 desktop_cli 模块级 shutil 名（不碰全局 shutil.which）。"""
    import bobo_tui_gateway.desktop_cli as dc
    monkeypatch.setattr(dc, "shutil", types.SimpleNamespace(which=fake_which))


class FakeProc:
    def __init__(self, returncode=0, stdout=""):
        self.returncode = returncode
        self.stdout = stdout


def _make_desktop(tmp_path) -> Path:
    """构造最小桌面工程：package.json（真实路径布局，无 node_modules）。"""
    d = tmp_path / "apps" / "desktop"
    d.mkdir(parents=True)
    (d / "package.json").write_text('{"name":"bobo-desktop","scripts":{"start":"electron ."}}', encoding="utf-8")
    return d


def _fake_subprocess(script):
    """subprocess.run mock：按 (argv, FakeProc) 顺序匹配；未匹配抛错。记录 calls。"""
    calls = []

    def _run(args, **kwargs):
        calls.append((list(args), kwargs))
        for argv, proc in script:
            if list(args) == list(argv):
                # proc 可为 FakeProc 实例，或 callable（模拟副作用，如安装后落地 electron）
                return proc(args, **kwargs) if callable(proc) else proc
        if list(args) == ["node", "--version"]:
            return FakeProc(stdout="v22.14.0\n")   # 默认 Node 版本检测通过
        raise AssertionError(f"unexpected subprocess call: {args}")

    return _run, calls


# ── CLI-1 子命令路由 ──────────────────────────────────────────────────

def test_cli1_desktop_subcommand_routes(monkeypatch):
    """`bobo desktop` argv → entry.main() 分发到 run_desktop 并 sys.exit(其返回值)。"""
    import bobo_tui_gateway.desktop_cli as dc
    import bobo_tui_gateway.entry as entry

    called = []

    monkeypatch.delenv("BOBO_BACKEND", raising=False)   # 测试进程本身是后端（自举），必须清除才走分发
    monkeypatch.setattr(sys, "argv", ["bobo", "desktop"])
    monkeypatch.setattr(dc, "run_desktop", lambda: (called.append(1), 0)[1])
    with pytest.raises(SystemExit) as e:
        entry.main()
    assert e.value.code == 0, "bobo desktop 应以 run_desktop 返回值退出"
    assert called == [1], "必须分发到 desktop_cli.run_desktop"


def test_cli1_desktop_subcommand_in_entry():
    """分发分支必须位于 BOBO_BACKEND 检查之后、TUI 启动之前（主流程零改动）。"""
    src = ENTRY.read_text(encoding="utf-8")
    i_backend = src.index('if os.environ.get("BOBO_BACKEND")')
    i_desktop = src.index('sys.argv[1] == "desktop"')
    i_tui = src.index("tui_path = _find_tui_path()")
    assert i_backend < i_desktop < i_tui, "desktop 分支必须在 BOBO_BACKEND 之后、TUI 之前"
    # TUI 既有逻辑保留：后端进程分支 / _find_tui_path / SIG_IGN 处理
    assert 'env["BOBO_BACKEND"] = "1"' in src, "TUI 后端启动逻辑必须保留"


# ── CLI-2 node 缺失人话提示 ───────────────────────────────────────────

def test_cli2_node_missing_human_message(monkeypatch, tmp_path, capsys):
    """无 node → 人话提示（Node.js ≥ 18 / brew install node），无 Python 栈、退出码 1。"""
    import bobo_tui_gateway.desktop_cli as dc

    d = _make_desktop(tmp_path)
    _patch_which(monkeypatch, lambda name: None if name == "node" else "/usr/bin/npm")
    rc = dc.run_desktop_in(d)
    out = capsys.readouterr()
    assert rc == 1, "node 缺失应返回 1"
    assert "Node.js ≥ 18" in out.err, f"必须提示 Node 版本要求，实际: {out.err}"
    assert "brew install node" in out.err, f"必须给安装引导，实际: {out.err}"
    assert "Traceback" not in out.err, "禁止 Python 栈"


def test_cli2_npm_missing_human_message(monkeypatch, tmp_path, capsys):
    """node 存在但 npm 缺失 → 人话提示。"""
    import bobo_tui_gateway.desktop_cli as dc

    d = _make_desktop(tmp_path)
    _patch_which(monkeypatch, lambda name: "/usr/bin/node" if name == "node" else None)
    rc = dc.run_desktop_in(d)
    out = capsys.readouterr()
    assert rc == 1
    assert "npm" in out.err and "Node.js ≥ 18" in out.err


def test_cli2_node_version_too_low(monkeypatch, tmp_path, capsys):
    """node 版本 < 18 → 人话提示升级。"""
    import bobo_tui_gateway.desktop_cli as dc

    d = _make_desktop(tmp_path)
    _patch_which(monkeypatch, lambda name: "/usr/bin/node" if name == "node" else "/usr/bin/npm")

    def _fake_run(args, **kwargs):
        if list(args) == ["node", "--version"]:
            return FakeProc(stdout="v16.20.2\n")
        raise AssertionError(f"unexpected call: {args}")

    _patch_subprocess(monkeypatch, _fake_run)
    rc = dc.run_desktop_in(d)
    out = capsys.readouterr()
    assert rc == 1
    assert "Node.js 版本过低" in out.err and "brew upgrade node" in out.err


def test_cli2_parse_major():
    import bobo_tui_gateway.desktop_cli as dc
    assert dc._parse_major("v22.14.0") == 22
    assert dc._parse_major("v18.20.2") == 18
    assert dc._parse_major("v6.0.0") == 6
    assert dc._parse_major("garbage") == 0


# ── CLI-3/4/5 依赖检测与安装流程（mock npm，不真实安装）──────────────

def test_cli3_node_modules_missing_triggers_install(monkeypatch, tmp_path, capsys):
    """node_modules 缺失 → npm install（mock）→ 成功后 npm start。"""
    import bobo_tui_gateway.desktop_cli as dc

    d = _make_desktop(tmp_path)

    def _fake_install(args, **kwargs):
        # 模拟 npm install 成功落地 electron 可执行
        bindir = d / "node_modules" / ".bin"
        bindir.mkdir(parents=True, exist_ok=True)
        (bindir / "electron").write_text("#!/bin/sh\n", encoding="utf-8")
        return FakeProc()

    fake_run, calls = _fake_subprocess([(["npm", "install"], _fake_install), (["npm", "start"], FakeProc())])
    _patch_subprocess(monkeypatch, fake_run)
    rc = dc.run_desktop_in(d)
    out = capsys.readouterr()
    assert rc == 0, f"安装+启动应返回 0，实际 {rc}"
    argv_seq = [c[0] for c in calls if c[0][0] == "npm"]  # 过滤 node --version 检测
    assert argv_seq == [["npm", "install"], ["npm", "start"]], f"调用序错误: {argv_seq}"
    assert "npm install" in out.out, "必须输出安装进度提示"
    assert "首次运行" in out.out


def test_cli4_electron_present_skips_install(monkeypatch, tmp_path, capsys):
    """electron 已存在 → 跳过 npm install，直接 npm start。"""
    import bobo_tui_gateway.desktop_cli as dc

    d = _make_desktop(tmp_path)
    bindir = d / "node_modules" / ".bin"
    bindir.mkdir(parents=True)
    (bindir / "electron").write_text("#!/bin/sh\n", encoding="utf-8")

    sigint_state = {}

    def _check_sigint(args, **kwargs):
        import signal
        sigint_state["handler"] = signal.getsignal(signal.SIGINT)
        return FakeProc()

    fake_run, calls = _fake_subprocess([(["npm", "start"], _check_sigint)])
    _patch_subprocess(monkeypatch, fake_run)
    rc = dc.run_desktop_in(d)
    assert rc == 0
    argv_seq = [c[0] for c in calls if c[0][0] == "npm"]  # 过滤 node --version 检测
    assert argv_seq == [["npm", "start"]], f"electron 存在时不应 npm install: {argv_seq}"
    assert sigint_state["handler"] == __import__("signal").SIG_IGN, \
        "npm start 期间必须忽略 SIGINT（Ctrl+C 干净退出，无 KeyboardInterrupt traceback）"
    assert __import__("signal").getsignal(__import__("signal").SIGINT) != __import__("signal").SIG_IGN, \
        "npm start 结束后必须恢复 SIGINT handler"


def test_cli5_npm_install_failure_guidance(monkeypatch, tmp_path, capsys):
    """npm install 失败 → 返回退出码 + 引导信息（网络/镜像/手动命令）。"""
    import bobo_tui_gateway.desktop_cli as dc

    d = _make_desktop(tmp_path)
    fake_run, _ = _fake_subprocess([(["npm", "install"], FakeProc(returncode=1))])
    _patch_subprocess(monkeypatch, fake_run)
    rc = dc.run_desktop_in(d)
    out = capsys.readouterr()
    assert rc == 1, "install 失败应透传退出码"
    assert "npm install 失败" in out.err
    assert "cd apps/desktop && npm install && npm start" in out.err, "必须给手动引导"


def test_cli5_install_done_but_no_electron(monkeypatch, tmp_path, capsys):
    """install 成功但 electron 仍缺失 → 引导手动排查。"""
    import bobo_tui_gateway.desktop_cli as dc

    d = _make_desktop(tmp_path)
    fake_run, _ = _fake_subprocess([(["npm", "install"], FakeProc())])  # 不落地 electron
    _patch_subprocess(monkeypatch, fake_run)
    rc = dc.run_desktop_in(d)
    out = capsys.readouterr()
    assert rc == 1
    assert "未找到 electron 可执行文件" in out.err


def test_cli6_desktop_project_missing(tmp_path, capsys):
    """apps/desktop 无 package.json → 人话报错（仓库结构异常）。"""
    import bobo_tui_gateway.desktop_cli as dc

    d = tmp_path / "apps" / "desktop"
    d.mkdir(parents=True)  # 空目录，无 package.json
    rc = dc.run_desktop_in(d)
    out = capsys.readouterr()
    assert rc == 1
    assert "package.json" in out.err and "pip install -e ." in out.err


def test_cli6_desktop_dir_env_override(monkeypatch, tmp_path):
    """BOBO_DESKTOP_DIR 环境变量可注入桌面工程目录。"""
    import bobo_tui_gateway.desktop_cli as dc

    monkeypatch.setenv("BOBO_DESKTOP_DIR", str(tmp_path / "custom"))
    assert dc.desktop_dir() == tmp_path / "custom"
    monkeypatch.delenv("BOBO_DESKTOP_DIR")
    assert dc.desktop_dir().name == "desktop"


# ── CLI-7 TUI 既有行为零改动 ──────────────────────────────────────────

def test_cli7_tui_behavior_unchanged():
    """bobo 主入口与 pyproject 脚本零改动；TUI 启动链完整保留。"""
    # pyproject.toml：bobo 主入口未动（无新增 console script，仍是 entry:main）
    pp = PYPROJECT.read_text(encoding="utf-8")
    assert 'bobo = "bobo_tui_gateway.entry:main"' in pp, "bobo 主入口必须保持不变"
    assert "bobo-desktop" not in pp, "不得新增独立 bobo-desktop 脚本（子命令分发即可）"
    # entry.py：TUI 链路（_find_tui_path / BOBO_BACKEND / SIG_IGN / node 启动）全保留
    src = ENTRY.read_text(encoding="utf-8")
    for needle in ["def _find_tui_path", "def _run_backend", "BOBO_BACKEND",
                   "tui_path = _find_tui_path()", "preexec_fn", "node"]:
        assert needle in src, f"TUI 启动链元素缺失: {needle}"
    # 分发段必须为锚点段包裹（V4/V4B 守卫据此放行）
    assert "# ── TICKET-DESK-CLI：`bobo desktop` 子命令 → Electron 桌面端（锚点段开始）──" in src
    assert "# ── end TICKET-DESK-CLI ──" in src, "DESK-CLI 锚点段必须闭合"
    # desktop_cli 独立成模块（entry 只加分发，主流程零改动）
    assert DESKTOP_CLI.exists(), "desktop_cli.py 必须存在"


def test_cli7_readme_quick_start():
    """README 快速开始：clone → pip install -e . → bobo / bobo desktop + .env 指引。"""
    readme = README.read_text(encoding="utf-8")
    assert "## Quick Start — Developer (from source)" in readme, "缺开发者快速开始一节"
    assert "git clone https://github.com/Newton-666/boboagent.git" in readme
    assert "pip install -e ." in readme
    assert "bobo desktop" in readme, "必须覆盖 bobo desktop 命令"
    assert "npm install" in readme, "必须说明首次自动装依赖"
    assert "Node.js ≥ 18" in readme or "Node.js v18+" in readme, "必须说明 Node 前置要求"
    assert "Configuration" in readme and "[Configuration](#configuration)" in readme, \
        "必须指向现有配置说明（不重复造）"
    assert "~/.bobo/.env" in readme and "data/.env" in readme, "必须给 .env 配置位置"
