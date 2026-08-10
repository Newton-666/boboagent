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

# ── TICKET-SCAN-L3b：莫兰迪双色（owner 逐字确认，零表情）──
# BOBO 行 = 莫兰迪蓝 #7C93A8 加粗；PI 行 = 莫兰迪粉 #B69A94 加粗；
# 分隔线/状态行 = 莫兰迪灰 #9AA0A6。正文不染色。
RELAY_BOBO_HEX = "7C93A8"
RELAY_PI_HEX = "B69A94"
RELAY_MUTED_HEX = "9AA0A6"

ANSI_RESET = "\x1b[0m"


def _ansi_fg_bold(hex_rgb: str, text: str) -> str:
    """ANSI 24-bit 前景色 + 加粗包裹文本（SGR 1;38;2;r;g;b）。"""
    r = int(hex_rgb[0:2], 16)
    g = int(hex_rgb[2:4], 16)
    b = int(hex_rgb[4:6], 16)
    return f"\x1b[1;38;2;{r};{g};{b}m{text}{ANSI_RESET}"


def _ansi_fg(hex_rgb: str, text: str) -> str:
    """ANSI 24-bit 前景色包裹文本（不加粗）。"""
    r = int(hex_rgb[0:2], 16)
    g = int(hex_rgb[2:4], 16)
    b = int(hex_rgb[4:6], 16)
    return f"\x1b[38;2;{r};{g};{b}m{text}{ANSI_RESET}"


def relay_header_line(sender: str, target: str, pane: str, ts: str, round_no: int, total: int) -> str:
    """互传块顶部分隔线 + 状态行（莫兰迪灰）。"""
    sep = _ansi_fg(RELAY_MUTED_HEX, "─" * 45)
    status = _ansi_fg(RELAY_MUTED_HEX,
                      f" 互传中 · {sender} ↔ {target}（{pane}）· 第 {round_no}/{total} 轮 ")
    return f"{sep}\n{status}\n{sep}"


def relay_msg_line(sender: str, target: str, ts: str, body: str) -> str:
    """单句互传：头部行（谁→谁+时间，双色加粗）+ 正文（不染色）。"""
    if sender == "BOBO":
        head = _ansi_fg_bold(RELAY_BOBO_HEX, f"{sender} → {target}  {ts}")
    else:
        head = _ansi_fg_bold(RELAY_PI_HEX, f"{sender} → {target}  {ts}")
    body_lines = [f"  {ln}" for ln in body.splitlines()] or ["  （空）"]
    return f"{head}\n" + "\n".join(body_lines)


def relay_footer_line() -> str:
    """互传块底部：断开提示 + 日志留底（莫兰迪灰）。"""
    sep = _ansi_fg(RELAY_MUTED_HEX, "─" * 45)
    hint = _ansi_fg(RELAY_MUTED_HEX, " ESC 断开 · /disconnect 手动断开 · 日志留底 ")
    return f"{sep}\n{hint}\n{sep}"


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

def strip_ansi(text: str) -> str:
    """去掉 ANSI 转义序列，返回纯文本（日志文件用）。"""
    import re as _re
    return _re.sub(r"\x1b\[[0-9;]*m", "", text)


# ── TICKET-SCAN-L3c：转发净化（Bug 2 思考剥离 + Bug 3 pi 输出净化）──
_THINKING_BLOCK_RE = None  # 惰性编译


def strip_thinking(text: str) -> str:
    """剥离 bobo 回复中的思考段（票 P 降级展示块），只留最终回复正文。

    格式：'──  思考过程 ──\n...\n── 思考结束 ──'（engine.py 票 P 追加）。
    只剥离块本身；块前后正文原样保留。
    """
    global _THINKING_BLOCK_RE
    if _THINKING_BLOCK_RE is None:
        import re as _re
        # 非贪婪匹配到首个 '── 思考结束 ──' 行；不跨多块（一次消费一块）。
        _THINKING_BLOCK_RE = _re.compile(
            r"\n*──\s*💭\s*思考过程\s*──.*?──\s*思考结束\s*──\s*", _re.S
        )
    if not text or "💭" not in text:
        return text
    cleaned = _THINKING_BLOCK_RE.sub("", text).strip()
    return cleaned


_PI_NOISE_LINE = None  # 惰性编译


