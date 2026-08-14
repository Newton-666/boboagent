"""TICKET-GUI-F6D 回归测试 — 相邻判定跳过状态行 + 写类工具思考不吞并。

覆盖：
- F6D-1 静态断言（GUI 闸门）：
  * WRITE_TOOLS 名单存在且含 edit_file/file_operation（写删）
  * isWriteToolEl 存在并读取 data-tool
  * swallowThinkBox 含写类短路 + contains('status') 跳过
  * message.delta 合并判定含 contains('status') 跳过（F6B 扩展）
  * 建聚合卡分支按 isWriteToolEl 分流（编辑流不建空聚合卡）
  * F6/F6B/F6C 已验收要素不破；无新视觉 class
- F6D-2 node 实跑：
  * 思考-状态行-思考 → 合并为一个思考框（F6B 跳过状态行）
  * 思考-状态行-读类工具 → 思考随工具正常吞并进聚合卡（F6C 跳过状态行）
  * 编辑流（edit_file×2）全程摊开：无聚合卡、思考与编辑卡均留消息流
  * 混合序列（读-写-读-写）：读类吞并进聚合卡，写类思考+卡留消息流

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


# ── 辅助（与 F6B/F6C 同款）──────────────────────────────────────────────

def _extract_func(src: str, fname: str) -> str:
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
    r = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        raise AssertionError(f"node 执行失败: {r.stderr}")
    return r.stdout


def _gui_fns() -> str:
    """提取当前 HTML 真实函数 + WRITE_TOOLS 常量（F6D 桩依赖）。"""
    src = GUI_FILE.read_text(encoding="utf-8")
    wt_m = re.search(r"var WRITE_TOOLS = \[[^\]]*\];", src)
    assert wt_m, "F6D: 需要 var WRITE_TOOLS 名单"
    # F8 配套：TOOL_FRIENDLY 提升为模块级后 addTool 引用它，桩必须带上
    tf_m = re.search(r"var TOOL_FRIENDLY = \{[^;]*\};", src)
    assert tf_m, "F8: 需要 var TOOL_FRIENDLY 映射"
    # V2D25 配套：TOOL_ICONS/toolIcon/prefersReducedMotion（addTool 引用，桩必须带上）
    ic_m = re.search(r"var TOOL_ICONS = \{[^;]*\};", src)
    assert ic_m, "V2D25: 需要 var TOOL_ICONS 映射"
    return "\n".join(
        [tf_m.group(0), ic_m.group(0), wt_m.group(0), _extract_func(src, "isWriteToolEl")] +
        [_extract_func(src, n) for n in ("toolIcon", "prefersReducedMotion", "esc", "addTool", "swallowThinkBox", "aggHeadArrowText")]
    )


# ── F6D-1：静态断言 ─────────────────────────────────────────────────────

def test_f6d_1_static_asserts():
    """两条规则落位：状态行跳过 + 写类名单；F6/F6B/F6C 要素不破。"""
    src = GUI_FILE.read_text(encoding="utf-8")

    # ── 规则 2：写/改类工具名单 ──
    assert "var WRITE_TOOLS" in src, "F6D: 需要写类工具名单"
    assert "'edit_file'" in src and "'file_operation'" in src, \
        "F6D: 名单须含 edit_file / file_operation（写删类）"
    assert "function isWriteToolEl(el)" in src, "F6D: 需要 isWriteToolEl"
    assert "getAttribute('data-tool')" in src, "F6D: 按 data-tool 判定工具类型"
    assert "WRITE_TOOLS.indexOf(name)" in src, "F6D: 名单命中判定"

    # ── 规则 1：swallowThinkBox 跳过状态行 ──
    sw = _extract_func(src, "swallowThinkBox")
    assert "isWriteToolEl(d)" in sw, "F6D: 写类工具思考不吞并（短路 return null）"
    assert "contains('status')" in sw, "F6D: 吞并判定须跳过 status 类节点"
    # F6C 要素保留
    assert "contains('think-box')" in sw and "contains('collapsed')" in sw, \
        "F6C: 只吞已折叠思考框不破"
    assert "contains('tool-agg')" in sw, "F6C: 隔聚合卡向前找档不破"

    # ── 规则 1：message.delta 合并判定跳过状态行 ──
    md = _extract_event_block(src, "message.delta")
    assert "contains('status')" in md, "F6D: 合并判定须跳过 status 类节点"
    # F6B 要素保留
    assert "lastElementChild" in md and "contains('think-box')" in md and \
        "contains('collapsed')" in md, "F6B 合并判定不破"
    assert "createThinkBox()" in md, "F6 分段不破"

    # ── 规则 2：聚合吞并按类型分流 ──
    assert "hasSwallowable" in src, "F6D: 建聚合卡前检查有无可吞元素（编辑流不建空卡）"
    assert "isWriteToolEl(d)) return;" in src, "F6D: 吞并循环跳过写类工具卡"
    # F4-1 / F6C 要素保留
    assert "roundTotalCount >= 2" in src and "roundToolEls = []" in src, "F4-1 不破"
    assert "if (tb2) aggBody2.appendChild(tb2);" in src and \
        "if (tb) aggBody.appendChild(tb);" in src, "F6C 配对思考移入不破"
    assert "aggBody2.appendChild(d);" in src and "aggBody.appendChild(d);" in src, \
        "F6C 工具卡吞并不破"
    # 视觉零新增
    for banned in ("think-agg", "write-tool", "edit-flow"):
        assert banned not in src, f"F6D 不得引入新视觉 class: {banned}"


# ── F6D-2：node 实跑 ────────────────────────────────────────────────────

# mini-DOM 桩（与 F6C 同款，另加 getAttribute 以测写类分流）
_NODE_STUB = r"""
function miniEl(cls) {
  const el = {
    _className: cls || '',
    _children: [], _subs: {}, style: {},
    id: '', innerHTML: '', textContent: '', parentNode: null, _attrs: {},
    setAttribute(k, v) { this._attrs[k] = v; },
    getAttribute(k) { return this._attrs[k] !== undefined ? this._attrs[k] : null; },
    appendChild(ch) {
      if (ch.parentNode) {
        const oldKids = ch.parentNode._children;
        const i = oldKids.indexOf(ch);
        if (i >= 0) oldKids.splice(i, 1);
      }
      ch.parentNode = this;
      this._children.push(ch);
      return ch;
    },
    insertBefore(ch, ref) {
      const i = this._children.indexOf(ref);
      ch.parentNode = this;
      if (i < 0) this._children.push(ch); else this._children.splice(i, 0, ch);
      return ch;
    },
    get previousElementSibling() {
      if (!this.parentNode) return null;
      const kids = this.parentNode._children;
      const i = kids.indexOf(this);
      return i > 0 ? kids[i - 1] : null;
    },
    get lastElementChild() {
      return this._children.length ? this._children[this._children.length - 1] : null;
    },
    querySelector(sel) {
      if (sel === '.tool-agg-head' || sel === '.tool-agg-arrow' || sel === '.tool-agg-body') {
        if (!this._subs[sel]) {
          const sub = miniEl(sel.slice(1));
          sub.parentNode = this;
          this._subs[sel] = sub;
          if (sel === '.tool-agg-body') this._children.push(sub);
        }
        return this._subs[sel];
      }
      if (sel === '.think-text') {
        if (!this._thinkTextEl) this._thinkTextEl = { textContent: this._thinkText || '' };
        return this._thinkTextEl;
      }
      return null;
    },
    querySelectorAll() { return []; },
    onclick: null,
  };
  Object.defineProperty(el, 'className', {
    get() { return el._className; },
    set(v) { el._className = v || ''; },
  });
  el.classList = {
    contains(c) { return (el._className || '').split(/\s+/).filter(Boolean).includes(c); },
    add(c) { if (!el.classList.contains(c)) el._className = (el._className + ' ' + c).trim(); },
    toggle(c, force) {
      const has = el.classList.contains(c);
      if (force === undefined) force = !has;
      if (force && !has) el._className = (el._className + ' ' + c).trim();
      if (!force && has) el._className = el._className.split(/\s+/).filter(x => x && x !== c).join(' ');
      return force;
    },
  };
  return el;
}
"""


def test_f6d_2_think_status_think_merges():
    """思考-状态行-思考 → 合并为一个思考框（F6B 跳过状态行，不新建框）。"""
    src = GUI_FILE.read_text(encoding="utf-8")
    block = _extract_event_block(src, "message.delta")
    handler = re.sub(
        r"^on\('message\.delta',\s*function",
        "deltaHandler = function",
        block,
    )
    js = _NODE_STUB + f"""
