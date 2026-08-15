"""TICKET-GUI-F10 回归测试 — 事件流串台修复（后台会话事件不渲染）。

覆盖：
- F10-1 静态断言（GUI 闸门）：
  * 分发层把 params.session_id（server_utils.emit 顶层字段）注入回调数据
  * isForeignSession 闸门存在：事件带 session_id 且非当前会话 → 拦截 + 后台活跃标记
  * 全部渲染类回调开头都有闸门（message.start/delta/complete、tool.start/complete、
    status.update、session.auto_state/office_state、terminal.output、gateway.error）
  * approval.request 记录 _approvalSid；approvalRespond 用 _approvalSid 应答
    （审批不吞弹窗——全局单队列，但应答回来源会话，防切窗错配）
  * 后台活动中标记：bgActiveSids / markBgActive / clearBgActive + .bg-active-dot
- F10-2 node 实跑模拟双会话（提取真实 isForeignSession + 真实渲染回调）：
  * 场景 1：currentSessionId=B，灌入 A 会话事件流（message.delta/tool.start/status.update）
    → 三条渲染通道计数全 0（B 窗口零渲染），A 被标记后台活动中
  * 场景 2：灌入 B 会话事件 → 三条通道正常渲染（当前会话放行）
  * 场景 3：切回 A（currentSessionId=A）→ A 事件放行渲染；clearBgActive 清标记；
    无 sid 全局事件恒放行

注：GUI 渲染层无法无头全自动化，采用静态断言 + node 实跑（与 F2/F3/F4/F6/F6B/F6C 同款，
零漂移验证当前 HTML 内真实函数）。
"""

import json
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
GUI_FILE = ROOT / "apps" / "desktop" / "dist" / "index.html"


# ── 辅助：提取当前 HTML 内真实 JS（零漂移，与 F6C 同款） ──────────────

def _extract_func(src: str, fname: str) -> str:
    """按 { } 括号配对提取 function <fname> 的完整源码。"""
    m = re.search(r"function\s+" + fname + r"\s*\(", src)
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


def _extract_event_block(src: str, event: str) -> str:
    """提取 on('<event>', function(...) { ... }) 的完整块（括号配对到闭合 );）。"""
    pat = re.compile(r"on\('" + re.escape(event) + r"',\s*function[^)]*\)\s*\{")
    m = pat.search(src)
    assert m, f"未找到 on('{event}') 事件块"
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
    raise AssertionError(f"on('{event}') 括号不闭合")


def _run_node(js: str) -> str:
    """在 node 中执行 JS（同步），返回 stdout。"""
    r = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        raise AssertionError(f"node 执行失败: {r.stderr}")
    return r.stdout


# ── F10-1：静态断言（GUI 闸门） ────────────────────────────────────────

def test_f10_1_dispatch_injects_sid():
    """分发层必须把 params.session_id 注入回调数据（根因修复点）。"""
    src = GUI_FILE.read_text(encoding="utf-8")
    assert "msg.params.session_id" in src, "F10: 分发层需读取 params.session_id"
    assert "Object.assign({}, evData, { session_id: msg.params.session_id })" in src, \
        "F10: 分发层需把 sid 注入回调数据（evData = payload + session_id）"
    # 分发仍保留 payload 或 params 的原始语义（不破坏全局事件）
    assert "msg.params.payload || msg.params" in src, "F10: payload 优先、params 兜底语义不破"


def test_f10_1_foreign_gate_exists():
    """isForeignSession 闸门存在且语义正确：带 sid 且非当前会话 → 拦截。"""
    src = GUI_FILE.read_text(encoding="utf-8")
    assert "function isForeignSession(data)" in src, "F10: 需要 isForeignSession 统一闸门"
    g = _extract_func(src, "isForeignSession")
    assert "data && data.session_id" in g, "F10: 闸门须读注入的 session_id"
    assert "sid === currentSessionId" in g, "F10: 当前会话事件放行"
    assert "markBgActive(sid)" in g, "F10: 后台会话事件须打活跃标记"
    assert "return false" in g, "F10: 无 sid / 当前会话 → 放行（全局事件语义）"
    assert "return true" in g, "F10: 后台会话 → 拦截"