def clean_pi_output(text: str) -> str:
    """净化 pi 侧 capture-pane 抓取的回复：去命令回显/工具噪音/提示符/spinner。

    宁保守：净化后为空返回 ""（调用方决定占位文案，如 '[pi 输出解析中]'）。
    只做噪音过滤，不改写正文内容（透明原则）。
    """
    global _PI_NOISE_LINE
    if not text:
        return ""
    if _PI_NOISE_LINE is None:
        import re as _re
        # 行级噪音：命令回显 / Took Xs / ctrl+o expand / 行数省略 / Loading / 提示符 / spinner
        _PI_NOISE_LINE = _re.compile(
            r"^\s*("
            r"\$.*"                                    # 命令回显（$ 开头整行）
            r"|Took\s+[\d.]+s\s*$"                     # 工具耗时
            r"|.*ctrl\+o.*expand.*"                    # 编辑提示
            r"|.*lines?\s+omitted.*"                   # 行数省略
            r"|^\(\d+ lines?\)$"                       # 折叠计数
            r"|Loading\s+.*"                           # 加载提示
            r"|[\w.-]+@[\w.-]+:[^\s]*[\$#~]?\s*$"      # shell 提示符（user@host:path）
            r"|[⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏⣾⣽⣻⢿⡿⣟⣯⣷].*"      # spinner 帧开头整行
            r")\s*$"
        )
    out = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if _PI_NOISE_LINE.match(line) or _PI_NOISE_LINE.match(s):
            continue
        out.append(line)
    return "\n".join(out).strip()


# ── TICKET-SCAN-L4-1：轮次自主（按话题复杂度评估，硬上限 5）──
MAX_ROUNDS = 5

# 简单问答：是否/确认/数字/短句
_SIMPLE_MARKERS = (
    "吗", "是不是", "能不能", "会不会", "可不可以", "等于", "多少",
    "是/否", "确认", "同意", "对吗", "对么", "yes", "no", "是", "否",
)
# 复杂设计/辩论/实现类
_COMPLEX_MARKERS = (
    "设计", "架构", "方案", "辩论", "对比", "分析", "评估", "实现",
    "如何", "为什么", "权衡", "选型", "优化", "重构", "迁移", "规划",
)
# 提前收敛信号（双方达成共识/无新观点）
_CONVERGE_MARKERS = (
    "达成共识", "达成一致", "无新观点", "讨论结束", "讨论完毕",
    "没有更多内容", "无需继续", "已解决", "不必再讨论",
)


def estimate_rounds(topic: str, user_specified=None) -> int:
    """轮次评估：用户明确指定轮数从用户（硬上限 MAX_ROUNDS）；否则按复杂度。

    - 简单问答（是否/确认/数字类）→ 2 轮
    - 观点讨论 → 3-4 轮
    - 复杂设计/辩论 → 5 轮（上限）
    """
    if user_specified is not None:
        try:
            n = int(user_specified)
        except (TypeError, ValueError):
            n = 5
        return max(1, min(MAX_ROUNDS, n))
    t = (topic or "").strip()
    if not t:
        return 1
    if len(t) <= 20 and any(m in t for m in _SIMPLE_MARKERS):
        return 2
    if any(m in t for m in _COMPLEX_MARKERS):
        return MAX_ROUNDS
    return 3


def should_converge(text: str) -> bool:
    """提前收敛判定：双方达成共识/无新观点时允许提前结束（省 token）。"""
    return any(m in text for m in _CONVERGE_MARKERS)


