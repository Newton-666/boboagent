#!/usr/bin/env python3
"""tmux 双 TUI relay — Bobo↔pi 真实界面互传对话。

原理：
    两个真实 TUI（bobo / pi）分别跑在 tmux 左右 pane。
    relay 用 capture-pane 轮询屏幕，检测一方"回复完成"后，
    用 send-keys 把回复内容"敲"进另一方的输入框并回车。

用法（由 pi_chat.sh 启动，也可手动）：
    python3 tools/pi_relay.py [轮数] [--log 文件]
"""
import difflib
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BOBO_PANE = os.environ.get("RELAY_BOBO_PANE", "0.0")
PI_PANE = os.environ.get("RELAY_PI_PANE", "0.1")
STATUS_PANE = os.environ.get("RELAY_STATUS_PANE", "0.2")
DONE_LABEL = "对话结束"


def cap(pane: str) -> str:
    """capture-pane 取 pane 当前屏幕文本。"""
    r = subprocess.run(["tmux", "capture-pane", "-p", "-t", pane],
                       capture_output=True, text=True, timeout=15)
    return r.stdout or ""


def send(pane: str, text: str):
    """把文本敲进 pane 的输入框并回车。消息与 Enter 必须分开 send。"""
    text = text.strip()
    if not text:
        return
    # TUI 输入框是单行的：把换行压成空格，避免被拆成多条消息
    flat = " ".join(text.split())
    # 分片发送，避免超长输入卡 TUI（每片 ~400 字符）
    step = 400
    for i in range(0, len(flat), step):
        chunk = flat[i:i + step]
        subprocess.run(["tmux", "send-keys", "-t", pane, chunk],
                       capture_output=True, timeout=15)
        time.sleep(0.3)
    subprocess.run(["tmux", "send-keys", "-t", pane, "Enter"],
                   capture_output=True, timeout=15)


def bobo_state(screen: str) -> str:
    """bobo 状态：ready / busy / unknown"""
    for line in screen.splitlines():
        if "● ready" in line:
            return "ready"
        if any(k in line for k in ("musing", "cogitating", "contemplating",
                                   "thinking", "busy", "executing", "running", "working")):
            return "busy"
    return "unknown"


def pi_finished(screen: str) -> bool:
    """pi 完成特征：底部状态栏出现 token 统计。"""
    for line in screen.splitlines():
        if "↑" in line and "↓" in line and "deepseek" in line:
            return True
    return False


def screen_stable(pane: str, seconds: float = 6.0, interval: float = 2.0) -> str:
    """连续 seconds 秒屏幕不变，返回最终屏幕（稳定性判定通用兜底）。"""
    last = cap(pane)
    t0 = time.time()
    while time.time() - t0 < seconds:
        time.sleep(interval)
        cur = cap(pane)
        if cur != last:
            last = cur
            t0 = time.time()
    return last


def clean(text: str) -> str:
    """过滤 TUI 杂讯行（状态栏 / 分隔线 / 输入提示），只留对话内容。"""
    out = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if "● ready" in s or "contemplating" in s or "thinking" in s:
            continue
        if "│ deepseek" in s or "deepseek v4" in s:
            continue
        if "↑" in s and "↓" in s and "deepseek" in s:  # pi 状态栏
            continue
        if set(s) <= {"─", "═", "━", "┄"} and len(s) > 3:  # 分隔线
            continue
        if s in (">", "> Ctrl+C to interrupt…") or s.startswith("> Try"):
            continue
        out.append(s)
    return "\n".join(out)


def diff_new(before: str, after: str) -> str:
    """返回 after 相对 before 新增的行（已过滤 TUI 杂讯）。"""
    bl, al = before.splitlines(), after.splitlines()
    sm = difflib.SequenceMatcher(None, bl, al)
    new = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ("insert", "replace"):
            new.extend(al[j1:j2])
    return clean("\n".join(new))


def log(msg: str, status_pane: str = None):
    """写日志到 stdout（nohup 重定向到 LOG 文件，tail -f 实时显示）。"""
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def handle_bobo_prompt(pane: str, screen: str) -> bool:
    """bobo 可能弹出工具授权确认框（Allow this session / Always allow / Deny）。
    检测到则自动选 3（Always allow）+ 回车，返回是否处理过。
    处理后 sleep 5s：避免屏幕残留的弹窗文本触发连发，污染输入框。"""
    if "Allow this session" in screen and "Always allow" in screen:
        subprocess.run(["tmux", "send-keys", "-t", pane, "3"],
                       capture_output=True, timeout=10)
        time.sleep(0.4)
        subprocess.run(["tmux", "send-keys", "-t", pane, "Enter"],
                       capture_output=True, timeout=10)
        log("自动放行 bobo 工具授权弹窗（Always allow）", STATUS_PANE)
        time.sleep(5)
        return True
    return False


def wait_bobo_busy(bobo_pane: str, timeout: float = 120) -> bool:
    """等 bobo 开始思考（状态 != ready）。

    修复误判：话题刚敲进输入框时界面仍显示 ready，直接 wait_bobo_ready
    会立即误判"回复完成"（内容还没生成，抓到的 diff 为空）。
    先等状态离开 ready（musing/cogitating/pondering…），确认思考真正开始。
    0.5s 快速轮询，捕捉短回复的 busy 窗口；超时返回 False（话题可能未提交）。
    """
    t0 = time.time()
    while time.time() - t0 < timeout:
        screen = cap(bobo_pane)
        if handle_bobo_prompt(bobo_pane, screen):
            time.sleep(1)
            continue
        if bobo_state(screen) != "ready":
            return True
        time.sleep(0.5)
    return False


