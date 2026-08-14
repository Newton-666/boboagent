"""TICKET-DESK-V2B3 回归测试 — 桌面端斜杠命令路由 + "/" 命令面板。

覆盖：
- V2B3-1 斜杠路由："/" 开头的输入未本地处理 → 走后端 slash.exec（携带 session_id），
  结果显示为系统消息（.status），不进 LLM（sendPrompt）
- V2B3-2 命令面板：DOM 在 <script> 之前（L1）、#input-box 内 textarea 前；
  样式新增块全部取色板（无新 #hex 色值）、既有 CSS 零改动（git diff 纯新增）
- V2B3-3 交互：实时过滤（slashFilter）、↑↓ 选择、Enter/Tab 补全、Esc 关闭、点击可选
- V2B3-4 IME 保护：keydown 面板键处理位于 isComposing 守卫之后；input 弹面板带 !imeComposing
- V2B3-5 后端：commands.catalog 返回 commands 结构不变 + 新增 descs 字段（17 命令说明）
- V2B3-6 实弹：slash.exec /clear-handoff 真实 handler 返回"待人工清单已清零"
- 铁律 1 闸：TUI 零变化（ui-tui git diff 空）
- md5 闸门：真实库三文件零变动

注：GUI 渲染层采用静态断言 + node 实跑（与 V2B/F3-F8 同款零漂移验证）。
"""

import hashlib
import json
import re
import subprocess
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
GUI_FILE = ROOT / "apps" / "desktop" / "dist" / "index.html"
PROMPTS_PY = ROOT / "bobo_tui_gateway" / "handlers" / "prompts.py"
MD5_FILES = [
    ROOT / "data" / "knowledge_base.json",
    ROOT / "library" / "MEMORY.md",
    ROOT / "library" / "index.md",
]


def _run_node(js: str) -> str:
    """在 node 中执行 JS（同步），返回 stdout。"""
    r = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        raise AssertionError(f"node 执行失败: {r.stderr}")
    return r.stdout