const assert = require('assert');
let thinkBoxEl = null;
let thinkText = '';
let created = 0;
const chatEl = miniEl('chat');
chatEl.scrollTop = 0; chatEl.scrollHeight = 0;
function collapsedThinkBox(text) {{
  const el = miniEl('think-box collapsed');
  el._thinkText = text;
  return el;
}}
function statusLine(text) {{
  const el = miniEl('status');
  el.textContent = text;
  return el;
}}
function createThinkBox() {{
  created++;
  const el = miniEl('think-box show');
  el._thinkText = '';
  return el;
}}
// TICKET-GUI-F10 兼容桩：真实 delta 块首行 isForeignSession 闸门（F10 新增），
// 本测试全部调用均不带 session_id（无 sid 恒放行），放行桩与真实语义等价（闸门语义由 test_f10_1 守住）
let currentSessionId = null;
function markBgActive() {{}}
function isForeignSession(data) {{
  var sid = data && data.session_id;
  if (!sid || sid === currentSessionId) return false;
  markBgActive(sid);
  return true;
}}

{handler}

// 场景：思考1 → 状态行 → 新思考 → 应合并进思考1（跳过状态行），不新建
const tb1 = collapsedThinkBox('思考一');
chatEl.appendChild(tb1);
const st = statusLine('AUTO MODE 已开启');
chatEl.appendChild(st);
thinkBoxEl = null; thinkText = ''; created = 0;
deltaHandler({{ text: '思考二' }});
assert(created === 0, '思考-状态行-思考 不应新建框: created=' + created);
assert(thinkBoxEl === tb1, '应复用状态行前的折叠思考框');
assert(thinkText === '思考一\\n思考二', '合并衔接: ' + JSON.stringify(thinkText));

