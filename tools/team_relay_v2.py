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

from pi_relay import cap, send, clean, diff_new, bobo_state, pi_idle  # noqa: E402

SES = "bobo-pi-chat"
PANES = {
    "bobo": f"{SES}:0.0",
    "hermes": f"{SES}:0.1",
    "claude": f"{SES}:0.2",
    "pi": f"{SES}:0.3",
}
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
    两种形态都接受。忙碌标志（Initializing/Working/⚡）出现即非空闲。
    """
    bottom = _bottom_lines(screen)
    has_prompt = any("⚕ ❯" in l or l.strip() == "❯" or l.strip().startswith("❯ ")
                     for l in bottom)
    if not has_prompt:
        return False
    busy = ("Initializing agent", "Working", "⏳", "⚡")
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
            "claude": claude_idle, "pi": pi_idle}[name]


def clean_reply(text: str) -> str:
    """清理转发内容：过滤 relay 注入段（【来自 X 的发言】/【硬约束】）、TUI 杂讯。

    按行过滤而非按 \\n\\n 分段：clean() 会去掉空行，段落分隔已不存在，
    按行 startswith 匹配更可靠。
    """
    cleaned = clean(text)
    out = []
    for line in cleaned.splitlines():
        s = line.strip()
        if s.startswith(INJECT_PREFIX) and "的发言】" in s:
            continue
        if s.startswith("【硬约束"):
            continue
        out.append(line)
    return "\n".join(out)


def extract_reply(before: str, after: str) -> str:
    """摘录完整回复：after 相对 before 的新增内容（已过滤杂讯）。"""
    return clean(diff_new(before, after))


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
                # 刚结束一轮思考：摘录完整回复写入通道
                new = extract_reply(base[name], cur)
                new = clean_reply(new)
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
            if not pane_idle_fn(next_name)(cap(PANES[next_name])):
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