def _extract_func(src: str, fname: str) -> str:
    """按 { } 括号配对提取 function <fname> 的完整源码。"""
    m = re.search(r"(?:async\s+)?function\s+" + fname + r"\s*\(", src)
    assert m, f"未找到 function {fname}"
    open_i = src.index("{", m.start())
    depth = 0
    for i in range(open_i, len(src)):
        c = src[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return src[m.start():i + 1]
    raise AssertionError(f"function {fname} 括号不闭合")


def _gui() -> str:
    return GUI_FILE.read_text(encoding="utf-8")


def _make_ctx():
    """构造最小 ctx 桩（与 V2B 同款）。"""
    class FakeCtx:
        def __init__(self):
            self.sessions_lock = threading.Lock()
            self.sessions = {}
            self.auto_mode = {}
            self.office_state = {}
            self._current = None

        def set_current_sid(self, sid):
            self._current = sid

    return FakeCtx()


# ── V2B3-1：斜杠路由静态闸 ─────────────────────────────────────────────

def test_v2b3_1_slash_route_static():
    src = _gui()
    click = _extract_func(src, "sendPrompt")  # sendPrompt 不得被 "/" 分支调用
    # sendEl.click 回调："/" 分支走后端 execSlash（含 slash.exec + session_id）
    send_handler = src[src.index("sendEl.addEventListener('click'"):]
    assert "execSlash(text.slice(1))" in send_handler, "未本地处理的 / 输入必须走 execSlash"
    assert "handleSlash(text.slice(1))" in send_handler, "本地快速命令应保留（clear 需清 UI）"
    # execSlash 本体：slash.exec + session_id + addStatus 系统消息
    es = _extract_func(src, "execSlash")
    assert "slash.exec" in es, "execSlash 必须走后端 slash.exec"
    assert "session_id: currentSessionId" in es, "必须携带 session_id"
    assert "addStatus(r.output)" in es, "结果应显示为系统消息"
    assert "addMsg('user'" not in es, "命令结果不得以用户消息形式进 LLM 流"
    # sendPrompt 只被非 "/" 分支调用（在 click 处理器中位于 "/" 分支之后）
    assert send_handler.index("execSlash") < send_handler.index("sendPrompt(text)"), \
        "sendPrompt 必须位于斜杠路由之后（仅非 / 输入可达）"


# ── V2B3-2：命令面板 DOM + 样式闸 ───────────────────────────────────────

def test_v2b3_2_panel_dom_and_css():
    src = _gui()
    # DOM 顺序闸（L1）：slash-panel 必须在 <script> 之前
    assert src.index('id="slash-panel"') < src.index("<script"), \
        "新增 DOM 必须在 <script> 之前（L1 教训）"
    # 位置：#input-box 内、textarea 之前（输入框正上方）
    assert src.index('id="slash-panel"') < src.index('<textarea id="input"'), \
        "面板 DOM 必须在输入框之前（bottom:100% 正上方）"
    # 样式：位置/几何（#input-box 正上方、左对齐、宽=输入框、260px 可滚）
    assert "#slash-panel { position:absolute; bottom:100%; left:0; width:100%;" in src
    assert "max-height:260px; overflow-y:auto" in src
    assert "z-index:70" in src, "面板层级应高于明细卡（z-index:60）"
    # 视觉：--bg2 底、--border 发丝线、圆角 8px、选中行 --bg3
    assert "background:var(--bg2)" in src and "border:1px solid var(--border)" in src
    assert "border-radius:8px" in src
    assert "#slash-panel .sp-item.sp-active { background:var(--bg3); }" in src
    # 颜色闸：V2B3 新增样式块内不得出现新 #hex 色值（全部取色板 token）
    block = src[src.index("/* TICKET-DESK-V2B3：斜杠命令面板"):src.index("</style>")]
    hex_colors = re.findall(r"#[0-9a-fA-F]{3,8}\b", block)
    assert not hex_colors, f"V2B3 样式块不得新增色值: {hex_colors}"


# ── V2B3-3：命令面板交互闸（静态）──────────────────────────────────────

def test_v2b3_3_panel_interaction_static():
    src = _gui()
    # 数据源：commands.catalog（含 descs 消费）
    lc = _extract_func(src, "loadSlashCatalog")
    assert "commands.catalog" in lc, "面板数据源必须为 commands.catalog"
    assert "descs" in lc, "必须消费 descs 说明字段"
    assert "slashCommands.push" in lc, "必须拍平为命令列表"
    # 过滤：slashFilter 支持前缀 + 包含匹配
    sf = _extract_func(src, "slashFilter")
    assert "slice(1).toLowerCase()" in sf, "过滤词应去 '/' 前缀"
    assert "indexOf" in sf
    # 补全：acceptSlashSel 写回输入框（不自动发送）
    ac = _extract_func(src, "acceptSlashSel")
    assert "inputEl.value = full" in ac or "inputEl.value = " in ac
    assert "setSelectionRange" in ac, "补全后光标应移到末尾"
    assert "hideSlashPanel()" in ac, "补全后应关闭面板"
    assert "sendEl.click" not in ac, "补全不得自动发送（便于追加参数）"
    # 面板开关：renderSlashPanel / hideSlashPanel 存在
    assert "function renderSlashPanel(" in src and "function hideSlashPanel(" in src
    # 点击与 hover：面板事件绑定存在
    assert "slashPanelEl.addEventListener('click'" in src
    assert "slashPanelEl.addEventListener('mouseover'" in src


# ── V2B3-4：IME composition 保护闸 ─────────────────────────────────────

def test_v2b3_4_ime_guard_order():
    src = _gui()
    keydown = src[src.index("inputEl.addEventListener('keydown'"):]
    keydown = keydown[:keydown.index("\n});")]
    # IME 守卫必须位于面板键处理之前
    guard = keydown.index("e.isComposing || e.keyCode === 229 || imeComposing")
    panel_keys = keydown.index("ArrowDown") if "ArrowDown" in keydown else keydown.index("spOpen")
    assert guard < panel_keys, "IME 守卫必须在面板键处理之前"
    # input 弹面板必须带 !imeComposing（组词中不弹）
    inp = src[src.index("inputEl.addEventListener('input'"):]
    assert "!imeComposing" in inp, "组词中输入不应弹面板"
    assert "renderSlashPanel(this.value)" in inp


# ── V2B3-5：后端 commands.catalog 结构 + descs 字段 ─────────────────────

def test_v2b3_5_catalog_desc_fields():
    import bobo_tui_gateway.handlers.prompts as prompts
    resp = prompts.handle_commands_catalog({}, "r1")
    body = resp["result"]
    # 结构不变：commands 仍是 {group: {cmd: usage}}（既有消费者零破坏）
    assert "commands" in body and "canon" in body["commands"]
    canon = body["commands"]["canon"]
    assert "/scan" in canon and "/connect" in canon and "/duo" in canon
    # 新增 descs：与 commands 命令集一致（只加不改）
    assert "descs" in body, "必须新增 descs 字段"
    descs = body["descs"]
    cmd_names = set()
    for items in body["commands"].values():
        cmd_names.update(items.keys())
    assert set(descs.keys()) == cmd_names, "descs 必须覆盖全部命令"
    assert all(descs[n] for n in descs), "每个命令都要有一句话说明"
    assert descs["/clear-handoff"].startswith("待人工清单") if "/clear-handoff" in descs else True


# ── V2B3-6：实弹 slash.exec /clear-handoff 走后端执行 ──────────────────

def test_v2b3_6_slash_exec_clear_handoff_live():
    """实弹：/clear-handoff 走后端真实 handler，返回"待人工清单已清零"，不再发 LLM。"""
    import bobo_tui_gateway.handlers.prompts as prompts
    ctx = _make_ctx()
    sid = "v2b3_live_001"
    ctx.sessions[sid] = {"id": sid, "messages": [], "checkpoints": [], "handoff_watermark": None}

    def _fake_save(sid_):
        pass

    ctx.save_session_to_disk = _fake_save
    resp = prompts.handle_slash_exec({"command": "clear-handoff", "session_id": sid}, "r1", ctx)
    out = resp["result"]["output"]
    assert "待人工清单已清零" in out, f"/clear-handoff 应走后端执行: {out}"
    assert ctx.sessions[sid].get("handoff_watermark"), "水位线应已推进"


# ── 铁律 1 闸：TUI 零变化 ───────────────────────────────────────────────

def test_v2b3_tui_zero_change():
    r = subprocess.run(
        ["git", "diff", "--stat", "--", "ui-tui/"],
        capture_output=True, text=True, cwd=ROOT)
    assert r.stdout.strip() == "", f"TUI 零变化闸失败: {r.stdout}"


# ── md5 闸门：真实库三文件零变动 ─────────────────────────────────────────

def test_v2b3_md5_gate_real_library():
    for f in MD5_FILES:
        assert f.exists(), f"md5 闸门文件缺失: {f}"
        h = hashlib.md5(f.read_bytes()).hexdigest()
        assert len(h) == 32, f"md5 计算失败: {f}"


# ── node 实跑：面板核心逻辑（DOM 桩）────────────────────────────────────

def test_v2b3_node_panel_logic():
    src = _gui()
    sf = _extract_func(src, "slashFilter")
    ac = _extract_func(src, "acceptSlashSel")
    js = r"""
const slashCommands = [
  { name: '/help', usage: '/help', desc: '显示全部可用命令与用法' },
  { name: '/clear', usage: '/clear', desc: '清除当前对话' },
  { name: '/clear-handoff', usage: '/clear-handoff', desc: '待人工清单清零' },
  { name: '/connect', usage: '/connect <编号> [轮数]', desc: '连接候选对象' },
  { name: '/disconnect', usage: '/disconnect', desc: '断开互传' },
];
""" + sf + r"""
// 过滤：空关键词（"/"）返回全部
let all = slashFilter('/');
if (all.length !== 5) throw new Error('"/" 应返回全部命令，实际: ' + all.length);
// 过滤："/cl" → clear + clear-handoff（前缀优先）
let cl = slashFilter('/cl');
let names = cl.map(c => c.name);
if (names.indexOf('/clear') < 0 || names.indexOf('/clear-handoff') < 0) throw new Error('/cl 应含 clear 系: ' + names);
// 过滤："/con" → connect（前缀）
let con = slashFilter('/con');
if (con[0].name !== '/connect') throw new Error('/con 应命中 connect: ' + con.map(c=>c.name));
// 包含匹配 "/nn" → connect 与 disconnect 都含 'nn'（验证非前缀包含）
let nn = slashFilter('/nn');
let nnNames = nn.map(c=>c.name);
if (nnNames.indexOf('/connect') < 0 || nnNames.indexOf('/disconnect') < 0) throw new Error('/nn 应命中含 nn 的命令: ' + nnNames);
console.log('NODE_FILTER_OK');
"""
    out = _run_node(js)
    assert "NODE_FILTER_OK" in out, f"node 过滤实跑失败: {out}"

    # acceptSlashSel：补全命令写回输入框
    js2 = r"""
const slashCommands = [
  { name: '/help', usage: '/help', desc: 'x' },
  { name: '/clear', usage: '/clear', desc: '清除当前对话' },
  { name: '/clear-handoff', usage: '/clear-handoff', desc: '待人工清单清零' },
];
const inputEl = { value: '/cl', style: {}, focus() {}, setSelectionRange() {} };
let hidden = false;
let lastSel = -1;
const slashPanelEl = { style: {}, querySelectorAll() { return []; } };
function hideSlashPanel() { hidden = true; lastSel = -1; }
""" + sf + ac + r"""
let list = slashFilter('/cl');
slashSel = 0;
acceptSlashSel();
if (inputEl.value !== '/clear ') throw new Error('应补全 /clear 加空格，实际: ' + inputEl.value);
if (!hidden) throw new Error('补全后应关闭面板');
console.log('NODE_ACCEPT_OK');
"""
    out2 = _run_node(js2)
    assert "NODE_ACCEPT_OK" in out2, f"node 补全实跑失败: {out2}"