// 连续多状态行同样跳过
chatEl.appendChild(statusLine('加载 12 个工具'));
chatEl.appendChild(statusLine('会话已恢复'));
thinkBoxEl = null; thinkText = ''; created = 0;
deltaHandler({{ text: '思考三' }});
assert(created === 0, '多状态行后仍应合并: created=' + created);
assert(thinkText === '思考一\\n思考二\\n思考三', '多状态行跳过合并: ' + JSON.stringify(thinkText));

console.log('NODE_F6D_THINK_STATUS_THINK_OK');
"""
    out = _run_node(js)
    assert "NODE_F6D_THINK_STATUS_THINK_OK" in out, f"node 实跑失败: {out}"


def test_f6d_2_think_status_tool_swallow():
    """思考-状态行-读类工具 → 思考随工具吞并进聚合卡（F6C 跳过状态行）。"""
    js = _NODE_STUB + f"""
const assert = require('assert');
const chatEl = miniEl('chat');
chatEl.scrollTop = 0; chatEl.scrollHeight = 0;
const welcomeEl = miniEl('welcome');
let thinkBoxEl = null;
let toolIdCounter = 0;
let roundToolEls = [], roundAggregated = false, roundTotalCount = 0, roundAggregateHead = null;
const document = {{ createElement: (tag) => miniEl(tag) }};

{_gui_fns()}

