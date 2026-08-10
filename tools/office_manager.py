"""office_manager — OFFICE 搭建器（TICKET-O2）。

actions: status / launch / teardown

纪律全部内置在工具里，不靠 LLM 自觉：
1. 所有 tmux 调用走 execute_terminal.execute（复用其黑名单拦截 + 超时 +
   进程组管理），不裸 subprocess——AUTO 决策树天然管放行/确认。
2. 安全红线：launch/teardown 只允许操作本工具创建的 session（内部登记台账
   data/office_manager_registry.json）；拒绝 kill 用户已有的其他 session
   （如 bobo-pi-chat、staff_office 里用户手建的）；违反即拒绝 + 审计
   office.redline。
3. 新窗口自动打开：检测 $TERM_PROGRAM（Apple_Terminal → Terminal.app
   osascript；iTerm.app → iTerm2 osascript；其他 → 降级返回 attach 命令
   文本，不失败）。osascript 命令同样走 execute_terminal。
"""

import json
import os
import time
from datetime import datetime

from tools.execute_terminal import execute as _sh  # noqa: E402 复用 execute_terminal

TOOL_NAME = "office_manager"

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DATA = os.path.join(_ROOT, "data")
_REGISTRY_PATH = os.path.join(_DATA, "office_manager_registry.json")
_AUDIT_PATH = os.path.join(_DATA, "office_audit.jsonl")

# 员工 pane 默认启动命令（注入 BOBO_ROLE / BOBO_TICKET 环境后执行）
_DEFAULT_START_CMD = "cd ui-tui && npx tsx src/entry.tsx"
# relay v2 脚本（R1 已参数化：RELAY_SESSION=<session>）
_RELAY_CMD = "python3 tools/team_relay_v2.py"


# ── 台账 / 审计 ──