def test_f10_1_all_render_handlers_gated():
    """全部渲染类回调开头必须有 isForeignSession 闸门。"""
    src = GUI_FILE.read_text(encoding="utf-8")
    # 事件名 → 回调参数名（terminal.output 用 payload，其余用 data）
    gated = {
        "message.start": "data",
        "message.delta": "data",
        "message.complete": "data",
        "tool.start": "data",
        "tool.complete": "data",
        "status.update": "data",
        "terminal.output": "payload",
        "gateway.error": "data",
    }
    for event, arg in gated.items():
        block = _extract_event_block(src, event)
        # 闸门必须出现在回调体最前（参数行后第一句）
        head = block[block.index("{"):]
        assert f"if (isForeignSession({arg})) return;" in head, \
            f"F10: on('{event}') 回调开头缺少 isForeignSession 闸门"
    # 模式徽标：单行回调内联闸门
    assert "on('session.auto_state', function(data) { if (isForeignSession(data)) return;" in src, \
        "F10: session.auto_state 需要闸门（A 会话 AUTO 不能点亮 B）"
    assert "on('session.office_state', function(data) { if (isForeignSession(data)) return;" in src, \
        "F10: session.office_state 需要闸门"


def test_f10_1_approval_not_misrouted():
    """审批不吞弹窗，但应答回来源会话（_approvalSid），防切窗错配。"""
    src = GUI_FILE.read_text(encoding="utf-8")
    assert "var _approvalSid = null" in src, "F10: 需要 _approvalSid 声明"
    assert "_approvalSid = (data && data.session_id) || currentSessionId" in src, \
        "F10: approval.request 须记录弹窗来源会话"
    assert "session_id: _approvalSid, choice: choice" in src, \
        "F10: approvalRespond 须用 _approvalSid 应答（不能用 currentSessionId）"
    # 弹窗本身保留（审批是引擎全局单队列，不吞）
    assert "approval-overlay').classList.add('open')" in src, "F10: 审批弹窗展示不破"


def test_f10_1_bg_active_marker():
    """后台活动中标记：活跃位 + 侧栏圆点 + 切回清除。"""
    src = GUI_FILE.read_text(encoding="utf-8")
    assert "var bgActiveSids = {}" in src, "F10: 需要后台活跃位容器"
    assert "function markBgActive(sid)" in src, "F10: 需要 markBgActive"
    assert "function clearBgActive(sid)" in src, "F10: 需要 clearBgActive"
    mb = _extract_func(src, "markBgActive")
    assert "bgActiveSids[sid] = 1" in mb, "F10: markBgActive 须置活跃位"
    cb = _extract_func(src, "clearBgActive")
    assert "delete bgActiveSids[sid]" in cb, "F10: clearBgActive 须清活跃位"
    assert "bg-active-dot" in src, "F10: 需要 .bg-active-dot 圆点样式"
    assert "bgActiveSids[s.id]" in src, "F10: renderSessions 须按活跃位渲染圆点"
    assert "clearBgActive(sid)" in src, "F10: loadSession 切回须清标记（resume 全量兜底）"
    # L9：圆点取色板现有色，禁止新颜色
    assert "background:var(--text-muted)" in src, "F10: 圆点必须取色板 --text-muted"


# ── F10-2：node 实跑模拟双会话 ─────────────────────────────────────────

