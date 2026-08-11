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
DEFAULT_ORDER = ["bobo", "hermes", "claude", "pi"]
VALID_AGENTS = set(DEFAULT_ORDER)


def _resolve_order() -> list:
    """票 O-3 豁免：RELAY_ORDER 环境变量（逗号分隔）覆盖轮巡名单。

    默认 bobo,hermes,claude,pi——未设/空/名单非法时回退默认，现行为
    零变化。例：RELAY_ORDER=bobo,pi → 两人小队轮巡（bobo→pi→bobo）。
    票 O-3 审查（pi 0006/0007）整改：
      P1：只过滤空串不校验角色名 → foo,bar 不回退，与票面"空/非法回退
          默认"不符；补 VALID_AGENTS 白名单校验，任一非法角色整体回退。
      P2：单角色自环（bobo→bobo）；补 len>=2 校验。
      补充：重复角色（bobo,bobo）转发链失效，补去重校验。
    """
    raw = os.environ.get("RELAY_ORDER", "").strip()
    order = [n.strip() for n in raw.split(",") if n.strip()] if raw else []
    if not order:
        return list(DEFAULT_ORDER)
    if len(order) < 2:  # P2：单角色自环
        return list(DEFAULT_ORDER)
    if any(n not in VALID_AGENTS for n in order):  # P1：非法角色
        return list(DEFAULT_ORDER)
    if len(set(order)) != len(order):  # 重复角色
        return list(DEFAULT_ORDER)
    return order


def build_panes(session: str, order: list = None) -> dict:
    """票 R1-1 评审点 6：会话名参数化——O-2 搭建器传不同 session 名建 pane 映射。

    票 O-3 豁免：按 order 名单建 pane 映射（pane 序号 = 名单序号），
    支持 2 人小队（RELAY_ORDER=bobo,pi → 0.0=bobo / 0.1=pi）。
    不传 order 时按 RELAY_ORDER/默认名单；禁止硬编码会话名：
    多员工讨论/多会话并存时各 relay 用各自的 RELAY_SESSION（env）
    或显式传参，互不串台。
    """
    order = order or _resolve_order()
    return {name: f"{session}:0.{i}" for i, name in enumerate(order)}


ORDER = _resolve_order()
PANES = build_panes(SES, ORDER)
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


# ── 单实例锁（票 R2-P3：relay.state 记录的 pid 存活检查为唯一事实源）──


def _pid_alive(pid: int) -> bool:
    """pid 是否为存活进程（Unix kill(pid,0) 探活）。"""
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # 进程存在但无权限发信号，视为存活
    except OSError:
        return False


def _state_pid() -> int:
    """relay.state 中记录的 relay 进程 pid（无/损坏返回 0）。"""
    try:
        return int(load_state().get("pid", 0) or 0)
    except Exception:
        return 0


def _pgrep_relay() -> list:
    """pgrep 兜底扫描：同类 relay 进程（旧版未写 state 的 relay 也能拦住）。"""
    try:
        out = subprocess.run(["pgrep", "-f", "team_relay_v2.py"],
                             capture_output=True, text=True, timeout=10).stdout
        return [p for p in out.split() if p.isdigit()]
    except Exception:
        return []


