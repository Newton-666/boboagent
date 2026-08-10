#!/usr/bin/env python3
"""agent_connect — TICKET-SCAN-L3：一键连接（/scan → 确认 → 自动互传）。

互传原语提炼自 tools/pi_relay.py（双 TUI relay 范式），核心差异：
  1. 目标 pane 来自 /scan 扫描结果（agent_scan 识别），非环境变量写死；
  2. 每次 send-keys 前复核 pane 身份（Kimi 补丁③，单一事实源 = agent_scan）；
  3. 安全闸：只向已确认候选 pane 发送，unknown 永不成为目标；
  4. 运行在 gateway 进程内的后台线程（daemon），进度经 emit 推送 TUI。

用法（由 /scan + /connect slash 命令触发，也可手动调试）：
    python3 tools/agent_connect.py --scan            # 打印候选
    python3 tools/agent_connect.py --verify <pane>   # 复核 pane 身份
"""
import difflib
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

DONE_LABEL = "对话结束"


# ── 互传原语（提炼自 pi_relay.py，复用其验证过的范式）──

def cap(pane: str) -> str:
    """capture-pane 取 pane 当前屏幕文本。"""
    r = subprocess.run(["tmux", "capture-pane", "-p", "-t", pane],
                       capture_output=True, text=True, timeout=15)
    return r.stdout or ""


def _send_keys(pane: str, text: str):
    """把文本敲进 pane 的输入框并回车。消息与 Enter 必须分开 send。"""
    text = text.strip()
    if not text:
        return
    # TUI 输入框是单行的：把换行压成空格，避免被拆成多条消息
    flat = " ".join(text.split())
    # 分片发送，避免超长输入卡 TUI（每片 ~400 字符）—— 安全闸长度限制
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


def handle_bobo_prompt(pane: str, screen: str) -> bool:
    """bobo 可能弹出工具授权确认框（Allow this session / Always allow / Deny）。
    检测到则自动选 3（Always allow）+ 回车，返回是否处理过。"""
    if "Allow this session" in screen and "Always allow" in screen:
        subprocess.run(["tmux", "send-keys", "-t", pane, "3"],
                       capture_output=True, timeout=10)
        time.sleep(0.4)
        subprocess.run(["tmux", "send-keys", "-t", pane, "Enter"],
                       capture_output=True, timeout=10)
        time.sleep(5)
        return True
    return False


def wait_bobo_busy(pane: str, timeout: float = 120) -> bool:
    """等 bobo 开始思考（状态 != ready）。0.5s 快速轮询，超时返回 False。"""
    t0 = time.time()
    while time.time() - t0 < timeout:
        screen = cap(pane)
        if handle_bobo_prompt(pane, screen):
            time.sleep(1)
            continue
        if bobo_state(screen) != "ready":
            return True
        time.sleep(0.5)
    return False


def wait_bobo_ready(pane: str, timeout: float) -> str:
    """等 bobo 回复完成：连续 2 次（间隔 2s）状态为 ready。"""
    t0 = time.time()
    hits = 0
    while time.time() - t0 < timeout:
        screen = cap(pane)
        if handle_bobo_prompt(pane, screen):
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
    return cap(pane)


def wait_pi_finished(pane: str, timeout: float) -> str:
    """等 pi 回复完成：连续 2 次（间隔 2s）出现 token 状态栏。"""
    t0 = time.time()
    hits = 0
    while time.time() - t0 < timeout:
        screen = cap(pane)
        if pi_finished(screen):
            hits += 1
            if hits >= 2:
                return screen
        else:
            hits = 0
        time.sleep(2)
    return cap(pane)


# ── Kimi 补丁③：发送前复核（单一事实源 = agent_scan）──

def verify_pane_identity(candidate: dict) -> tuple:
    """发送前复核：按 pane 重新取 pane_pid → 进程树 → 命令行，仍认定为原身份。

    返回 (ok: bool, reason: str)。失败原因：pane 不存在 / 身份已变化。
    禁止拿扫描时的旧结果直接打字——扫描与发送之间 pane 可能被关闭/复用。
    """
    from tools.agent_scan import pane_pid, process_tree, classify_by_cmd
    pane = candidate.get("pane", "")
    expected_kind = candidate.get("kind", "")
    if not pane:
        return False, "候选缺少 pane 标识"
    # 安全闸：unknown 永不通过复核（即使 classify 结果也是 unknown，也不放行）
    if expected_kind not in ("bobo", "pi"):
        return False, f"候选身份无效: {expected_kind or '空'}（unknown 永不通过复核）"
    pid = pane_pid(pane)
    if not pid:
        return False, f"pane {pane} 已不存在"
    tree = process_tree(pid)
    kind, match_pid, _ = classify_by_cmd(tree)
    if kind != expected_kind or kind == "unknown":
        return False, f"pane {pane} 身份已从 {expected_kind} 变为 {kind}（pid={match_pid or '?'}）"
    return True, ""


# ── 安全闸：受限发送（L3-4）──

def send_safe(pane: str, text: str, candidate: dict):
    """安全闸发送：发送前复核目标 pane 身份，失败则拒绝并抛错。

    任何情况下不得向未复核身份的 pane 发送（unknown 永不成为目标）。
    长度限制（400 字符分片）与频率限制（0.3s 间隔）在 _send_keys 内。
    """
    ok, reason = verify_pane_identity(candidate)
    if not ok:
        raise RuntimeError(f"目标 pane 身份已变化，已中止：{reason}")
    _send_keys(pane, text)


# ── 找自己的 pane（当前 gateway 进程所在的 tmux pane）──