def _f10_node_script() -> str:
    """构造 node 脚本：真实 isForeignSession + 真实渲染回调 + 桩 DOM/计数。

    场景 1：currentSessionId=B，灌 A 会话事件流 → 三通道零渲染 + A 活跃标记
    场景 2：currentSessionId=B，灌 B 会话事件 → 三通道正常渲染
    场景 3：切回 A → A 事件放行；clearBgActive 清标记；无 sid 事件放行
    """
    src = GUI_FILE.read_text(encoding="utf-8")
    fns = "\n".join([
        _extract_func(src, "isForeignSession"),
        _extract_func(src, "markBgActive"),
        _extract_func(src, "clearBgActive"),
    ])
    # 顶层活跃位容器（var 声明，非函数体，需单独提取）
    bg_m = re.search(r"var bgActiveSids = \{\};", src)
    assert bg_m, "F10: 需要 var bgActiveSids 顶层容器"
    fns = bg_m.group(0) + "\n" + fns
    # 真实常量 STATUS_DIAG_KINDS（status.update 回调引用）
    sk_m = re.search(r"var STATUS_DIAG_KINDS = \{[^;]*\};", src)
    assert sk_m, "F10: 需要 STATUS_DIAG_KINDS 常量"
    # 真实回调块 → 纯函数表达式（去掉 on('x', 前缀与尾部 );）
    blocks = {}
    for event in ("message.delta", "tool.start", "status.update"):
        b = _extract_event_block(src, event)
        b = re.sub(r"^on\('[^']+',\s*", "", b)
        b = re.sub(r"\);$", "", b).strip()
        blocks[event] = b
    script = f"""
const assert = require('assert');

// ── mini-DOM 桩（classList 实时读 className；支持 appendChild/insertBefore/查询）──
function miniEl(cls) {{
  const el = {{
    _className: cls || '', _children: [], _subs: {{}}, style: {{}},
    id: '', innerHTML: '', textContent: '', parentNode: null, _attrs: {{}},
    setAttribute(k, v) {{ this._attrs[k] = v; }},
    appendChild(ch) {{
      if (ch.parentNode) {{
        const oldKids = ch.parentNode._children;
        const i = oldKids.indexOf(ch);
        if (i >= 0) oldKids.splice(i, 1);
      }}
      ch.parentNode = this; this._children.push(ch); return ch;
    }},
    insertBefore(ch, ref) {{
      const i = this._children.indexOf(ref);
      ch.parentNode = this;
      if (i < 0) this._children.push(ch); else this._children.splice(i, 0, ch);
      return ch;
    }},
    get lastElementChild() {{
      return this._children.length ? this._children[this._children.length - 1] : null;
    }},
    get previousElementSibling() {{
      if (!this.parentNode) return null;
      const kids = this.parentNode._children;
      const i = kids.indexOf(this);
      return i > 0 ? kids[i - 1] : null;
    }},
    querySelector(sel) {{
      if (sel === '.think-text') {{
        if (!this._thinkTextEl) this._thinkTextEl = {{ textContent: this._thinkText || '' }};
        return this._thinkTextEl;
      }}
      return null;
    }},
    querySelectorAll() {{ return []; }},
    onclick: null,
  }};
  Object.defineProperty(el, 'className', {{
    get() {{ return el._className; }},
    set(v) {{ el._className = v || ''; }},
  }});
  el.classList = {{
    contains(c) {{ return (el._className || '').split(/\\s+/).filter(Boolean).includes(c); }},
    add(c) {{ if (!el.classList.contains(c)) el._className = (el._className + ' ' + c).trim(); }},
    toggle(c, force) {{
      const has = el.classList.contains(c);
      if (force === undefined) force = !has;
      if (force && !has) el._className = (el._className + ' ' + c).trim();
      if (!force && has) el._className = el._className.split(/\\s+/).filter(x => x && x !== c).join(' ');
      return force;
    }},
  }};
  return el;
}}

// ── 全局桩 ──
const chatEl = miniEl('chat');
chatEl.scrollTop = 0; chatEl.scrollHeight = 0;
const welcomeEl = miniEl('welcome');
const sendEl = miniEl('button');
const document = {{
  createElement: (tag) => miniEl(tag),
  getElementById: (id) => (id === 'session-search' ? {{ value: '' }} : null),
}};
let thinkBoxEl = null, thinkText = '', toolsCalledThisRound = false, messaging = false;
// TICKET-DESK-V2D5：认知状态条新增全局（桩同步，防 ReferenceError）
let roundMemBaseline = null, roundMemInjected = 0, roundToolCount = 0;
let toolIdCounter = 0, streamingId = null, sendTimeoutId = null;
function createThinkBox() {{ return miniEl('think-box show'); }}
function collapseThinkBox() {{}}
function debug() {{}}
function setBusy() {{}}
function showStop() {{}}
// 渲染通道计数器（tool.start → addTool；status.update → addStatus）
const renders = {{ delta: 0, tool: 0, status: 0 }};
function addTool() {{ renders.tool++; }}
function addStatus() {{ renders.status++; }}
function setMode() {{}}
function renderSessions() {{}}
{sk_m.group(0)}

// ── 真实代码（从 dist/index.html 提取）──
{fns}
let currentSessionId = null;
const deltaHandler = {blocks['message.delta']};
const toolHandler = {blocks['tool.start']};
const statusHandler = {blocks['status.update']};

// 辅助：跑一遍 delta 后取思考框文本（渲染是否发生的证据）
function runDelta(sid, text) {{
  thinkBoxEl = null; thinkText = ''; chatEl._children.length = 0;
  deltaHandler({{ session_id: sid, text: text }});
  return thinkText;
}}

// ── 场景 1：currentSessionId=B，灌 A 会话事件流 → B 窗口零渲染 ──
currentSessionId = 'B';
assert(runDelta('A', 'A的思考') === '', '场景1: A 的 delta 不得渲染进 B');
assert(renders.tool === 0, '场景1: A 的 tool.start 不得渲染进 B');
toolHandler({{ session_id: 'A', name: 'read_local_file', tool_id: 't1' }});
assert(renders.tool === 0, '场景1: A 的 tool.start 渲染计数必须为 0');
statusHandler({{ session_id: 'A', text: 'A的状态' }});
assert(renders.status === 0, '场景1: A 的 status.update 渲染计数必须为 0');
assert(bgActiveSids['A'] === 1, '场景1: A 应被打"后台活动中"标记');
assert(bgActiveSids['B'] === undefined, '场景1: 当前会话 B 不应有后台标记');

// ── 场景 2：灌 B 会话事件 → 当前会话正常渲染 ──
const t2 = runDelta('B', 'B的思考');
assert(t2 === 'B的思考', '场景2: B 的 delta 必须正常渲染，实际: ' + JSON.stringify(t2));
toolHandler({{ session_id: 'B', name: 'execute_terminal', tool_id: 't2' }});
assert(renders.tool === 1, '场景2: B 的 tool.start 必须渲染（计数=1）');
statusHandler({{ session_id: 'B', text: 'B的状态' }});
assert(renders.status === 1, '场景2: B 的 status.update 必须渲染（计数=1）');

// ── 场景 3：切回 A → A 事件放行；清标记；无 sid 全局事件恒放行 ──
currentSessionId = 'A';
const t3 = runDelta('A', '切回后A的思考');
assert(t3 === '切回后A的思考', '场景3: 切回 A 后 A 的 delta 必须放行渲染');
clearBgActive('A');
assert(bgActiveSids['A'] === undefined, '场景3: clearBgActive 后活跃标记须清除');
// 无 sid 事件（全局事件如 gateway.ready）恒放行
thinkBoxEl = null; thinkText = '';
deltaHandler({{ text: 'no-sid' }});
assert(thinkText === 'no-sid', '场景3: 无 sid 事件视为全局，应放行');

console.log('NODE_F10_DUAL_SESSION_OK');
"""
    return script


