#!/usr/bin/env python3
"""tmux 四方 TUI relay v2 — 结构化通道版（文件即总线）。

v1 问题（四 Agent 团队讨论 2026-08-10 确认）：
    屏幕 diff 抓发言在 4 个 TUI 混跑时不可用——思考流、状态栏、token
    计数、manual mode 提示全在互相污染，把中间态当完整回复转发。

v2 方案（结构化通道，内容与界面彻底解耦）：
    - inbox/{agent}/{seq:04d}.md   每个 agent 的完整发言，消息边界=文件边界
    - relay.state                  各 agent 已转发到的序号（JSON）
    - 写入侧（过渡版）：relay 检测到 agent 从 busy→idle 转变后，从屏幕
      摘一次完整回复写入 inbox（等空闲再摘，杜绝中间态）
    - 读取侧：轮询 inbox，发现新序号文件（> relay.state 记录）即转发，
      转发前检查下一位空闲；屏幕 capture 只做空闲判定，不提取内容

落地路径（笔记 pi完成判定与relay链路.md）：
    先做 relay 侧摘录过渡版跑通，再演进到各 agent 原生写通道。

与 agent_connect.py 的分工与边界（票 R1-1）：
    - agent_connect：双 agent（bobo↔pi）互传总线，pane 身份复核走
      pid/进程树取证（verify_pane_identity，仅认 bobo/pi 两种身份），
      用于 /scan 连接与双 TUI 互发。
    - 本文件（team_relay_v2）：多员工轮巡总线（bobo→hermes→claude→
      pi→bobo），结构化通道（文件即总线），pane 身份复核走提示符特征
      （verify_target_pane，见下），用于四 Agent 团队讨论。
    - 什么时候用哪个：双 agent 直连 → agent_connect；三方及以上轮巡 →
      team_relay_v2。两者互不调用、互不改动（深度融合留给 O-2 搭建器）。

用法：
    python3 tools/team_relay_v2.py [轮数] [间隔秒]
"""
import difflib
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from pi_relay import cap, send, clean, diff_new, bobo_state, pi_finished  # noqa: E402

SES = os.environ.get("RELAY_SESSION", "staff_office")


def build_panes(session: str) -> dict:
    """票 R1-1 评审点 6：会话名参数化——O-2 搭建器传不同 session 名建 pane 映射。

    禁止硬编码会话名：多员工讨论/多会话并存时各 relay 用各自的
    RELAY_SESSION（env）或显式传参，互不串台。
    """
    return {
        "bobo": f"{session}:0.0",
        "hermes": f"{session}:0.1",
        "claude": f"{session}:0.2",
        "pi": f"{session}:0.3",
    }


PANES = build_panes(SES)
ORDER = ["bobo", "hermes", "claude", "pi"]
DONE_LABEL = "团队讨论结束"

INBOX_ROOT = os.path.join(ROOT, "data", "relay_v2", "inbox")
STATE_PATH = os.path.join(ROOT, "data", "relay_v2", "relay.state")

# relay 自身注入的前缀，diff 时需过滤，防止回声
INJECT_PREFIX = "【来自"

# 只读硬约束：每次注入消息都强制附带，杜绝 agent 在讨论中执行写操作/修复
READONLY_RULE = (
    "【硬约束·必须遵守】本讨论为纯讨论：你只允许思考与发言，绝对禁止执行任何"
    "写操作——包括但不限于：修改/新建/删除文件、运行 git commit / write / "
    "edit / 落盘类命令、写入 library 或 data 目录、修复任何代码。所有产出"
    "只通过发言表达。禁止自行操作 tmux 给其他 agent 发消息（relay 统一调度）。"
    "违反约束将被视为讨论失败并立即终止。"
)


# ── 结构化通道：inbox 读写 ──
def _agent_inbox(agent: str) -> str:
    return os.path.join(INBOX_ROOT, agent)


def load_state() -> dict:
    """读 relay.state：各 agent 已转发到的序号。不存在则全 0。"""
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {a: 0 for a in ORDER}


def save_state(state: dict):
    """原子写 relay.state：tmp + rename，防半截文件。"""
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE_PATH)


def write_inbox(agent: str, content: str) -> int:
    """把完整发言原子写入 inbox/{agent}/{seq:04d}.md，返回序号。

    原子性：先写 .tmp 再 os.replace，防止读到半截文件。
    序号 = 当前最大序号 + 1（不依赖 relay.state，双端容错）。
    """
    d = _agent_inbox(agent)
    os.makedirs(d, exist_ok=True)
    seq = 1
    for fn in os.listdir(d):
        if fn.endswith(".md") and not fn.endswith(".tmp"):
            try:
                n = int(fn[:4])
                if n >= seq:
                    seq = n + 1
            except ValueError:
                continue
    tmp = os.path.join(d, f"{seq:04d}.md.tmp")
    final = os.path.join(d, f"{seq:04d}.md")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(content)
    os.replace(tmp, final)
    return seq