def run_relay_thread(sid: str, target: dict, rounds, emit, log_fn=None, engine_runner=None):
    """bobo(自己) ↔ target 互传。运行在 gateway 进程内的 daemon 线程。

    - target: agent_scan 扫描结果的候选 dict（已验证身份）
    - rounds: 互传轮数。API 直采模式下 None=轮次自主（L4-1 按话题复杂度评估，
      上限 MAX_ROUNDS=5；用户显式指定则从用户）；pane 模式 None 时默认 5。
    - emit: server_utils.emit 事件发射（进度推送 TUI）
    - log_fn: 可选日志回调（默认 print）
    - engine_runner: 可选回调 runner(text)->str，API 直采模式下 relay 线程
      显式调引擎（输入=pi 回复）拿 bobo 回复；由 gateway 闭包注入。

    TICKET-SCAN-L3b 双模式：
      pane 模式  —— 自己侧用 capture-pane 看屏幕（兼容 SCAN-L3 原路径）
      API 直采   —— 自己侧从 relay_hooks 内部数据通道取（用户话题 ← prompt.submit，
                     bobo 回复 ← engine_runner 显式调引擎）；bobo 不在 tmux 也能连。
    对方侧不变：仍走 capture-pane + send-keys + 发送前复核。

    TICKET-SCAN-L3c 路由三修：
      Bug1 用户输入只进 relay（prompt.submit 路由闸），开场直发 target，不进 bobo 大脑；
      Bug2 bobo 回复转发前 strip_thinking 剥思考段；
      Bug3 pi 回复 clean_pi_output 净化后再显示/转发。

    TICKET-SCAN-L4 交互裁决：
      L4-1 轮次自主：API 直采按话题复杂度评估轮数（硬上限 5），开屏明示
           '预计 N 轮（上限 5）'；用户显式指定从用户；共识/无新观点提前收敛。
      L4-3 持久多模式：API 直采连接常驻，每个新话题触发一轮"评估→互传→显示"，
           /disconnect 才退出；话题间上下文经 session.history 保留。
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

    from tools import relay_hooks

    target_pane = target["pane"]
    target_kind = target["kind"]
    target_label = target_kind.upper()

    # 日志文件（全文留底，无 ANSI）
    log_path = os.path.join(ROOT, "data", f"scan_relay_{time.strftime('%Y%m%d_%H%M%S')}.log")
    _log_file = open(log_path, "a", encoding="utf-8")

    def _log_line(text: str):
        try:
            _log_file.write(strip_ansi(text) + "\n")
            _log_file.flush()
        except Exception:
            pass

    # ── 模式判定：自己侧在 tmux 吗 ──
    bobo_pane = find_own_pane()
    api_mode = not bobo_pane
    if api_mode:
        relay_hooks.register(sid)
        _log(f"relay 线程启动（API 直采）：bobo 不在 tmux，target={target_pane}({target_kind}) 轮数={rounds}")
        _emit(f"▸ 已连接 {target_label}（{target_pane}），{rounds} 轮互传 · API 直采模式（bobo 无需 tmux）。输入话题即可开始。")
    else:
        _log(f"relay 线程启动（pane 模式）：bobo={bobo_pane} target={target_pane}({target_kind}) 轮数={rounds}")
        _emit(f"▸ 已连接 {target_label}（{target_pane}），{rounds} 轮互传。输入话题即可开始。")

    # 互传块头（ANSI 显示 + 纯文本日志）
    block_head = relay_header_line("BOBO", target_label, target_pane,
                                   time.strftime("%H:%M:%S"), 1, rounds)
    _emit(block_head)
    _log_line(strip_ansi(block_head))

    try:
        # ── 阶段 0：等用户话题（L3c：API 直采直发 target，不进 bobo 大脑）──
        if api_mode:
            # L4-3 持久多模式：连接常驻，每个话题一轮"评估→互传→显示"循环，
            # /disconnect 才退出；话题间 bobo 上下文经 session.history 自然保留。
            def _show_pi(new_pi_raw: str) -> str:
                """净化显示 pi 回复；净化后为空显示占位（宁保守不倒垃圾）。返回净化文本。"""
                pi_text = clean_pi_output(new_pi_raw)
                if pi_text:
                    _emit(relay_msg_line(target_label, "BOBO", time.strftime("%H:%M:%S"), pi_text))
                    _log_line(strip_ansi(relay_msg_line(target_label, "BOBO", time.strftime("%H:%M:%S"), pi_text)))
                elif new_pi_raw:
                    _emit(relay_msg_line(target_label, "BOBO", time.strftime("%H:%M:%S"), "[pi 输出解析中]"))
                    _log_line(strip_ansi(relay_msg_line(target_label, "BOBO", time.strftime("%H:%M:%S"), "[pi 输出解析中]")))
                return pi_text

            while True:
                user_topic = relay_hooks.poll_user_input(sid, 600)
                if user_topic is None:
                    _emit("⏹ 10 分钟内未检测到输入，已停止")
                    break
                _log("API 直采：收到用户话题，直发 target（不进 bobo 大脑）")
                # L4-1 轮次自主：用户显式指定轮数从用户；否则按话题复杂度评估
                est = estimate_rounds(user_topic, rounds)
                _emit(f"▸ 本话题预计 {est} 轮（上限 {MAX_ROUNDS}），开始互传")
                msg_u2t = relay_msg_line("USER", target_label, time.strftime("%H:%M:%S"), user_topic)
                _emit(msg_u2t)
                _log_line(strip_ansi(msg_u2t))
                try:
                    send_safe(target_pane, user_topic, target)
                except RuntimeError as e:
                    _emit(f"❌ {e}")
                    break
                p_after = wait_pi_finished(target_pane, 300)
                _log(f"开场：{target_label} 回复完成")
                p_base = cap(target_pane)
                p_before = p_base
                pi_clean = _show_pi(diff_new(p_base, p_after))
                converged = False
                for r in range(1, est + 1):
                    if engine_runner is None:
                        _log(f"轮{r}：engine_runner 未注入，无法 bobo 接话，停止")
                        break
                    bobo_input = pi_clean or "（pi 无新内容，请继续讨论）"
                    _log(f"轮 {r}/{est}：调引擎（输入={target_label} 回复）…")
                    bobo_reply = engine_runner(bobo_input)
                    new = strip_thinking(bobo_reply)
                    if not new:
                        _log(f"轮{r}：bobo 回复为空，跳过")
                        continue
                    _log(f"── 轮 {r}/{est}：bobo 回复 → {target_label} ──")
                    msg_b2t = relay_msg_line("BOBO", target_label, time.strftime("%H:%M:%S"), new)
                    _emit(msg_b2t)
                    _log_line(strip_ansi(msg_b2t))
                    try:
                        send_safe(target_pane, new, target)  # 发送前复核（补丁③）
                    except RuntimeError as e:
                        _emit(f"❌ {e}")
                        break
                    p_after = wait_pi_finished(target_pane, 300)
                    _log(f"轮 {r}：{target_label} 回复完成")
                    p_base = cap(target_pane)
                    pi_clean = _show_pi(diff_new(p_base, p_after))
                    # L4-1 提前收敛：达成共识/无新观点 → 提前结束（省 token，不算失败）
                    if should_converge(new):
                        _log(f"轮 {r}：检测到共识信号，提前收敛")
                        _emit(f"▸ 双方已达成共识/无新观点，提前结束（第 {r} 轮，未跑满 {est} 轮）")
                        converged = True
                        break
                _suffix = "（提前收敛）" if converged else f"（{est} 轮）"
                _emit(f"## 话题「{user_topic[:20]}{'…' if len(user_topic) > 20 else ''}」互传结束{_suffix}")
                _emit("▸ 连接保持中：可继续输入新话题，或 /disconnect 断开")
        else:
            # pane 模式：等屏幕新行（"> xxx"）（L4-1：None 时默认 5 轮，不评估）
            rounds = rounds or 5
            b_base = cap(bobo_pane)
            b_before = b_base
            t0 = time.time()
            while time.time() - t0 < 600:
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
            wait_bobo_busy(bobo_pane, 120)
            b_after = wait_bobo_ready(bobo_pane, 300)
            _log("bobo 首次回复完成")
            p_base = cap(target_pane)
            p_before = p_base

            for r in range(1, rounds + 1):
                # ── bobo → target ──
                new = diff_new(b_before, b_after)
                if not new:
                    _log(f"轮{r}：bobo 回复为空，跳过")
                    b_before = b_after
                    continue
                _log(f"── 轮 {r}/{rounds}：bobo 回复 → {target_label} ──")
                # 全透明显示：BOBO → PI 全文（ANSI 蓝加粗头部 + 正文不染）
                msg_b2t = relay_msg_line("BOBO", target_label, time.strftime("%H:%M:%S"), new)
                _emit(msg_b2t)
                _log_line(strip_ansi(msg_b2t))
                try:
                    send_safe(target_pane, new, target)  # 发送前复核（补丁③）
                except RuntimeError as e:
                    _emit(f"❌ {e}")
                    return
                p_after = wait_pi_finished(target_pane, 300)
                _log(f"轮 {r}：{target_label} 回复完成")

                # ── 显示 pi 回复（L3c Bug3：净化后显示，不倒噪音）──
                new_pi = diff_new(p_before, p_after)
                pi_clean = clean_pi_output(new_pi)
                if pi_clean:
                    msg_t2b = relay_msg_line(target_label, "BOBO", time.strftime("%H:%M:%S"), pi_clean)
                    _emit(msg_t2b)
                    _log_line(strip_ansi(msg_t2b))
                elif new_pi:
                    msg_t2b = relay_msg_line(target_label, "BOBO", time.strftime("%H:%M:%S"), "[pi 输出解析中]")
                    _emit(msg_t2b)
                    _log_line(strip_ansi(msg_t2b))

                if r == rounds:
                    break

                # ── target → bobo（L3c Bug3：净化后转发）──
                if not pi_clean:
                    _log(f"轮{r}：{target_label} 回复净化后为空，跳过")
                    p_before = p_after
                    continue
                _log(f"轮 {r}：{target_label} 回复 → bobo")
                try:
                    send_safe(bobo_pane, pi_clean, {"pane": bobo_pane, "kind": "bobo"})
                except RuntimeError as e:
                    _emit(f"❌ {e}")
                    return
                b_before = b_after
                b_after = wait_bobo_ready(bobo_pane, 300)
                _log(f"轮 {r}：bobo 回复完成")

        # ── 完成 ──
        out_path = os.path.join(ROOT, "data", f"scan_connect_{time.strftime('%Y%m%d_%H%M%S')}.txt")
        try:
            body = (f"===== BOBO PANE ({bobo_pane or 'API'}) =====\n"
                    f"===== {target_label} PANE ({target_pane}) =====\n{cap(target_pane)}\n")
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(body)
        except Exception:
            out_path = ""
        footer = relay_footer_line()
        _emit(footer)
        _log_line(strip_ansi(footer))
        _emit(f"## {DONE_LABEL}：{rounds} 轮互传完成" + (f"，日志留底：{log_path}" if os.path.exists(log_path) else ""))
    finally:
        _log_file.close()
        if api_mode:
            relay_hooks.unregister(sid)


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