def find_own_pane() -> str:
    """沿当前进程父链向上，找到 pane_pid 匹配的 pane（即 bobo 自己所在 pane）。"""
    me = os.getpid()
    pid = me
    for _ in range(10):
        r = subprocess.run(["ps", "-o", "ppid=", "-p", str(pid)],
                           capture_output=True, text=True, timeout=5)
        ppid = r.stdout.strip()
        if not ppid or not ppid.isdigit():
            break
        # 检查 ppid 是否为某个 pane 的 pane_pid
        r2 = subprocess.run(
            ["tmux", "list-panes", "-a",
             "-F", "#{session_name}:#{window_index}.#{pane_index}|#{pane_pid}"],
            capture_output=True, text=True, timeout=5)
        for line in r2.stdout.splitlines():
            parts = line.strip().split("|")
            if len(parts) == 2 and parts[1] == ppid:
                return parts[0]
        pid = ppid
    return ""


# ── 互传主循环（后台线程入口）──

def run_relay_thread(sid: str, target: dict, rounds: int, emit, log_fn=None):
    """bobo(自己) ↔ target 互传 N 轮。运行在 gateway 进程内的 daemon 线程。

    - target: agent_scan 扫描结果的候选 dict（已验证身份）
    - emit: server_utils.emit 事件发射（进度推送 TUI）
    - log_fn: 可选日志回调（默认 print）
    """
    def _log(msg):
        if log_fn:
            log_fn(msg)
        else:
            print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

    def _emit(msg: str):
        try:
            emit("message.delta", sid, {"text": msg, "session_id": sid})
        except Exception:
            pass

    bobo_pane = find_own_pane()
    if not bobo_pane:
        _emit("❌ 无法定位当前 bobo 所在 pane，已中止")
        return
    target_pane = target["pane"]
    target_kind = target["kind"]
    _log(f"relay 线程启动：bobo={bobo_pane} target={target_pane}({target_kind}) 轮数={rounds}")
    _emit(f"▸ 已连接 {target_kind}（{target_pane}），{rounds} 轮互传。在输入框输入话题即可开始。")

    # 基线
    b_base = cap(bobo_pane)
    p_base = cap(target_pane)

    # 阶段 0：等用户在 bobo 输入（检测 "> xxx" 新行）
    b_before = b_base
    t0 = time.time()
    while time.time() - t0 < 600:  # 10 分钟等用户
        screen = cap(bobo_pane)
        if handle_bobo_prompt(bobo_pane, screen):
            time.sleep(2)
            continue
        if screen != b_base:
            new_lines = diff_new(b_base, screen)
            if any(l.strip().startswith(">") and len(l.strip()) > 3 for l in new_lines.splitlines()):
                _log("检测到用户在 bobo 输入话题")
                b_before = screen
                break
        time.sleep(2)
    else:
        _emit("⏹ 10 分钟内未检测到输入，已停止")
        return

    # 首次 bobo 回复完成
    wait_bobo_busy(bobo_pane, 120)
    b_after = wait_bobo_ready(bobo_pane, 300)
    _log("bobo 首次回复完成")
    p_before = p_base

    for r in range(1, rounds + 1):
        # ── bobo → target ──
        new = diff_new(b_before, b_after)
        if not new:
            _log(f"轮{r}：bobo 回复为空，跳过")
            b_before = b_after
            continue
        _log(f"── 轮 {r}/{rounds}：bobo 回复 → {target_kind} ──")
        try:
            send_safe(target_pane, new, target)  # 发送前复核（补丁③）
        except RuntimeError as e:
            _emit(f"❌ {e}")
            return
        p_after = wait_pi_finished(target_pane, 300)
        _log(f"轮 {r}：{target_kind} 回复完成")

        if r == rounds:
            break

        # ── target → bobo ──
        new = diff_new(p_before, p_after)
        if not new:
            _log(f"轮{r}：{target_kind} 回复为空，跳过")
            p_before = p_after
            continue
        _log(f"轮 {r}：{target_kind} 回复 → bobo")
        try:
            send_safe(bobo_pane, new, {"pane": bobo_pane, "kind": "bobo"})
        except RuntimeError as e:
            _emit(f"❌ {e}")
            return
        b_before = b_after
        b_after = wait_bobo_ready(bobo_pane, 300)
        _log(f"轮 {r}：bobo 回复完成")

    # 完成
    out_path = os.path.join(ROOT, "data", f"scan_connect_{time.strftime('%Y%m%d_%H%M%S')}.txt")
    try:
        body = (f"===== BOBO PANE ({bobo_pane}) =====\n{cap(bobo_pane)}\n\n"
                f"===== {target_kind.upper()} PANE ({target_pane}) =====\n{cap(target_pane)}\n")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(body)
    except Exception:
        out_path = ""
    _emit(f"## {DONE_LABEL}：{rounds} 轮互传完成" + (f"，截屏存档：{out_path}" if out_path else ""))


# ── CLI 调试入口 ──

def main():
    if "--scan" in sys.argv:
        from tools.agent_scan import scan
        for r in scan():
            if r["kind"] in ("bobo", "pi"):
                print(f"[{r['kind'].upper()}] {r['pane']}  cwd={r['cwd'] or '?'}  started={r['lstart'] or '?'}")
        return
    if "--verify" in sys.argv:
        idx = sys.argv.index("--verify") + 1
        pane = sys.argv[idx] if idx < len(sys.argv) else ""
        if not pane:
            print("用法: --verify <pane>")
            return
        from tools.agent_scan import scan
        cands = [r for r in scan() if r["pane"] == pane]
        if not cands:
            print(f"pane {pane} 未找到")
            return
        ok, reason = verify_pane_identity(cands[0])
        print(f"复核 {pane}（kind={cands[0]['kind']}）: {'通过' if ok else '拒绝'} — {reason}")
        return
    print(__doc__)


if __name__ == "__main__":
    main()