def read_new_inbox(agent: str, last_seq: int) -> list:
    """读 inbox/{agent}/ 中序号 > last_seq 的所有发言，按序返回 [(seq, text)]。"""
    d = _agent_inbox(agent)
    if not os.path.isdir(d):
        return []
    files = sorted(
        fn for fn in os.listdir(d)
        if fn.endswith(".md") and not fn.endswith(".tmp")
    )
    out = []
    for fn in files:
        try:
            seq = int(fn[:4])
        except ValueError:
            continue
        if seq > last_seq:
            with open(os.path.join(d, fn), encoding="utf-8") as f:
                out.append((seq, f.read()))
    return out


# ── 各自空闲判定（屏幕 capture 只做这个，不提取内容）──
def _bottom_lines(screen: str, n: int = 10) -> list:
    return [l for l in screen.splitlines() if l.strip()][-n:]


def claude_idle(screen: str) -> bool:
    """claude 空闲：底部 10 行内有独立 ❯ 提示行，且无进行中标志。

    注意：'⏺ ' 是后台 agent 的历史标记（agent 结束后仍残留），不代表
    正在运行，不能作为忙碌标志。真正进行中：Working/Waiting/确认框。
    """
    bottom = _bottom_lines(screen)
    has_prompt = any(l.strip().startswith("❯") for l in bottom)
    if not has_prompt:
        return False
    busy = ("Working", "Waiting for", "Do you want to proceed",
            "requires approval", "⌛")
    return not any(b in screen for b in busy)


def hermes_idle(screen: str) -> bool:
    """hermes 空闲：底部出现提示符（⚕ ❯ 或独立 ❯ 行）。

    注意：hermes 空闲时提示行可能是 "⚕ ❯ msg=interrupt…" 或单独的 "❯"，
    两种形态都接受。忙碌标志（Initializing/Working/⏳）出现即非空闲。
    ⚡ 为工具调用历史标记（同 claude 的 ⏺，任务结束后仍残留，0.0s 耗时
    即已完成记录），不代表正在运行，不能作为忙碌标志——2026-08-10 团队
    启动时实测：hermes 空闲（❯ 提示符 + 状态行 ⏲）却被残留 ⚡ 判忙，
    relay 转发死锁。忙碌判定只认状态行活跃标志。
    """
    bottom = _bottom_lines(screen)
    has_prompt = any("⚕ ❯" in l or l.strip() == "❯" or l.strip().startswith("❯ ")
                     for l in bottom)
    if not has_prompt:
        return False
    busy = ("Initializing agent", "Working", "⏳")
    return not any(b in screen for b in busy)


def bobo_idle(screen: str) -> bool:
    """bobo 空闲：底部有 > 提示符，且状态行无思考词。

    bobo 状态行：`─ ● 状态 │ ...`。思考词有
    cogitating/analyzing/deliberating/reflecting/pondering/mulling/
    thinking/working 等（引擎退出/等待输入时状态行不显示思考词）。
    """
    bottom = _bottom_lines(screen)
    has_prompt = any(l.strip() == ">" or l.strip().startswith("> ") for l in bottom)
    if not has_prompt:
        return False
    thinking = ("cogitating", "analyzing", "deliberating", "reflecting",
                "pondering", "mulling", "thinking", "working", "computing",
                "reasoning", "planning", "searching", "reading")
    return not any(t in screen.lower() for t in thinking)


def pane_idle_fn(name: str):
    return {"bobo": bobo_idle, "hermes": hermes_idle,
            "claude": claude_idle, "pi": pi_finished}[name]


def _pane_signature(name: str, screen: str) -> bool:
    """票 R1-1 评审点 5：pane 身份特征检测（L3 铁律沿用）。

    特征 = 该 agent 提示符形态（bobo '>' / hermes '⚕ ❯|❯' /
    claude '❯' / pi token 统计）。特征缺失 → 该 pane 不是预期 agent
    （unknown），永不通过身份复核、永不作为转发目标。
    与 agent_connect.verify_pane_identity 的差异：那边按 pid/进程树
    取证（只认 bobo/pi）；这边按提示符特征（四 agent 轮巡通用）。
    """
    bottom = _bottom_lines(screen)
    if name == "bobo":
        return any(l.strip() == ">" or l.strip().startswith("> ") for l in bottom)
    if name == "hermes":
        return any("⚕ ❯" in l or l.strip() == "❯" or l.strip().startswith("❯ ") for l in bottom)
    if name == "claude":
        return any(l.strip().startswith("❯") for l in bottom)
    if name == "pi":
        return any("↑" in l and "↓" in l and "deepseek" in l for l in screen.splitlines())
    return False