def test_f10_2_dual_session_simulation():
    """双会话模拟：A 流不进 B 窗口；B 正常渲染；切回 A 恢复；全局事件放行。"""
    out = _run_node(_f10_node_script())
    assert "NODE_F10_DUAL_SESSION_OK" in out, f"node 实跑失败: {out}"


# ── F10-3：防回归 —— 既有 GUI 闸门不破 ────────────────────────────────

def test_f10_3_existing_gui_gates_intact():
    """F1/F6/F6B/F6C/D1d 既有行为不破（关键锚点仍在）。"""
    src = GUI_FILE.read_text(encoding="utf-8")
    # F1-2 思考剥离
    assert "function splitThinking(s)" in src, "F1-2 splitThinking 不破"
    # F6 思考分段 / F6B 连续合并 / F6C 吞并
    assert "createThinkBox()" in src, "F6 思考框创建不破"
    assert "contains('collapsed')" in src, "F6B 合并判定不破"
    assert "function swallowThinkBox(d)" in src, "F6C 吞并函数不破"
    # D1d ④⑤ Stop 按钮联动：只对 currentSessionId 发 interrupt（现状不动）
    assert "session.interrupt" in src, "D1d session.interrupt 不破"
    assert "session_id: currentSessionId" in src, "Stop 仍只对当前会话发 interrupt"