def _acquire_single_instance() -> bool:
    """单实例锁（票 R2-P3）：启动前查 relay.state 存活进程。

    病历（23:22）：同一 office 重复启动 4 次 relay、双实例并发——v1 的
    pgrep 全扫在 cmdline 变体（绝对路径/不同解释器/不同参数）下漏判。
    修复：relay.state 的 pid 字段是唯一事实源——pid 存活 → 已有人持锁，
    退出；pid 失效/缺失 → 本进程接管（写入自己 pid）。pgrep 仅作兜底
    （拦旧版未写 state 的 relay）。返回 True=获得锁，False=已有实例。
    """
    pid = _state_pid()
    if _pid_alive(pid):
        print(f"已有 relay 在运行（relay.state pid={pid} 存活），本次退出", file=sys.stderr)
        return False
    for pid_str in _pgrep_relay():
        if int(pid_str) != os.getpid():
            print(f"已有 team_relay_v2 在运行（pgrep pid={pid_str}），本次退出", file=sys.stderr)
            return False
    return True


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
    """读 inbox/{agent}/ 中序号 > last_seq 的所有发言，按序返回 [(seq, text)]。

    按数字序号排序（TICKET-R2-P1）：字符串排序在 seq >= 10 时乱序
    （"0010.md" < "0002.md"），转发会丢序。
    """
    d = _agent_inbox(agent)
    if not os.path.isdir(d):
        return []
    files = sorted(
        (fn for fn in os.listdir(d)
         if fn.endswith(".md") and not fn.endswith(".tmp")),
        key=_seq_of,
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


def _seq_of(filename: str) -> int:
    """从文件名提取序号：'0003.md' → 3。非预期格式返回 0。"""
    try:
        return int(filename[:4])
    except (ValueError, IndexError):
        return 0


def sanitize_state(state: dict) -> dict:
    """修复 state 与 inbox 实际内容不一致（票 R2-P2 防御性修复）。

    场景 1：state 记录的序号高于 inbox 实际最大序号（文件被删除/损坏）
            → 重置为该 agent 的 inbox 实际最大值（防止转发漏跳）。
    场景 2：state 缺少某 agent → 补 0。
    场景 3：state 有未知 agent key → 保留（不影响转发逻辑，不越权删数据）。

    返回修复后的 state 副本（不修改原 dict）。
    """
    out = {}
    for name in ORDER:
        d = _agent_inbox(name)
        max_seq = 0
        if os.path.isdir(d):
            for fn in os.listdir(d):
                if fn.endswith(".md") and not fn.endswith(".tmp"):
                    max_seq = max(max_seq, _seq_of(fn))
        recorded = state.get(name, 0)
        # state 不应超过 inbox 实际最大值
        out[name] = recorded if recorded <= max_seq else max_seq
    return out


# ── 各自空闲判定（屏幕 capture 只做这个，不提取内容）──
def _bottom_lines(screen: str, n: int = 10) -> list:
    return [l for l in screen.splitlines() if l.strip()][-n:]


def claude_idle(screen: str) -> bool:
    """claude (Claude Code) 空闲：底部 3 行内有独立 ❯ 提示行（非内容引用），
    且无进行中标志。

    Claude Code TUI 特征（我本人最清楚自己的脸）：
        - 空闲：❯ 提示符独占最后一行（或倒数第 2 行，最后是空行）
        - 忙碌：❯ 不出现（思考文本填充屏幕）；或出现 "Thinking…"
        - 工具调用：⏺ 历史标记（结束后残留，0.0s=已完成）≠ 忙碌
        - 确认框："Do you want to proceed" / "requires approval"
        - ⏱ (U+23F1) = 活跃计时器（与 hermes 一致，表示 LLM 调用进行中）

    注意：❯ 出现在内容中（如引用命令 ❯ ls -la）不是提示符——
    提示符特征是独占一行（前后无大量其他内容）。只检查最后 3 行提高精度。
    """
    bottom = _bottom_lines(screen)
    # 空闲提示符（2026-08-11 演练 1 实测补充）：auto mode 下 claude 底部
    # 状态区显示 "auto mode on" 且**无独立 ❯ 提示符**（❯ 只出现在内容
    # 引用里，不能作空闲依据）——auto mode on 行 = 空闲提示的等价形态。
    has_prompt = any(
        l.strip() == "❯" or (l.strip().startswith("❯") and len(l.strip()) < 40)
        or "auto mode on" in l
        for l in bottom
    )
    if not has_prompt:
        return False
    # 忙碌标志只在底部 10 行检查（2026-08-11 演练 1 实测校准）：
    # 全屏扫描被历史发言文本污染（历史引用 Thinking/Working → 误判忙碌）；
    # busy 词以 "esc to interrupt" 为主——2026-08-11 busy 形态实测（0.3s
    # 高频 capture）：claude auto mode 处理消息时（2.8s→3.4s 窗口）屏幕
    # 唯一变化是状态区出现 "esc to interrupt"（可中断 = 正在处理），
    # Thinking/Working 从不出现（"Thought/Worked for Xs" 是完成标记，
    # 不是进行中）。"esc to interrupt" 是状态区 UI 元素，不会出现在
    # 历史发言文本里，天然抗污染。
    busy = ("Thinking", "Working", "⏱", "esc to interrupt",
            "Waiting for", "Do you want to proceed",
            "requires approval", "⌛")
    bottom_text = "\n".join(bottom)
    return not any(b in bottom_text for b in busy)


def hermes_idle(screen: str) -> bool:
    """hermes 空闲：底部出现提示符（⚕ ❯ 或独立 ❯ 行）。

    注意：hermes 空闲时提示行可能是 "⚕ ❯ msg=interrupt…" 或单独的 "❯"，
    两种形态都接受。忙碌标志出现即非空闲。

    hermes TUI 忙碌/空闲时间标志（2026-08-10 团队启动实测）：
        - ⏱ (U+23F1 STOPWATCH)：活跃计时器，LLM 调用进行中 → 忙碌
        - ⏲ (U+23F2 TIMER CLOCK)：等待中计时器，Agent 空闲 → 非忙碌
        - ⏳ (U+23F3 HOURGLASS)：沙漏，可能为忙碌（启动/等待阶段）
    ⚡ 为工具调用历史标记（同 claude 的 ⏺，任务结束后仍残留，0.0s 耗时
    即已完成记录），不代表正在运行，不能作为忙碌标志——2026-08-10 团队
    启动时实测：hermes 空闲（❯ 提示符 + 状态行 ⏲）却被残留 ⚡ 判忙，
    relay 转发死锁。忙碌判定只认状态行活跃标志与 ⏱ 计时器。
    """
    bottom = _bottom_lines(screen)
    has_prompt = any("⚕ ❯" in l or l.strip() == "❯" or l.strip().startswith("❯ ")
                     for l in bottom)
    if not has_prompt:
        return False
    # 忙碌信号只在状态行（含 ⚕ 的那行）检查——2026-08-11 演练 1 实测：
    # 全屏扫描会被屏幕历史发言文本污染（hermes 历史发言引用过
    # "Working/⏳/⏱" 等词 → 误判忙碌 → 转发卡死）。⏱=活跃计时器=忙碌，
    # ⏲=等待计时器=空闲（hermes 本人确认）。
    status_line = next((l for l in bottom if "⚕" in l), "")
    busy = ("Initializing agent", "Working", "⏱", "⏳")
    return not any(b in status_line for b in busy)


def pi_idle(screen: str) -> bool:
    """pi 空闲：无忙碌标志（spinner/Working/Thinking），且底部出现 cwd 路径行。

    pi TUI 特征（pi 本人确认 · TICKET-R2-P2 收编复核）：
        - 空闲：braille spinner 消失 + Working 消失 + 底部出现 ~/... cwd 行
          + 屏幕连续稳定数秒
        - 忙碌：Working / Thinking 文本 + braille spinner（⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏）
        - **token 统计栏（↑/↓ + deepseek 模型名）常驻——idle/busy 都在，
          不能作为空闲信号**；pi_finished 一次性误判的根因正是 token 统计
          一直在、判定永远命中。pi 本人确认后弃用。
        - ⏱/⏲ 计时器是 hermes 状态行特征（非 pi 侧），保留在忙碌标志中
          仅作兜底（pi 屏幕正常情况下不出现）。
    """
    # 必要条件：无忙碌标志（token 统计栏常驻，不作判定依据）。
    # 忙碌检查只查 cwd 行上方紧邻 3 行（内容区尾部）——2026-08-11 演练 1
    # 实测：底部 10 行全扫会被历史发言文本污染（pi 历史讨论引用过
    # "Working/spinner/⏱" 字样 → 误判忙碌）。busy 时 spinner/Working
    # 出现在内容区最底部（紧贴分隔线/cwd 行上方）。
    bottom = _bottom_lines(screen)
    cwd_idx = next((i for i, l in enumerate(bottom)
                    if l.strip().startswith("~/") or l.strip().startswith("/")), None)
    if cwd_idx is None:
        return False  # 无 cwd 行 = 非空闲（pi 本人确认：cwd 行是空闲充分条件）
    tail = bottom[max(0, cwd_idx - 3):cwd_idx]
    busy = ("Working", "Thinking", "⏱", "⠋", "⠙", "⠹", "⠸", "⠼",
            "⠴", "⠦", "⠧", "⠇", "⠏")
    if any(b in "\n".join(tail) for b in busy):
        return False
    return True


def bobo_idle(screen: str) -> bool:
    """bobo 空闲：底部有 > 提示符，且状态行显示 ready。

    bobo 状态行：`─ ● 状态 │ ...`。空闲时状态行固定显示 `● ready`；
    忙碌时显示 `● <emoji> <思考词>… · Ns`（如 reasoning/pondering/
    musing/cogitating 等）。2026-08-11 演练 2 实测：思考词列举法有漏
    （bobo 思考词 "musing" 不在原元组 → 思考期间误判 idle → 回复漏摘、
    链条断在 bobo）。改用状态行 ready 判据，覆盖全部思考词形态。
    """
    bottom = _bottom_lines(screen)
    has_prompt = any(l.strip() == ">" or l.strip().startswith("> ") for l in bottom)
    if not has_prompt:
        return False
    status_line = next((l for l in bottom if "●" in l), "")
    if not status_line:
        return True  # 无状态行（异常/极短屏幕）→ 不阻塞转发，判空闲
    return "ready" in status_line


def pane_idle_fn(name: str):
    return {"bobo": bobo_idle, "hermes": hermes_idle,
            "claude": claude_idle, "pi": pi_idle}[name]


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
    # 票 O-3 审查 P3（pi 0007）：标题/文件名不再硬编码"四Agent"，
    # 按实际 ORDER 名单生成（两人序 → bobo、pi 团队讨论汇总）
    agent_label = "、".join(ORDER)
    fname = os.path.join(vault_dir, f"{agent_label}团队讨论汇总-{ts}.md")
    lines = [
        f"# {agent_label} 团队讨论汇总（{ts}）",
        "",
        f"> 参与者：{' / '.join(ORDER)}",
        f"> 调度：team_relay v2 结构化通道（{' → '.join(ORDER)} 轮巡）",
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

    # 单实例锁（票 R2-P3：state 记录的 pid 存活检查为唯一事实源，pgrep 兜底）
    me = os.getpid()
    if not _acquire_single_instance():
        return 0
    # 接管：把本进程 pid 写入 relay.state（心跳在轮询循环里续写，防误判崩溃）
    st = load_state()
    st["pid"] = me
    st["started_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    save_state(st)

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
    state = sanitize_state(load_state())       # 票 R2-P2：防御 state/inbox 不一致
    base = {name: cap(pane) for name, pane in PANES.items()}
    prev_screen = dict(base)                    # 票 R2-P2：上一轮屏幕，检测 busy 稳定性
    idle_prev = {name: pane_idle_fn(name)(base[name]) for name in ORDER}
    pre_busy_base = {}                          # 票 R2-P2：idle→busy 转变时保存的"发言前屏幕"
    spoken = {name: 0 for name in ORDER}        # 已摘录条数
    forwarded = {name: 0 for name in ORDER}   # 本次运行实际转发条数（轮次上限用）
    forwarded_count = 0
    t_start = time.time()
    hard_timeout = 3600  # 1 小时硬上限

    log("建立基线（3s）…")
    time.sleep(3)
    base = {name: cap(pane) for name, pane in PANES.items()}
    prev_screen = dict(base)
    idle_prev = {name: pane_idle_fn(name)(base[name]) for name in ORDER}

    def finish(reason: str) -> int:
        log(f"{reason}，共转发 {forwarded_count} 次")
        try:
            fname = write_summary(state, spoken)
            log(f"已生成 Obsidian 汇总：{fname}")
        except Exception as e:
            log(f"生成 Obsidian 汇总失败：{e}")
        # 收尾（票 R2-P3）：正常退出释放单实例锁（清 pid），防陈旧 state 占锁
        state["pid"] = None
        save_state(state)
        logf.close()
        return 0

    log("开始轮询…")
    while time.time() - t_start < hard_timeout:
        # ── 阶段 1：摘录（busy→idle 转变 = 一轮思考结束，摘完整回复）──
        # 票 R2-P2 修复：三方发言检测从未触发（hermes/claude/pi）。
        # 根因：① idle 函数忙碌标志不完整（缺 ⏱/Thinking/spinner）；
        # ② base[name] 是从 init 时取的（含历史），diff_new 在大量公共行
        #    上 SequenceMatcher 易漏新内容，且 _capture_reply 的 clean_reply
        #    过滤注入段后可能 <10 字符被静默丢弃。
        # 修复：idle→busy 时保存 pre_busy_base[name]（发言前的干净屏幕），
        # busy→idle 时用 pre_busy_base 做 diff——比 init base 精确得多。
        # 修复后 diff 范围 = 仅本轮的注入+新回复，clean_reply 再过滤注入段。
        for name in ORDER:
            pane = PANES[name]
            cur = cap(pane)
            idle_now = pane_idle_fn(name)(cur)

            if idle_prev[name] and not idle_now:
                # idle→busy 转变：保存发言前的干净屏幕作为 diff 基线
                pre_busy_base[name] = prev_screen.get(name, base[name])
            elif (not idle_prev[name]) and idle_now:
                # busy→idle 转变：用 pre_busy_base（发言前屏幕）做 diff
                capture_base = pre_busy_base.pop(name, base[name])
                new = _capture_reply(name, capture_base, cur)
                if len(new.strip()) >= 10:
                    seq = write_inbox(name, new)
                    spoken[name] += 1
                    log(f"{name} 发言（{len(new)}字符）写入 inbox {seq:04d} [第{spoken[name]}次]")
                else:
                    log(f"{name} busy→idle 转变但摘录为空（{len(new.strip())}字符），跳过")
                # 更新 base 为当前屏幕（下一次同一 agent 发言的备用基线）
                base[name] = cur

            idle_prev[name] = idle_now
            prev_screen[name] = cur

        # ── 阶段 2：转发（通道驱动：inbox 新序号文件 → 下一位空闲时转发）──
        # TICKET-R2-P1：触发只看通道（文件序号 vs state），不依赖摘录计数。
        # 旧实现用 spoken（本次运行摘录计数）与 state（跨运行持久序号）互比：
        # 残留高位 state（封口 999 / 上次运行遗留）→ 永不触发 = 23:30 零转发；
        # inbox 非 1 起始序号 → 计数追不上 → 转 1 条即停 = 23:05 停摆。
        state = sanitize_state(state)  # 自愈：通道清理/封口残留不阻塞转发
        for name in ORDER:
            if forwarded[name] >= rounds:
                continue  # 该 agent 本轮转发已达上限
            msgs = read_new_inbox(name, state.get(name, 0))
            if not msgs:
                continue  # 无新发言（触发只看通道）
            next_name = ORDER[(ORDER.index(name) + 1) % len(ORDER)]
            # 票 R1：发送前复核目标 pane 身份（unknown 永不通过复核，L3 铁律沿用）
            ok, reason, next_screen = verify_target_pane(next_name)
            if not ok:
                log(f"  {next_name} 复核失败：{reason}（unknown，拒绝转发 {name} 的发言）")
                continue
            if not pane_idle_fn(next_name)(next_screen):
                log(f"  {next_name} 忙碌，暂缓转发 {name} 的发言（下次重试）")
                continue  # 不更新 state，下轮重试
            for seq, content in msgs:
                if forwarded[name] >= rounds:
                    break
                msg = f"{INJECT_PREFIX} {name} 的发言】\n{content}\n\n{READONLY_RULE}"
                send(PANES[next_name], msg)
                state[name] = seq
                forwarded[name] += 1
                forwarded_count += 1
                log(f"  {name} 发言 → {next_name} [第{seq}条]")
                # 注入后重设目标基线：注入消息已入对方历史，下次摘录只取
                # 新回复，防把注入内容当发言回声转发（TICKET-R2-P1）
                time.sleep(0.8)
                base[next_name] = cap(PANES[next_name])
                idle_prev[next_name] = pane_idle_fn(next_name)(base[next_name])
                save_state(state)  # 逐条持久化，缩小崩溃丢状态窗口
                if forwarded_count >= rounds * len(ORDER):
                    return finish(f"{DONE_LABEL}：共转发 {forwarded_count} 次")

        state["pid"] = os.getpid()  # 心跳：续写 pid，防 state 被误判为陈旧
        save_state(state)
        time.sleep(interval)

    return finish(f"硬超时（{hard_timeout}s）结束")


if __name__ == "__main__":
    sys.exit(main())