def verify_target_pane(name: str) -> tuple:
    """票 R1-1 评审点 5：发送前复核目标 pane 身份（L3 铁律沿用）。

    返回 (ok, reason, screen)。ok=False 时拒绝转发，绝不 send——
    unknown pane 永不通过身份复核（pane 可能被关闭/复用，转发前必须复核）。
    """
    if name not in PANES:
        return False, f"未知 agent: {name}", ""
    try:
        screen = cap(PANES[name])
    except Exception as e:
        return False, f"pane {PANES[name]} 不可读: {e}", ""
    if not _pane_signature(name, screen):
        return False, f"pane {PANES[name]} 无 {name} 身份特征（unknown，永不通过复核）", screen
    return True, "", screen


def clean_reply(text: str) -> str:
    """清理转发内容：过滤 relay 注入段（【来自 X 的发言】/【硬约束】）、TUI 杂讯、思考流。

    按行过滤而非按 \\n\\n 分段：clean() 会去掉空行，段落分隔已不存在，
    按行 startswith 匹配更可靠。
    票 R1-1 评审点 3：思考流（💭 块）是 agent 内部思考，绝不进结构化通道——
    只发正式发言，思考流只属于写通道前的屏幕，不属于通道内容。
    """
    cleaned = clean(text)
    out = []
    for line in cleaned.splitlines():
        s = line.strip()
        if s.startswith(INJECT_PREFIX) and "的发言】" in s:
            continue
        if s.startswith("【硬约束"):
            continue
        if s.startswith("💭"):
            continue  # 票 R1：思考流不进通道
        out.append(line)
    return "\n".join(out)


def extract_reply(before: str, after: str) -> str:
    """摘录完整回复：after 相对 before 的新增内容（已过滤杂讯）。"""
    return clean(diff_new(before, after))


def _capture_reply(name: str, base: str, cur: str) -> str:
    """过渡版摘录：busy→idle 转变后从屏幕 diff 提取完整回复（评审点 4）。

    屏幕 capture 的长期职责只做空闲判定 + 调度触发，不做内容提取——
    内容提取终态由各 agent 原生写通道负责（O-2 搭建器落地后本函数删除，
    届时 inbox 只收原生写通道的消息，本摘录路径整体移除）。
    过渡期保留 diff 提取，但与 idle 判定在函数层面已严格分离。
    """
    return clean_reply(extract_reply(base, cur))


def write_summary(state: dict, spoken: dict) -> str:
    """讨论收尾：从 inbox 汇总各 agent 发言成 Obsidian 文件。

    汇总数据源 = 结构化通道（比屏幕摘录可靠），每条发言带序号。
    """
    ts = time.strftime("%Y%m%d-%H%M%S")
    vault_dir = os.path.join(ROOT, "library", "agent开发")
    os.makedirs(vault_dir, exist_ok=True)
    fname = os.path.join(vault_dir, f"四Agent团队讨论汇总-{ts}.md")
    lines = [
        f"# 四 Agent 团队讨论汇总（{ts}）",
        "",
        "> 参与者：bobo / hermes / claude / pi",
        "> 调度：team_relay v2 结构化通道（bobo→hermes→claude→pi→bobo）",
        "> 生成方式：达到轮数上限后由 relay 自动收尾汇总，非人工整理",
        "> 数据源：data/relay_v2/inbox 结构化通道（消息边界=文件边界）",
        "> 规则：全程只读，未修改任何文件",
        "",
        f"## 发言轮次统计",
        "",
        "| Agent | 发言次数 |",
        "|-------|---------|",
    ]
    for name in ORDER:
        lines.append(f"| {name} | {spoken.get(name, 0)} |")
    lines.append("")
    for name in ORDER:
        lines.append(f"## {name} 的发言")
        lines.append("")
        msgs = read_new_inbox(name, 0)
        if not msgs:
            lines.append("（无发言）")
        else:
            for seq, m in msgs:
                lines.append(f"### 第 {seq} 次发言")
                lines.append("")
                lines.append("```")
                lines.append(m.strip()[:2000])
                lines.append("```")
                lines.append("")
    content = "\n".join(lines)
    with open(fname, "w", encoding="utf-8") as f:
        f.write(content)
    return fname