function thinkBox(text) {{
  const el = miniEl('think-box collapsed');
  el._thinkText = text;
  return el;
}}
function statusLine(text) {{
  const el = miniEl('status');
  el.textContent = text;
  return el;
}}
function maxConsecThink(el) {{
  let run = 0, best = 0;
  for (const c of el._children) {{
    if (c.classList.contains('think-box')) {{ run++; best = Math.max(best, run); }}
    else run = 0;
  }}
  return best;
}}
function kidsOf(el) {{
  // V2D25 演进：工具卡 className 含 'shimmer' 附加 token，按 'tool' token 判定
  return el._children.map(c => c.classList.contains('think-box') ? 'think:' + (c._thinkText || '') : (c.classList.contains('tool') ? 'tool' : c.className));
}}

// 思考1 → 状态行 → 读类工具1 → 状态行 → 思考2 → 读类工具2 → 思考3 → 读类工具3
chatEl.appendChild(thinkBox('思考1'));
chatEl.appendChild(statusLine('AUTO MODE 已开启'));
addTool('read_local_file', '', 'read_local_file');  // 第 1 步（读类；建卡时跳过状态行吞思考1）
chatEl.appendChild(statusLine('加载 12 个工具'));
chatEl.appendChild(thinkBox('思考2'));
addTool('grep_code', '', 'grep_code');              // 第 2 步（读类；最新一步摊开）
chatEl.appendChild(thinkBox('思考3'));
addTool('list_directory', '', 'list_directory');    // 第 3 步（读类；触发吞并第 2 步）

// 目标态：[聚合卡(思考1+工具1, 思考2+工具2)] + 最新 思考3+工具3 摊开；无思考墙；状态行保留原地
assert(maxConsecThink(chatEl) <= 1, '无思考墙');
const kids = chatEl._children;
const agg = kids.find(c => c.className === 'tool-agg');
assert(agg, '应建聚合卡');
const aggBody = agg.querySelector('.tool-agg-body');
const order = aggBody._children.map(c => c._thinkText || (c.classList.contains('tool') ? 'tool' : c.className));
assert(JSON.stringify(order) === JSON.stringify(["思考1", "tool", "思考2", "tool"]),
  '聚合卡体应含 思考1→工具1→思考2→工具2: ' + JSON.stringify(order));
// 状态行仍在消息流（位置与显示不动）
assert(kids.some(c => c.className === 'status'), '状态行应保留在消息流');
// 最新一步摊开（F4-1：聚合卡 + 最新思考 + 最新工具）
assert(kids.some(c => c.classList.contains('think-box') && c._thinkText === '思考3'), '思考3 应摊开');
assert(kids.some(c => c.getAttribute('data-tool') === 'list_directory'), '工具3 应摊开');

console.log('NODE_F6D_THINK_STATUS_TOOL_OK');
"""
    out = _run_node(js)
    assert "NODE_F6D_THINK_STATUS_TOOL_OK" in out, f"node 实跑失败: {out}"


def test_f6d_2_edit_flow_stays_open():
    """编辑流（edit_file×2）全程摊开：无聚合卡、思考与编辑卡均留消息流。"""
    js = _NODE_STUB + f"""
const assert = require('assert');
const chatEl = miniEl('chat');
chatEl.scrollTop = 0; chatEl.scrollHeight = 0;
const welcomeEl = miniEl('welcome');
let thinkBoxEl = null;
let toolIdCounter = 0;
let roundToolEls = [], roundAggregated = false, roundTotalCount = 0, roundAggregateHead = null;
const document = {{ createElement: (tag) => miniEl(tag) }};

{_gui_fns()}

function thinkBox(text) {{
  const el = miniEl('think-box collapsed');
  el._thinkText = text;
  return el;
}}
function kidsOf(el) {{
  // V2D25 演进：工具卡 className 含 'shimmer' 附加 token，按 'tool' token 判定
  return el._children.map(c => c.classList.contains('think-box') ? 'think:' + (c._thinkText || '') : (c.classList.contains('tool') ? 'tool' : c.className));
}}

// 编辑流：思考1+edit_file → 思考2+edit_file → 思考3+file_operation
chatEl.appendChild(thinkBox('思考1'));
addTool('edit_file', '', 'edit_file');
chatEl.appendChild(thinkBox('思考2'));
addTool('edit_file', '', 'edit_file');
chatEl.appendChild(thinkBox('思考3'));
addTool('file_operation', '', 'file_operation');