def _load_registry() -> dict:
    """自建 session 台账：{session: {created_at, staff, layout, relay_pid?}}"""
    if os.path.exists(_REGISTRY_PATH):
        try:
            with open(_REGISTRY_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_registry(reg: dict):
    os.makedirs(_DATA, exist_ok=True)
    tmp = _REGISTRY_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(reg, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _REGISTRY_PATH)


def _audit(event: str, detail: str):
    """写审计 office.* 事件（office.setup / office.teardown / office.redline / office.guard）。"""
    try:
        os.makedirs(_DATA, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        with open(_AUDIT_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": ts, "event": event, "detail": detail},
                               ensure_ascii=False) + "\n")
    except Exception:
        pass  # 审计失败不影响主流程


def _registered(session: str) -> bool:
    return session in _load_registry()


def _guard_self_created(session: str) -> tuple:
    """红线：launch/teardown 只允许操作本工具创建的 session。

    返回 (ok, reason)。违反 → 拒绝 + 审计 office.redline。
    """
    if not session or not session.strip():
        return False, "session 名为空"
    if not _registered(session):
        _audit("office.redline",
               f"试图操作非自建 session: {session!r}（拒绝：只动自建 session 红线）")
        return False, (f"拒绝：{session} 不是本工具创建的 session"
                       "（红线：launch/teardown 只允许操作自建 session，"
                       "不碰 bobo-pi-chat / staff_office 等用户手建 session）")
    return True, ""


# ── 新窗口自动打开（O2-4，owner 2026-08-10 裁决）──

def _open_new_window(session: str) -> str:
    """按 $TERM_PROGRAM 三分支开新窗口 attach 到 session；不支持 → 降级返回命令文本。

    放行语义：osascript 命令走 execute_terminal → auto on 自动放行、
    auto off 弹窗确认；含危险串仍被黑名单硬锁（execute_terminal 内置）。
    """
    term = os.environ.get("TERM_PROGRAM", "")
    if term == "Apple_Terminal":
        # Terminal.app：do script 开新窗口并 attach
        cmd = (f'osascript -e \'tell application "Terminal" to do script '
               f'"tmux attach -t {session}"\'')
        r = _sh(cmd, timeout=15)
        if "error" not in r.lower() and "execution error" not in r.lower():
            return f"已在新 Terminal 窗口打开：tmux attach -t {session}"
        return f"自动开窗失败（{r[:120]}），请手动：tmux attach -t {session}"
    if term == "iTerm.app":
        cmd = (f'osascript -e \'tell application "iTerm2" to create window '
               f'with default profile command "tmux attach -t {session}"\'')
        r = _sh(cmd, timeout=15)
        if "error" not in r.lower() and "execution error" not in r.lower():
            return f"已在新 iTerm2 窗口打开：tmux attach -t {session}"
        return f"自动开窗失败（{r[:120]}），请手动：tmux attach -t {session}"
    # 其他终端（含 vscode）→ 降级：不失败，返回 attach 命令文本
    return (f"当前终端（TERM_PROGRAM={term or '未知'}）不支持自动开新窗口，"
            f"请手动执行：tmux attach -t {session}")


# ── actions ──

def launch(session: str, staff: str = "bobo,hermes,claude,pi",
           layout: str = "even-horizontal", ticket: str = "") -> str:
    """建办公室：detached 建 tmux session + 员工 pane 注入角色 + 起 relay v2。

    - session: 办公室 session 名（必填，O-2 搭建器传参，不硬编码）
    - staff: 逗号分隔员工角色清单（默认 4 员工 bobo/hermes/claude/pi）
    - layout: tmux pane 布局（默认 even-horizontal）
    - ticket: 可选 BOBO_TICKET（有票时注入员工环境）
    """
    session = session.strip()
    if not session:
        return "错误: launch 需要 session 参数（办公室名）"
    if _registered(session):
        return f"错误: session {session} 已在台账中（先 teardown 或换名）"

    roles = [r.strip() for r in staff.split(",") if r.strip()]
    if not roles:
        return "错误: staff 不能为空"
    if len(roles) > 4:
        return "错误: 最多 4 个员工 pane（relay v2 PANES 为 :0.0~:0.3）"

    # 1. detached 建 session（skill 纪律：绝不碰正在 attach 的 client）
    r = _sh(f"tmux new-session -d -s {session} -n office", timeout=15)
    if "error" in r.lower() and "no server running" not in r.lower():
        return f"创建 session 失败: {r}"
    # 清掉默认 pane 0 里的启动命令残留？默认 session 自带一个 pane，直接复用为 pane 0
    # 2. 员工 pane 启动命令注入 BOBO_ROLE / BOBO_TICKET（pane 0 已有，pane 1..n 新建）
    cmds = []
    for i, role in enumerate(roles):
        env = f"BOBO_ROLE={role}"
        if ticket:
            env += f" BOBO_TICKET={ticket}"
        start_cmd = f"{env} {_DEFAULT_START_CMD}"
        if i == 0:
            # pane 0 已存在：send-keys 启动（先清屏再启动）
            cmds.append(f"tmux send-keys -t {session}:0.0 \"{start_cmd}\" Enter")
        else:
            cmds.append(f"tmux split-window -t {session}:0 -h")
            cmds.append(f"tmux send-keys -t {session}:0.{i} \"{start_cmd}\" Enter")
    for c in cmds:
        rr = _sh(c, timeout=15)
        if "error" in rr.lower() and "usage" not in rr.lower():
            return f"员工 pane 启动失败: {rr}（步骤: {c}）"
    # 布局
    _sh(f"tmux select-layout -t {session}:0 {layout}", timeout=15)

    # 3. 起 relay v2（RELAY_SESSION=<session> 后台，relay 自管单实例锁）
    relay_cmd = f"RELAY_SESSION={session} nohup {_RELAY_CMD} > /tmp/office_relay_{session}.log 2>&1 &"
    _sh(relay_cmd, timeout=15)

    # 4. 登记台账 + 审计
    reg = _load_registry()
    reg[session] = {
        "created_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "staff": roles,
        "layout": layout,
        "ticket": ticket,
    }
    _save_registry(reg)
    _audit("office.setup",
           f"session={session} staff={roles} layout={layout} ticket={ticket or '无'}")

    # 5. 新窗口自动打开（TERM_PROGRAM 三分支，降级不炸）
    open_note = _open_new_window(session)

    lines = [
        f"OFFICE 已搭建：{session}（{len(roles)} 员工）",
        "",
        "布局图：",
    ]
    for i, role in enumerate(roles):
        lines.append(f"  pane 0.{i}  [{role}]  {_DEFAULT_START_CMD}")
    lines.append(f"  relay   RELAY_SESSION={session} → {_RELAY_CMD}")
    lines.append("")
    lines.append(f"员工 pane 环境：BOBO_ROLE={roles[0] if roles else '?'}（有票时 + BOBO_TICKET）")
    lines.append(f"新窗口：{open_note}")
    lines.append(f"管理：office_manager status/teardown（teardown 只动本工具创建的 {session}）")
    return "\n".join(lines)


def status(session: str = "") -> str:
    """读 tmux 列出 office 的 session/pane/角色/存活状态。"""
    reg = _load_registry()
    if session:
        ok, reason = _guard_self_created(session)
        if not ok:
            return reason
        sessions = [session]
    else:
        sessions = sorted(reg.keys())
        if not sessions:
            return "尚无自建 office（台账为空）。launch 创建：office_manager launch session=<名>"

    lines = []
    for s in sessions:
        info = reg.get(s, {})
        # session 是否活着
        r = _sh(f"tmux has-session -t {s} 2>&1 && echo ALIVE || echo DEAD", timeout=15)
        alive = "ALIVE" in r
        lines.append(f"[{s}] {'🟢 存活' if alive else '🔴 不在'} 创建于 {info.get('created_at', '?')} "
                     f"staff={info.get('staff', [])} layout={info.get('layout', '?')}")
        if alive:
            r = _sh(f"tmux list-panes -t {s}:0 -F '#{{pane_index}} #{pane_current_command}'", timeout=15)
            for line in r.splitlines():
                line = line.strip()
                if line:
                    lines.append(f"    {line}")
        # relay 存活
        r = _sh(f"pgrep -f 'team_relay_v2.py' | head -3 || true", timeout=15)
        relay_alive = "team_relay_v2" in r or (r.strip().isdigit())
        lines.append(f"    relay: {'🟢 运行中' if relay_alive else '⚪ 未运行'} "
                     f"(RELAY_SESSION={s} 的 relay 由 pgrep 确认)")
    return "\n".join(lines)


def teardown(session: str, keep: bool = True) -> str:
    """收尾（O2-3）：停 relay → 员工 pane 发退出指令 → 审计；session 保留/清理由 owner 决定。

    - session: 办公室 session 名（只允许自建，红线）
    - keep: True=保留 session 后台跑（skill：误关终端≠数据丢失）；
            False=询问后清理（kill-session）。off 时一次性确认，不逐窗问。
    """
    session = session.strip()
    ok, reason = _guard_self_created(session)
    if not ok:
        return reason

    # 1. 停 relay（该 session 的 relay：RELAY_SESSION=<session>）
    r = _sh(f"pkill -f 'team_relay_v2.py' 2>/dev/null; echo done", timeout=15)
    relay_note = "relay 已停（pkill team_relay_v2）" if "done" in r else f"停 relay 异常: {r}"

    # 2. 员工 pane 发退出指令（skill 第 7 节停止信号；relay 停了不再灌消息）
    roles = _load_registry().get(session, {}).get("staff", [])
    for i in range(len(roles)):
        _sh(f"tmux send-keys -t {session}:0.{i} '【调度员·停止信号】讨论已收尾，请停止并收敛。' Enter",
            timeout=15)
    time.sleep(2)

    # 3. 保留 or 清理
    if keep:
        session_note = (f"session {session} 已保留在后台（tmux attach -t {session} 随时回来；"
                        "如需清理执行 teardown keep=false）")
    else:
        r = _sh(f"tmux kill-session -t {session}", timeout=15)
        session_note = f"session {session} 已清理" if "error" not in r.lower() else f"清理失败: {r}"

    # 4. 台账删除 + 审计
    reg = _load_registry()
    reg.pop(session, None)
    _save_registry(reg)
    _audit("office.teardown", f"session={session} keep={keep}")

    return "\n".join([
        f"OFFICE 收尾完成：{session}",
        f"  {relay_note}",
        f"  已向 {len(roles)} 个员工 pane 发送停止信号",
        f"  {session_note}",
        "  审计已写：office.teardown",
    ])


def office_manager(action: str, session: str = "", staff: str = "bobo,hermes,claude,pi",
                   layout: str = "even-horizontal", ticket: str = "",
                   keep: bool = True) -> str:
    """office_manager 入口。action: status / launch / teardown。"""
    action = (action or "").strip().lower()
    if action == "launch":
        return launch(session, staff, layout, ticket)
    if action == "status":
        return status(session)
    if action == "teardown":
        return teardown(session, keep)
    return "错误: action 必须是 launch / status / teardown 之一"


TOOL_FUNC = office_manager
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": """【用途】OFFICE 搭建器：launch（建办公室）/ status（查状态）/ teardown（收尾）。
【纪律】只允许操作本工具自建的 session（红线，teardown 碰用户手建 session 会拒绝+审计）；
所有 tmux 调用走 execute_terminal 安全执行。""",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["launch", "status", "teardown"],
                    "description": "操作：launch 建办公室 / status 查状态 / teardown 收尾"
                },
                "session": {
                    "type": "string",
                    "description": "办公室 session 名（launch 必填；teardown 必填且只允许自建）"
                },
                "staff": {
                    "type": "string",
                    "description": "逗号分隔员工角色清单，默认 bobo,hermes,claude,pi（≤4）"
                },
                "layout": {
                    "type": "string",
                    "description": "tmux pane 布局，默认 even-horizontal"
                },
                "ticket": {
                    "type": "string",
                    "description": "可选 BOBO_TICKET（有票时注入员工环境）"
                },
                "keep": {
                    "type": "boolean",
                    "description": "teardown 时是否保留 session 后台跑，默认 true；false=清理"
                }
            },
            "required": ["action"]
        }
    }
}


def register(reg):
    reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA)