def wait_bobo_ready(bobo_pane: str, timeout: float) -> str:
    """等 bobo 回复完成：连续 2 次（间隔 2s）状态为 ready。"""
    t0 = time.time()
    hits = 0
    while time.time() - t0 < timeout:
        screen = cap(bobo_pane)
        if handle_bobo_prompt(bobo_pane, screen):
            hits = 0
            time.sleep(2)
            continue
        if bobo_state(screen) == "ready":
            hits += 1
            if hits >= 2:
                return screen
        else:
            hits = 0
        time.sleep(2)
    return cap(bobo_pane)


def wait_pi_finished(pi_pane: str, timeout: float) -> str:
    """等 pi 回复完成：连续 2 次（间隔 2s）出现 token 状态栏。"""
    t0 = time.time()
    hits = 0
    while time.time() - t0 < timeout:
        screen = cap(pi_pane)
        if pi_finished(screen):
            hits += 1
            if hits >= 2:
                return screen
        else:
            hits = 0
        time.sleep(2)
    return cap(pi_pane)


def snapshot(out_path: str, bobo_pane: str, pi_pane: str) -> str:
    """截屏双 pane，写入文件，返回文件路径。"""
    b = cap(bobo_pane)
    p = cap(pi_pane)
    body = f"===== BOBO PANE ({bobo_pane}) =====\n{b}\n\n===== PI PANE ({pi_pane}) =====\n{p}\n"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(body)
    return out_path


def main() -> int:
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 5

    # 单实例锁：多个 relay 同时盯同一 pane 会互相误判、抢传消息（曾出现
    # 11:23 与 11:24 两个 relay 并存导致话题被重复处理）。发现其他 relay 即退出。
    me = os.getpid()
    try:
        procs = subprocess.run(["pgrep", "-f", "pi_relay.py"],
                               capture_output=True, text=True, timeout=10).stdout.split()
    except Exception:
        procs = []
    for pid_str in procs:
        if pid_str.isdigit() and int(pid_str) != me:
            print(f"已有 relay 在运行（pid {pid_str}），本次退出", file=sys.stderr)
            return 0
    log_path = None
    if "--log" in sys.argv:
        log_path = sys.argv[sys.argv.index("--log") + 1]

    out_path = os.path.join(ROOT, "data", f"pi_discuss_{time.strftime('%Y%m%d_%H%M%S')}.txt")
    log(f"relay 启动：bobo={BOBO_PANE} pi={PI_PANE} 轮数={rounds}", STATUS_PANE)
    log("请在 bobo pane 输入话题…", STATUS_PANE)

    # 基线
    b_base = cap(BOBO_PANE)
    p_base = cap(PI_PANE)

    # 阶段 0：等用户在 bobo 输入——检测屏幕上新增的用户消息行（"> xxx"）
    # 比检测 busy 状态可靠：bobo 思考词随机变化（musing/cogitating…），
    # 且简单问题 3 秒就回复完，轮询可能错过 busy 窗口。
    b_before = b_base  # 输入前的屏幕（欢迎页/历史）
    t0 = time.time()
    while time.time() - t0 < 600:  # 10 分钟等用户
        screen = cap(BOBO_PANE)
        if handle_bobo_prompt(BOBO_PANE, screen):
            time.sleep(2)
            continue
        if screen != b_base:
            new_lines = diff_new(b_base, screen)
            # 用户消息行特征：以 ">" 开头且有实际内容（bobo 输入框回显）
            if any(l.strip().startswith(">") and len(l.strip()) > 3 for l in new_lines.splitlines()):
                log("检测到用户在 bobo 输入话题", STATUS_PANE)
                b_before = screen  # 含用户消息的屏幕 = 本轮提取起点
                break
        time.sleep(2)
    else:
        log("超时：10 分钟内未检测到用户输入", STATUS_PANE)
        return 1

    # 首次 bobo 回复完成——先等思考开始（修复：话题刚输入时界面仍 ready，
    # 直接 wait_bobo_ready 会立即误判完成，抓到空 diff）
    wait_bobo_busy(BOBO_PANE, 120)
    b_after = wait_bobo_ready(BOBO_PANE, 300)
    log("bobo 首次回复完成", STATUS_PANE)
    p_before = p_base  # pi 提取起点（收到首条消息前的屏幕）

    for r in range(1, rounds + 1):
        # ── bobo → pi ──
        new = diff_new(b_before, b_after)
        if not new:
            log(f"轮{r}：bobo 回复为空，跳过", STATUS_PANE)
            b_before = b_after
            continue
        log(f"── 轮 {r}/{rounds}：bobo 回复 → pi ──", STATUS_PANE)
        send(PI_PANE, new)
        p_after = wait_pi_finished(PI_PANE, 300)
        log(f"轮 {r}：pi 回复完成", STATUS_PANE)

        if r == rounds:
            break

        # ── pi → bobo ──
        new = diff_new(p_before, p_after)
        if not new:
            log(f"轮{r}：pi 回复为空，跳过", STATUS_PANE)
            p_before = p_after
            continue
        log(f"轮 {r}：pi 回复 → bobo", STATUS_PANE)
        send(BOBO_PANE, new)
        b_before = b_after          # 上一轮 bobo 完成屏 = 本轮提取起点
        b_after = wait_bobo_ready(BOBO_PANE, 300)
        log(f"轮 {r}：bobo 回复完成", STATUS_PANE)

    # 截屏存档 + 通知
    path = snapshot(out_path, BOBO_PANE, PI_PANE)
    log(f"{DONE_LABEL}，共 {rounds} 轮，截屏：{path}", STATUS_PANE)
    try:
        subprocess.run(["osascript", "-e",
                        f'display notification "5轮讨论完成，见 {path}" with title "Bobo↔pi 讨论"'],
                       capture_output=True, timeout=10)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