def main() -> int:
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    interval = float(sys.argv[2]) if len(sys.argv) > 2 else 2.0

    # 单实例锁（与 v1 相同，防双 relay 竞争）
    me = os.getpid()
    try:
        procs = subprocess.run(["pgrep", "-f", "team_relay_v2.py"],
                               capture_output=True, text=True, timeout=10).stdout.split()
    except Exception:
        procs = []
    for pid_str in procs:
        if pid_str.isdigit() and int(pid_str) != me:
            print(f"已有 team_relay_v2 在运行（pid {pid_str}），本次退出", file=sys.stderr)
            return 0

    log_path = os.path.join(ROOT, "data", "team_relay_v2.log")
    logf = open(log_path, "a", encoding="utf-8")

    def log(msg):
        ts = time.strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        print(line, flush=True)
        logf.write(line + "\n")
        logf.flush()

    log(f"team_relay v2 启动：{' → '.join(ORDER)} 轮数={rounds} 间隔={interval}s")

    # 初始化：inbox 目录 + 基线 + 各 agent 初始空闲状态
    state = load_state()
    base = {name: cap(pane) for name, pane in PANES.items()}
    idle_prev = {name: pane_idle_fn(name)(base[name]) for name in ORDER}
    spoken = {name: 0 for name in ORDER}      # 已摘录条数
    forwarded_count = 0
    t_start = time.time()
    hard_timeout = 3600  # 1 小时硬上限

    log("建立基线（3s）…")
    time.sleep(3)
    base = {name: cap(pane) for name, pane in PANES.items()}
    idle_prev = {name: pane_idle_fn(name)(base[name]) for name in ORDER}

    def finish(reason: str) -> int:
        log(f"{reason}，共转发 {forwarded_count} 次")
        try:
            fname = write_summary(state, spoken)
            log(f"已生成 Obsidian 汇总：{fname}")
        except Exception as e:
            log(f"生成 Obsidian 汇总失败：{e}")
        logf.close()
        return 0

    log("开始轮询…")
    while time.time() - t_start < hard_timeout:
        # ── 阶段 1：摘录（busy→idle 转变 = 一轮思考结束，摘完整回复）──
        for name in ORDER:
            pane = PANES[name]
            cur = cap(pane)
            idle_now = pane_idle_fn(name)(cur)
            if (not idle_prev[name]) and idle_now:
                # 刚结束一轮思考：摘录完整回复写入通道（过渡版，见 _capture_reply）
                new = _capture_reply(name, base[name], cur)
                if len(new.strip()) >= 10:
                    seq = write_inbox(name, new)
                    spoken[name] += 1
                    log(f"{name} 发言（{len(new)}字符）写入 inbox {seq:04d} [第{spoken[name]}次]")
                # 太短（界面波动）不写，但基线照常更新
                base[name] = cur
            idle_prev[name] = idle_now

        # ── 阶段 2：转发（轮询 inbox 新文件 → 下一位空闲时转发）──
        for name in ORDER:
            if spoken[name] <= state.get(name, 0):
                continue  # 无新发言
            if spoken[name] > rounds:
                continue  # 已达轮次上限，不再转发
            next_name = ORDER[(ORDER.index(name) + 1) % len(ORDER)]
            # 票 R1：发送前复核目标 pane 身份（unknown 永不通过复核，L3 铁律沿用）
            ok, reason, next_screen = verify_target_pane(next_name)
            if not ok:
                log(f"  {next_name} 复核失败：{reason}（unknown，拒绝转发 {name} 的发言）")
                continue
            if not pane_idle_fn(next_name)(next_screen):
                log(f"  {next_name} 忙碌，暂缓转发 {name} 的发言（下次重试）")
                continue  # 不更新 state，下轮重试
            msgs = read_new_inbox(name, state.get(name, 0))
            for seq, content in msgs:
                msg = f"{INJECT_PREFIX} {name} 的发言】\n{content}\n\n{READONLY_RULE}"
                send(PANES[next_name], msg)
                state[name] = seq
                forwarded_count += 1
                log(f"  {name} 发言 → {next_name} [第{seq}条]")
                if forwarded_count >= rounds * len(ORDER):
                    save_state(state)
                    return finish(f"{DONE_LABEL}：共转发 {forwarded_count} 次")

        save_state(state)
        time.sleep(interval)

    return finish(f"硬超时（{hard_timeout}s）结束")


if __name__ == "__main__":
    sys.exit(main())
