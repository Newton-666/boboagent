"""票 SAFETY-1 专项测试：进程杀灭白名单 + 后端退出码 0 自动重启 + 1345 空元素守卫。

2026-08-16 两次真实事故（Kimi 取证定案）：
- 18:53 bobo 执行"杀孤儿进程"时 pkill -f 误杀自身后端 → SIGTERM 优雅退出 code 0
  → Electron 只对非 0 退出码重启 → owner 桌面端永久断连
- 20:41 清理环境时 SIGKILL 误杀 owner 正在用的桌面端渲染进程（[renderer-gone]
  reason=killed exitCode=9）→ 白屏
- apps/desktop/dist/index.html:1345 反复报 Cannot set properties of null
  (setting 'textContent')（owner 实例前端日志 19:32-20:15 出现 9 次）

覆盖：
① command_safety.py 进程杀灭分级（拦截/审批/放行三档）
② main.cjs 后端无论退出码都自动重启（用户主动退出除外）
③ index.html:1345 空元素守卫存在
"""

import os
import re
import subprocess
from pathlib import Path

import pytest

from core.command_safety import (
    classify_command,
    classify_side_effect,
    is_blacklisted,
    is_high_risk_tool,
    classify_kill_command,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent
_MAIN_CJS = _REPO_ROOT / "apps" / "desktop" / "electron" / "main.cjs"
_INDEX_HTML = _REPO_ROOT / "apps" / "desktop" / "dist" / "index.html"

KILL_CONFIRM_FRAGMENT = "指定具体 PID 并说明理由"


# ── ① 进程杀灭白名单 ──────────────────────────────────────────────

BLOCK_CASES = [
    # 模式匹配杀灭（黑名单硬拦）
    "pkill -f python",
    "pkill python",
    "killall python",
    "killall -9 node",
    # 按进程名 kill（非数字目标）
    "kill python",
    "kill -9 python",
    "kill -TERM python",
    "kill -s TERM python",
    "kill electron",
    # 杀灭目标含 bobo 自身/桌面端标识
    "kill bobo_backend",
    "kill -9 bobo_tui_gateway",
    "kill -9 bobo-gateway",
    "kill -9 gateway_desktop",
]

CONFIRM_CASES = [
    # 对具体数字 PID 的 kill → 强制人工确认（普通模式弹审批 / AUTO 拒绝）
    "kill 12345",
    "kill -9 12345",
    "kill -TERM 12345",
    "kill -s TERM 12345",
    "kill --signal=KILL 12345",
    "kill 12345 67890",
    "kill 12345 && echo bobo done",   # 链式后续 echo bobo 不误伤
    "kill 12345 # bobo",              # 注释里的 bobo 不误伤
    "ls && kill 12345",               # 链式 kill 也审批
]

SAFE_CASES = [
    "pgrep python",                    # 只查询不杀灭
    "ps aux | grep python",            # 查询
    'echo "kill python"',              # 引号内字样不参与
    "echo a # kill 12345",             # 注释里的 kill 不触发
    "ls -la",
    "cat /tmp/x.py",
]


@pytest.mark.parametrize("cmd", BLOCK_CASES)
def test_kill_block_cases(cmd):
    """模式匹配杀灭 / bobo 标识目标：黑名单硬拦，任何模式拒绝。"""
    level, reason = classify_command(cmd)
    assert level == "dangerous", f"{cmd!r} 应判 dangerous，实际 {level} ({reason})"
    # AUTO 模式：external-irreversible → 拒绝 + 待人工清单
    slevel, _ = classify_side_effect(cmd)
    assert slevel == "external-irreversible", f"{cmd!r} AUTO 应拒绝"
    # 普通模式：is_high_risk_tool 必须返回需确认
    high_risk, hr_reason = is_high_risk_tool("execute_terminal", {"command": cmd})
    assert high_risk, f"{cmd!r} 应弹审批/拦截"
    assert "误杀" in hr_reason or "禁止" in hr_reason or "指定" in hr_reason, hr_reason


@pytest.mark.parametrize("cmd", CONFIRM_CASES)
def test_kill_confirm_cases(cmd):
    """数字 PID 的 kill：强制审批（普通模式弹窗 / AUTO 拒绝），不静默执行。"""
    level, reason = classify_command(cmd)
    assert level == "gray", f"{cmd!r} 应判 gray（审批），实际 {level} ({reason})"
    assert "进程杀灭需人工确认" in reason, reason
    # AUTO 模式：不允许静默放行（external-irreversible → 拒绝）
    slevel, _ = classify_side_effect(cmd)
    assert slevel == "external-irreversible", f"{cmd!r} AUTO 下不得放行"
    # 普通模式：is_high_risk_tool 必须返回需确认，且文案含需求人话
    high_risk, hr_reason = is_high_risk_tool("execute_terminal", {"command": cmd})
    assert high_risk, f"{cmd!r} 应弹审批"
    assert KILL_CONFIRM_FRAGMENT in hr_reason, hr_reason


@pytest.mark.parametrize("cmd", SAFE_CASES)
def test_kill_safe_cases(cmd):
    """查询/字样/注释类：不受影响，正常放行。"""
    high_risk, _ = is_high_risk_tool("execute_terminal", {"command": cmd})
    assert not high_risk, f"{cmd!r} 不应弹审批"


def test_kill_confirm_pid_shows_identity():
    """审批提示必须包含目标进程身份（ps 现场查询）。"""
    own_pid = os.getpid()  # 当前 python 测试进程，必然存在
    high_risk, reason = is_high_risk_tool(
        "execute_terminal", {"command": f"kill {own_pid}"})
    assert high_risk
    assert "目标进程" in reason or str(own_pid) in reason, reason
    # ps 输出应包含 python（本测试进程的 comm）
    assert "python" in reason.lower(), reason


def test_kill_block_is_blacklisted():
    """pkill/killall 进入 is_blacklisted（AUTO 入口硬锁）。"""
    assert is_blacklisted("pkill -f python")[0] is True
    assert is_blacklisted("killall python")[0] is True
    # 数字 PID 的 kill 不进黑名单（走审批路径，不误伤）
    assert is_blacklisted("kill 12345")[0] is False


def test_kill_classify_direct():
    """classify_kill_command 三档分级。"""
    assert classify_kill_command("pkill -f python")[0] == "dangerous"
    assert classify_kill_command("killall python")[0] == "dangerous"
    assert classify_kill_command("kill python")[0] == "dangerous"
    assert classify_kill_command("kill 12345")[0] == "confirm"
    assert classify_kill_command("kill -9 12345")[0] == "confirm"
    assert classify_kill_command("kill bobo_gateway")[0] == "dangerous"
    assert classify_kill_command("pgrep python")[0] == "safe"


# ── ② main.cjs：后端退出码 0 也自动重启 ───────────────────────────

_MAIN_CJS_TEXT = _MAIN_CJS.read_text(encoding="utf-8")


def test_main_cjs_has_stop_flag():
    """用户主动停止标志存在（Cmd+Q / 改配置时置位）。"""
    assert "let backendStopRequested = false" in _MAIN_CJS_TEXT
    assert "backendStopRequested = true" in _MAIN_CJS_TEXT      # stopBackend 置位
    assert "backendStopRequested = false" in _MAIN_CJS_TEXT     # startBackend 重置


def test_main_cjs_restart_regardless_of_exit_code():
    """核心守卫：退出码 0 且非主动停止也要重启（18:53 事故根因）。"""
    # exit handler 中重启条件不再绑定 code !== 0
    assert "code !== 0 && backendRestartCount" not in _MAIN_CJS_TEXT
    # 主动停止是唯一豁免
    assert "if (backendStopRequested) return" in _MAIN_CJS_TEXT
    # 重启分支保留 backoff 与上限
    assert "if (backendRestartCount < MAX_BACKEND_RESTARTS)" in _MAIN_CJS_TEXT


def test_main_cjs_exit_handler_extract():
    """提取 exit handler 的判定骨架，逐条断言关键语义。"""
    m = re.search(r"backendProcess\.on\('exit'.*?\n  \}\)", _MAIN_CJS_TEXT, re.S)
    assert m, "未找到 backendProcess.on('exit') handler"
    handler = m.group(0)
    # 退出码 0 的提示文案（不再静默）
    assert "自动重启中" in handler
    # 重启计数不区分退出码
    assert "backendRestartCount++" in handler


@pytest.mark.skipif(subprocess.run(["which", "node"], capture_output=True).returncode != 0,
                    reason="node 不存在，跳过行为模拟")
def test_main_cjs_node_syntax():
    """main.cjs 编译闸：node --check 必须通过。"""
    r = subprocess.run(["node", "--check", str(_MAIN_CJS)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


# ── ③ index.html:1345 空元素守卫 ──────────────────────────────────

_INDEX_TEXT = _INDEX_HTML.read_text(encoding="utf-8")


def test_index_1345_guard_exists():
    """1345 事故行：.tool-agg-arrow 空值守卫存在。"""
    assert "if (arrowEl) arrowEl.textContent" in _INDEX_TEXT


def test_index_agg_body_guard_exists():
    """1345 同处：.tool-agg-body 空值守卫（body 为 null 时直接跳过）。"""
    assert "if (!body) return;" in _INDEX_TEXT


def test_index_no_bare_tool_agg_textcontent():
    """聚合卡区域不再有裸 textContent 赋值（自查同类）。"""
    # 聚合卡折叠箭头（1345 同款）已全部守卫
    assert "this.querySelector('.tool-agg-arrow').textContent" not in _INDEX_TEXT
    # 工具卡 toggle（1313 同款）已守卫
    assert "var t = div.querySelector('.tool-toggle'); t.textContent" not in _INDEX_TEXT


def test_index_safety_markers():
    """守卫均带票 SAFETY-1 标记，且 1345 行上下文确实存在。"""
    assert _INDEX_TEXT.count("票 SAFETY-1") >= 7, "7 处守卫标记（1345/1313/1071/1442/1455/1463/797）"


def test_index_js_syntax():
    """index.html 内联 JS 编译闸：提取 script 块 node --check。"""
    scripts = re.findall(r"<script[^>]*>(.*?)</script>", _INDEX_TEXT, re.S)
    assert scripts, "未找到内联 script 块"
    tmp = _REPO_ROOT / "data" / "trash" / "_bobo_safety1_index_check.js"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text("\n;\n".join(scripts), encoding="utf-8")
    try:
        r = subprocess.run(["node", "--check", str(tmp)],
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
    finally:
        tmp.unlink(missing_ok=True)