// 无聚合卡（编辑流不建空聚合卡）
assert(chatEl._children.every(c => c.className !== 'tool-agg'), '编辑流不得出现聚合卡');
// 全部思考框 + 编辑卡留在消息流（全程摊开）
const classes = kidsOf(chatEl);
assert(classes.filter(c => c.startsWith('think:')).length === 3, '3 个思考框都摊开: ' + JSON.stringify(classes));
assert(classes.filter(c => c === 'tool').length === 3, '3 张编辑卡都摊开: ' + JSON.stringify(classes));

console.log('NODE_F6D_EDIT_FLOW_OK');
"""
    out = _run_node(js)
    assert "NODE_F6D_EDIT_FLOW_OK" in out, f"node 实跑失败: {out}"


def test_f6d_2_mixed_sequence():
    """混合序列（读-写-读-写）：读类吞并进聚合卡，写类思考+卡留消息流。"""
    js = _NODE_STUB + f"""
const assert = require('assert');
const chatEl = miniEl('chat');
chatEl.scrollTop = 0; chatEl.scrollHeight = 0;
const welcomeEl = miniEl('welcome');
let thinkBoxEl = null;
let toolIdCounter = 0;
let roundToolEls = [], roundAggregated = false, roundTotalCount = 0, roundAggregateHead = null;
const document = {{ createElement: (tag) => miniEl(tag) }};

{_gui_fns()}

function thinkBox(text) {{
  const el = miniEl('think-box collapsed');
  el._thinkText = text;
  return el;
}}
function kidsOf(el) {{
  // V2D25 演进：工具卡 className 含 'shimmer' 附加 token，按 'tool' token 判定
  return el._children.map(c => c.classList.contains('think-box') ? 'think:' + (c._thinkText || '') : (c.classList.contains('tool') ? 'tool' : c.className));
}}
function toolName(el) {{
  return el.getAttribute('data-tool') || '';
}}

// 读 → 写 → 读 → 写
chatEl.appendChild(thinkBox('思考1'));
addTool('read_local_file', '', 'read_local_file');  // 1 读（被吞）
chatEl.appendChild(thinkBox('思考2'));
addTool('edit_file', '', 'edit_file');              // 2 写（摊开）
chatEl.appendChild(thinkBox('思考3'));
addTool('grep_code', '', 'grep_code');              // 3 读（被吞）
chatEl.appendChild(thinkBox('思考4'));
addTool('file_operation', '', 'file_operation');    // 4 写（摊开）

const kids = chatEl._children;
// 聚合卡存在且含 读类1+读类3（配对思考一并入卡）
const agg = kids.find(c => c.className === 'tool-agg');
assert(agg, '应有聚合卡');
const aggBody = agg.querySelector('.tool-agg-body');
const inAgg = aggBody._children.map(c => (c._thinkText ? 'think:' + c._thinkText : toolName(c)));
const inAggStr = JSON.stringify(inAgg);
assert(inAggStr.includes('"think:思考1"') && inAggStr.includes('"read_local_file"'), '读1+思考1 入卡: ' + inAggStr);
assert(inAggStr.includes('"think:思考3"') && inAggStr.includes('"grep_code"'), '读3+思考3 入卡: ' + inAggStr);
assert(!inAggStr.includes('edit_file') && !inAggStr.includes('file_operation'), '写类不得入卡: ' + inAggStr);
// 写类思考+卡留消息流
const msgs = kidsOf(chatEl);
assert(msgs.includes('think:思考2') && msgs.includes('think:思考4'), '写类思考摊开: ' + JSON.stringify(msgs));
const openTools = kids.filter(c => c.classList.contains('tool')).map(toolName);
assert(openTools.includes('edit_file') && openTools.includes('file_operation'),
  '写类编辑卡摊开: ' + JSON.stringify(openTools));

console.log('NODE_F6D_MIXED_OK');
"""
    out = _run_node(js)
    assert "NODE_F6D_MIXED_OK" in out, f"node 实跑失败: {out}"
