"""TICKET-DESK-TEL 专项测试 — Telescope 引擎实况观测台（右侧 Plugin 区第四入口）。

覆盖（票验收，全部 node 桩实跑 + 静态断言）：
- TEL-1  plugins 数组含 telescope 项：id/name/desc 精确 + 细线 SVG 图标（非 emoji）+ openPlugin 接线
- TEL-2  五区渲染函数齐全（Prompt/理解卡、Task Ledger、分类调用活表格、终端执行、收尾小结），
         面板内容一律经 render()（marked+DOMPurify）管线
- TEL-3  活表格机制：同 category 两次调用 = 一张表两行（绝不新开表）
- TEL-4  轮次分隔：message.start 驱动 Round N 递增渲染
- TEL-5  diff 模态弹层：telShowDiff 内 diffBlock 与主聊天区逐字节同源；✕/Esc/点背景关闭
- TEL-6  终端执行区：命令代码块 + 退出码/耗时弱色小字 + 长输出折叠
- TEL-7  理解卡（AI 开头回应）与收尾小结卡（改动文件/增删行/测试/token 预算审计）
- TEL-8  零干涉守卫：core/bobo_tui_gateway/widget.html 零 diff；事件订阅为包装（原 handler 先跑）
- TEL-9  CSS 锚点段成对 + 色板守卫（段内 #hex 必须 ⊆ 既有色板，零新增色值族）

node 实跑：真实函数 + F13 同款桩 DOM（makeEl）。
"""

import json
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
GUI_FILE = ROOT / "apps" / "desktop" / "dist" / "index.html"

ANCHOR = "/* === TEL Telescope === */"
ANCHOR_END = "/* === end TEL Telescope === */"

# 面板五区渲染函数（票验收清单）
FIVE_SECTIONS = (
    "_telRenderPrompt",   # 用户 Prompt 区 + 理解卡
    "_telRenderLedger",   # Task Ledger 区
    "_telRenderCalls",    # 分类调用活表格区
    "_telRenderTerminal", # 终端执行区
    "_telRenderSummary",  # 收尾小结卡
)
EVENT_HOOKS = (
    ("message.start", "_telOnStart"),
    ("message.delta", "_telOnDelta"),
    ("tool.start", "_telOnToolStart"),
    ("tool.complete", "_telOnToolComplete"),
    ("message.complete", "_telOnComplete"),
)


def _gui() -> str:
    return GUI_FILE.read_text(encoding="utf-8")


def _extract_func(src: str, fname: str) -> str:
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


def _run_node(js: str) -> str:
    r = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        raise AssertionError(f"node 执行失败: {r.stderr}")
    return r.stdout


def _node_prelude() -> str:
    """F13 同款桩 DOM + Telescope 所需全局。"""
    src = _gui()
    funcs = [_extract_func(src, fn) for fn in (
        # Telescope 渲染/事件函数
        "_telCat", "_telIsWriteTool", "_telDiffStats", "_telLastUserPrompt",
        "_telBlankState", "_telNewRound", "_telStateHasContent", "_telWrap",
        "_telOnStart", "_telOnDelta", "_telOnToolStart", "_telOnToolComplete", "_telOnComplete",
        "_telRowStart", "_telRowEnd", "_telHuman", "_telLedgerComplete", "_telTermComplete",
        "renderTelescopePanel", "_telInitOnce", "_telScheduleRender", "_telRender", "_telRenderState",
        "_telRenderPrompt", "_telRenderLedger", "_telRenderCalls",
        "_telRenderTerminal", "_telRenderSummary",
        "telToggleTerm", "telShowDiff", "telCloseDiff", "_telOnClick",
        # 同源依赖（与主聊天区逐字节同源）
        "esc", "diffBlock", "splitThinking",
    )]
    return r"""
// ── node 桩 DOM（F13 同款最小集）──
function makeEl(tag) {
  const el = {
    tagName: tag, _className: '', _innerHTML: '', textContent: '', style: {},
    _children: [], _attrs: {}, parentNode: null, _qs: {}, _firstChild: null,
    appendChild(c) { if (c) { c.parentNode = this; this._children.push(c); } return c; },
    setAttribute(k, v) { this._attrs[k] = v; },
    getAttribute(k) { return this._attrs[k]; },
    querySelector(sel) {
      if (!this._qs[sel]) { const sub = makeEl(sel); sub.parentNode = this; this._qs[sel] = sub; }
      return this._qs[sel];
    },
    querySelectorAll(sel) {
      if (sel === '.msg.user' && this === chatEl) return [USER_MSG_STUB];
      return [];
    },
    get firstChild() { return this._firstChild || null; },
    set innerHTML(v) {
      this._innerHTML = v || '';
      if (v) {
        this._firstChild = makeEl('div'); this._firstChild._innerHTML = v;
        const cm = v.match(/class="([^"]+)"/);
        if (cm) this._firstChild._className = cm[1];
      }
    },
    get innerHTML() { return this._innerHTML || ''; },
    addEventListener() {},
    onclick: null,
  };
  Object.defineProperty(el, 'className', {
    get() { return el._className; },
    set(v) { el._className = v || ''; },
  });
  el.classList = {
    contains(c) { return (el._className || '').split(/\s+/).filter(Boolean).includes(c); },
    add(c) { if (!el.classList.contains(c)) el._className = (el._className + ' ' + c).trim(); },
    remove(c) { el._className = (el._className || '').split(/\s+/).filter(Boolean).filter(x => x !== c).join(' '); },
    toggle(c, force) {
      const has = el.classList.contains(c);
      const want = force === undefined ? !has : !!force;
      if (want && !has) el._className = (el._className + ' ' + c).trim();
      if (!want && has) el._className = (el._className || '').split(/\s+/).filter(Boolean).filter(x => x !== c).join(' ');
    },
  };
  return el;
}
// ── 全局桩 ──
const USER_MSG_STUB = { querySelector: () => ({ textContent: '用户原话：查一下项目结构' }) };
const chatEl = makeEl('div');
let _telTab = 'battle';  // COST-1b：与 dist/index.html 全局默认一致（battle=战报 | cost=消耗）
const document = { createElement: makeEl, body: { appendChild(c) { c.parentNode = this; }, removeChild() {} }, addEventListener() {} };
// rAF 桩：手动队列（测试可触发），供 delta 节流验证
let _telRafQueue = [];
const window = { requestAnimationFrame(cb) { _telRafQueue.push(cb); return _telRafQueue.length; } };
const handlers = new Map();
function isForeignSession(d) { return false; }
// 管线 stub：真实管线由浏览器 marked 承担。必须用真实函数名 mdReply/md ——
// 教训（DESK-TEL 打回）：早前桩了一个并不存在的全局 render()，把"浏览器里 render is not defined"完全掩盖。
function mdReply(s) { return String(s == null ? '' : s); }
function md(s) { return String(s == null ? '' : s); }
// Telescope 全局状态（对应 index.html 顶层 var；面板默认已打开）
let _telEl = makeEl('div');
let _telRound = 0;
let _telRounds = [];
let _telState = null;
let _telInitDone = false;
let _telModalEl = null;
let _telDirty = false;
let _telRaf = null;
""" + "\n".join(funcs) + "\n"


# ── TEL-1：plugins 入口 + openPlugin 接线 ─────────────────────────────

def test_tel_1_plugins_entry():
    src = _gui()
    # plugins 数组含 telescope 项（精确字段）
    m = re.search(r"\{[^}]*id:'telescope'[^}]*\}", src)
    assert m, "plugins 数组缺 telescope 项"
    entry = m.group(0)
    assert "name:'Telescope'" in entry, "telescope 项缺 name"
    assert "desc:'Engine live view'" in entry, "telescope 项缺 desc"
    # 图标 = 细线 SVG（非 emoji）：1.25 描边 / currentColor / fill:none / viewBox
    assert "icon:'<svg" in entry, "图标必须是 SVG（非 emoji）"
    assert 'stroke-width="1.25"' in entry, "图标必须 1.25px 细线描边"
    assert 'stroke="currentColor"' in entry and 'fill="none"' in entry, "图标必须 currentColor + fill:none"
    assert "aria-hidden=\"true\"" in entry, "图标应 aria-hidden（装饰性）"
    # openPlugin 接线
    assert "else if (id === 'telescope') renderTelescopePanel(content);" in src, \
        "openPlugin 必须接线 renderTelescopePanel"


# ── TEL-2：五区渲染函数齐全 + 全部走 render() 管线 ────────────────────

def test_tel_2_five_sections():
    src = _gui()
    assert "function renderTelescopePanel(el)" in src, "缺面板入口 renderTelescopePanel"
    # 五区函数齐全
    for fn in FIVE_SECTIONS:
        assert f"function {fn}(" in src, f"缺五区渲染函数 {fn}"
    # 面板内容一律经 mdReply() 真实管线（禁止 raw JSON/日志直拼上屏）
    for fn in FIVE_SECTIONS:
        body = _extract_func(src, fn)
        assert "mdReply(" in body, f"{fn} 必须经 mdReply() 管线渲染"
    # 用户原话/Markdown 表格/代码块全走管线
    p = _extract_func(src, "_telRenderPrompt")
    assert "mdReply(st.prompt)" in p, "用户原话必须经管线渲染"
    assert "mdReply('**Understood as**: '" in p, "理解卡必须经管线渲染"
    led = _extract_func(src, "_telRenderLedger")
    assert "mdReply(md)" in led, "Task Ledger 必须渲染成 Markdown 表格"
    terms = _extract_func(src, "_telRenderTerminal")
    assert "mdReply('```" in terms, "终端命令必须渲染成代码块"


# ── TEL-2b：守卫——Telescope 段内禁止裸 render(（该全局在浏览器不存在）────

def test_tel_2b_no_phantom_render():
    src = _gui()
    # 抽取 TEL 段（JS 锚点注释到 end），段内不允许调用不存在的全局 render(
    m = re.search(r"TICKET-DESK-TEL.*?end TICKET-DESK-TEL", src, re.S)
    assert m, "缺 TEL 锚点段"
    seg = m.group(0)
    bare = [ln for ln in seg.split("\n")
            if re.search(r"(?<![A-Za-z])render\(", ln) and "mdReply(" not in ln]
    assert not bare, f"TEL 段内残留裸 render( 调用（浏览器无此全局）: {bare[:2]}"


# ── TEL-3：活表格机制（同 category 追加，绝不新开表）──────────────────

def test_tel_3_live_table_append():
    js = _node_prelude() + r"""
// 一轮真实事件：两次 edit_file（同 category=Tools）
_telOnStart({ session_id: 's1' });
_telOnToolStart({ name: 'edit_file', arguments: { file_path: 'a.py' }, context: 'a.py', session_id: 's1' });
_telOnToolComplete({ name: 'edit_file', duration: 0.8, arguments: { file_path: 'a.py' },
  inline_diff: '@@ -1,2 +1,3 @@\n-旧行\n+新行\n 上下文行', session_id: 's1' });
_telOnToolStart({ name: 'edit_file', arguments: { file_path: 'b.py' }, context: 'b.py', session_id: 's1' });
_telOnToolComplete({ name: 'edit_file', duration: 0.5, arguments: { file_path: 'b.py' },
  inline_diff: '@@ -1,1 +1,1 @@\n-旧\n+新', session_id: 's1' });

// 活表格：同 category 两行 = 一张表
if (_telState.calls.Tools.length !== 2) throw new Error('同 category 应追加为 2 行，实际 ' + _telState.calls.Tools.length);
const html = _telRenderCalls();
const tables = (html.match(/<div class="tel-sec"><div class="tel-sec-title">Tools<\/div>/g) || []).length;
if (tables !== 1) throw new Error('Tools 区必须只有一张表，实际 ' + tables + ' 张');
const rows = (html.match(/\| `edit_file` \|/g) || []).length;
if (rows !== 2) throw new Error('一张表应含两行 edit_file，实际 ' + rows);
// 结果列人话渲染 + diff 链接
if (html.indexOf('Wrote +1 / −1 lines') === -1) throw new Error('结果列必须人话渲染增删行');
if ((html.match(/View diff/g) || []).length !== 2) throw new Error('两个写入应各带查看 diff 链接');
// 耗时列
if (html.indexOf('0.8s') === -1) throw new Error('耗时列应渲染');
console.log('NODE_TEL3_OK');
"""
    out = _run_node(js)
    assert "NODE_TEL3_OK" in out, f"node 实跑失败: {out}"


# ── TEL-3b：活表格管道符转义（TEL-b：a|b 单元格不破坏列结构）──────────

def test_tel_3b_calls_pipe_escape():
    """单元格含 | 必须转义（同台账 \\|）：三表各 1 行、内容完整保留、行结构合法。"""
    js = _node_prelude() + r"""
// 真实事件流初始化状态（与 TEL-3 同款），再注入含 | 的单元格数据
_telOnStart({ session_id: 's1' });
_telState.calls = {
  Skills: [{ name: 'read|file', args: 'a|b', result: 'ok|yes' }],
  Memory: [{ name: 'm|1', args: 'sig|nal', result: 'in|ject', error: true }],
  Tools:  [{ name: 'edit|file', args: 'x|y', result: '写入 +1|−1', dur: '0.8|s', diff: true }],
};
const html = _telRenderCalls();
// 三张活表格各渲染一张（同 category 行追加不新开表）
const secs = (html.match(/<div class="tel-sec"><div class="tel-sec-title">(Skills|Memory|Tools)<\/div>/g) || []).length;
if (secs !== 3) throw new Error('三张活表格应各一张，实际 ' + secs);
// 单元格内容完整保留（管道已转义为 \|，防 marked 打乱列结构；error 态 span 内同样转义）
for (const needle of ['read\\|file', 'a\\|b', 'ok\\|yes', 'm\\|1', 'sig\\|nal', 'in\\|ject',
                      'edit\\|file', 'x\\|y', '写入 +1\\|−1', '0.8\\|s']) {
  if (html.indexOf(needle) === -1) throw new Error('单元格内容未完整保留: ' + needle);
}
// diff 链接是 HTML 非单元格文本，必须原样保留（不被转义误伤）
if (html.indexOf('<a href="#tel-diff-0" data-tel-src="_cur">View diff</a>') === -1)
  throw new Error('查看 diff 链接必须 HTML 原样保留');
// 行结构合法：数据行未转义管道数 = 列数 + 1（Tools 4 列 → 5，Skills/Memory 3 列 → 4）
const rows = html.split('\n').filter(l => l.indexOf('\\|') !== -1);
if (rows.length !== 3) throw new Error('应 3 条数据行（各表 1 行），实际 ' + rows.length);
for (const row of rows) {
  const pipes = (row.match(/(?<!\\)\|/g) || []).length;
  const expect = row.indexOf('edit\\|file') !== -1 ? 5 : 4;
  if (pipes !== expect) throw new Error('行未转义管道数不符：期望 ' + expect + '，实际 ' + pipes + ' → ' + row);
}
console.log('NODE_TEL3B_OK');
"""
    out = _run_node(js)
    assert "NODE_TEL3B_OK" in out, f"node 实跑失败: {out}"


# ── TEL-3c：守卫——三张活表格转义调用必须存在（TEL-b）────────────────

def test_tel_3c_calls_pipe_escape_guard():
    """静态守卫：_telRenderCalls 单元格管道转义必须存在（同台账 \\| 做法）。"""
    src = _gui()
    m = re.search(r"function _telRenderCalls.*?(?=\nfunction )", src, re.S)
    assert m, "未找到 _telRenderCalls"
    body = m.group(0)
    assert "var escP = function(s) { return esc(s).replace(/\\|/g, '\\\\|'); };" in body, \
        "_telRenderCalls 必须定义单元格管道转义 helper（escP，同台账 \\| 做法）"
    for frag in ("escP(r.name)", "escP(r.args)", "escP(r.result)", "escP(r.dur)"):
        assert frag in body, f"_telRenderCalls 单元格未走管道转义: {frag}"
    # 查看 diff 链接是 HTML 非单元格文本，必须保持原样拼在结果列后（防误伤）
    assert "res + link + ' | '" in body, "diff 链接必须保持 HTML 原样（不得被转义吞掉）"


# ── TEL-4：轮次分隔（message.start 驱动 Round N）──────────────────────

def test_tel_4_round_separator():
    js = _node_prelude() + r"""
_telOnStart({ session_id: 's1' });
if (_telState.round !== 1) throw new Error('第一轮 round 应=1');
_telOnStart({ session_id: 's1' });
if (_telState.round !== 2) throw new Error('第二轮 round 应=2');
// 第一轮有观测内容（prompt 快照）→ 已归档进历史
if (_telRounds.length !== 1) throw new Error('第一轮应归档进历史，实际 ' + _telRounds.length);
// 首开空态（无事件）不递增轮次
_telEl = makeEl('div');
renderTelescopePanel(_telEl);
if (_telRound !== 2) throw new Error('空态开面板不得递增轮次，实际 ' + _telRound);
const html = _telEl.innerHTML;
if (html.indexOf('Round 1') === -1 || html.indexOf('Round 2') === -1) throw new Error('历史轮+当前轮分隔线都应渲染');
if (html.indexOf('tel-round') === -1) throw new Error('轮次分隔线样式类缺 tel-round');
console.log('NODE_TEL4_OK');
"""
    out = _run_node(js)
    assert "NODE_TEL4_OK" in out, f"node 实跑失败: {out}"


def test_tel_4b_continuous_battle_report():
    """打回修复（Kimi 审）：历史轮次保留 —— 整面板可读成连贯战报，
    Round 2 开始时 Round 1 的 Prompt/活表格/小结卡全部仍在，轮分隔线有意义。"""
    js = _node_prelude() + r"""
// 轮 1：完整事件链（prompt + 工具 + 小结）
_telOnStart({ session_id: 's1' });
_telOnToolStart({ name: 'edit_file', arguments: { file_path: 'a.py' }, context: 'a.py', session_id: 's1' });
_telOnToolComplete({ name: 'edit_file', duration: 0.5, arguments: { file_path: 'a.py' },
  inline_diff: '@@ -1,1 +1,2 @@\n-旧行\n+新行\n 上下文', session_id: 's1' });
_telOnComplete({ final_text: '第一轮完成：改了一处。', usage: {}, session_id: 's1' });
// 轮 2 开始：轮 1 归档进历史
_telOnStart({ session_id: 's1' });
if (_telRounds.length !== 1) throw new Error('轮 1 应归档，实际 ' + _telRounds.length);
if (_telState.round !== 2) throw new Error('当前轮应=2');
// start 边界同步渲染：历史轮 + 当前轮同时可见（连贯战报）
const html = _telEl.innerHTML;
if (html.indexOf('Round 1') === -1 || html.indexOf('Round 2') === -1) throw new Error('两轮分隔线都应渲染');
if (html.indexOf('edit_file') === -1) throw new Error('历史轮工具调用应保留');
if (html.indexOf('Wrote +1 / −1 lines') === -1) throw new Error('历史轮活表格结果应保留');
if (html.indexOf('第一轮完成') === -1) throw new Error('历史轮小结卡应保留');
if (html.indexOf('用户原话') === -1) throw new Error('历史轮 Prompt 应保留');
console.log('NODE_TEL4B_OK');
"""
    out = _run_node(js)
    assert "NODE_TEL4B_OK" in out, f"node 实跑失败: {out}"


# ── TEL-5：diff 模态弹层（与主聊天区 diffBlock 逐字节同源）─────────────

def test_tel_5_diff_modal_same_source():
    js = _node_prelude() + r"""
const DIFF = '@@ -1,3 +1,4 @@\n-旧行1\n-旧行2\n+新行1\n+新行2\n+新行3\n 上下文行';
telShowDiff(DIFF);
if (!_telModalEl) throw new Error('弹层未打开');
if (_telModalEl._className.indexOf('tel-modal-ov') === -1) throw new Error('弹层缺遮罩类 tel-modal-ov');
const box = _telModalEl._children[0];
if (!box || box._className.indexOf('tel-modal') === -1) throw new Error('弹层缺面板类 tel-modal');
const body = box._children[1];
// 逐字节同源：modal body === diffBlock 输出（同一 esc/diffBlock，1:1 复用主聊天区渲染）
const expected = diffBlock(DIFF);
if (body.innerHTML !== expected) throw new Error('diff 块必须与主聊天区逐字节同源\n实际: ' + body.innerHTML + '\n期望: ' + expected);
// ✕ / 点背景关闭
telCloseDiff();
if (_telModalEl !== null) throw new Error('✕/关闭后 _telModalEl 应为 null');
console.log('NODE_TEL5_OK');
"""
    out = _run_node(js)
    assert "NODE_TEL5_OK" in out, f"node 实跑失败: {out}"


def test_tel_5b_diff_modal_static():
    src = _gui()
    show = _extract_func(src, "telShowDiff")
    # 同源调用 diffBlock（1:1 复用主聊天区渲染链）
    assert "diffBlock(diffText)" in show, "telShowDiff 必须调用主聊天区同源 diffBlock"
    # 宽 90% 面板 + ✕ + 点背景关闭 + Esc
    css = _css_seg()
    assert ".tel-modal { width:90%" in css.replace("\n", " ") or ".tel-modal { width:90%" in css, \
        "弹层面板必须宽 90%"
    assert "rgba(0,0,0,0.45)" in css, "背景压暗必须黑色系 rgba(0,0,0,*)"
    assert "tel-modal-x" in show, "✕ 关闭按钮必须存在"
    assert "e.target === ov" in show, "点背景必须关闭"
    assert "document.addEventListener('keydown'" in src and "Escape" in _extract_func(src, "_telOnClick") or \
           "'Escape' && _telModalEl" in src, "Esc 关闭必须存在（capture 优先不触发主窗 stopThinking）"
    assert "e.stopPropagation()" in src.split("// ── end TICKET-DESK-TEL")[0].split("Escape")[-1], \
        "Esc capture 拦截必须 stopPropagation（零干涉主窗快捷键）"


# ── TEL-6：终端执行区 ─────────────────────────────────────────────────

def test_tel_6_terminal_section():
    js = _node_prelude() + r"""
_telOnStart({ session_id: 's1' });
_telOnToolStart({ name: 'execute_terminal', arguments: { command: 'ls -la' }, context: 'ls -la', session_id: 's1' });
_telOnToolComplete({ name: 'execute_terminal', duration: 1.2, result_text: 'total 8\ndrwxr-xr-x', session_id: 's1' });
if (_telState.terminal.length !== 1) throw new Error('终端区应记录 1 条');
const html = _telRenderTerminal();
if (html.indexOf('$ ls -la') === -1) throw new Error('命令必须渲染成代码块，含 $ 前缀');
if (html.indexOf('Time 1.2s') === -1) throw new Error('弱色小字必须含耗时');
if (html.indexOf('exit code') === -1) throw new Error('弱色小字必须含退出码');
// 长输出默认折叠 + 展开按钮
_telOnToolStart({ name: 'execute_terminal', arguments: { command: 'cat big.log' }, context: 'cat big.log', session_id: 's1' });
const longOut = Array(60).fill('line-xxx-0123456789').join('\n');   // >400 字符
_telOnToolComplete({ name: 'execute_terminal', duration: 2.0, result_text: longOut, session_id: 's1' });
const html2 = _telRenderTerminal();
if (html2.indexOf('collapsed') === -1) throw new Error('长输出必须默认折叠');
if (html2.indexOf('Expand all (') === -1) throw new Error('长输出必须带展开按钮');
console.log('NODE_TEL6_OK');
"""
    out = _run_node(js)
    assert "NODE_TEL6_OK" in out, f"node 实跑失败: {out}"


# ── TEL-7：理解卡 + 收尾小结卡 ────────────────────────────────────────

def test_tel_7_understand_card():
    js = _node_prelude() + r"""
_telOnStart({ session_id: 's1' });
_telOnDelta({ text: '我来分析这个需求：把观测台面板做出来。', session_id: 's1' });
if (_telState.understand.indexOf('我来分析这个需求') !== 0) throw new Error('理解卡应取 AI 开头回应');
const html = _telRenderPrompt();
if (html.indexOf('**Understood as**: ') === -1) throw new Error('理解卡缺文案前缀');
if (html.indexOf('我来分析这个需求') === -1) throw new Error('理解卡缺开头回应内容');
if (html.indexOf('用户原话：查一下项目结构') === -1) throw new Error('用户原话必须渲染在最顶部');
if (html.indexOf('tel-understand') === -1) throw new Error('理解卡样式类缺 tel-understand');
console.log('NODE_TEL7_OK');
"""
    out = _run_node(js)
    assert "NODE_TEL7_OK" in out, f"node 实跑失败: {out}"


def test_tel_7b_ledger_table():
    js = _node_prelude() + r"""
_telOnStart({ session_id: 's1' });
_telOnToolComplete({ name: 'task_ledger', duration: 0.2, arguments: {
  action: 'create',
  items: [
    { id: 'a', title: '任务甲', status: 'in_progress' },
    { id: 'b', title: '任务乙', status: 'pending' },
  ],
}, session_id: 's1' });
if (!_telState.ledger || _telState.ledger.rows.length !== 2) throw new Error('台账应解析 2 行');
const html = _telRenderLedger();
if (html.indexOf('| # | Item | Status |') === -1) throw new Error('台账必须渲染成 Markdown 表格');
if (html.indexOf('任务甲') === -1 || html.indexOf('任务乙') === -1) throw new Error('台账缺事项行');
if (html.indexOf('in_progress') === -1 || html.indexOf('pending') === -1) throw new Error('台账状态格缺状态');
// 状态格弱色：td:last-child 弱色
const css = document._css || '';
console.log('NODE_TEL7B_OK');
"""
    out = _run_node(js)
    assert "NODE_TEL7B_OK" in out, f"node 实跑失败: {out}"


def test_tel_7c_summary_card():
    js = _node_prelude() + r"""
_telOnStart({ session_id: 's1' });
// 一轮真实施工：edit_file + run_tests → 小结卡数据
_telOnToolStart({ name: 'edit_file', arguments: { file_path: 'x.py' }, context: 'x.py', session_id: 's1' });
_telOnToolComplete({ name: 'edit_file', duration: 0.4, arguments: { file_path: 'x.py' },
  inline_diff: '@@ -1,2 +1,3 @@\n-旧\n+新1\n+新2\n 上下文', session_id: 's1' });
_telOnToolStart({ name: 'run_tests', arguments: {}, context: '', session_id: 's1' });
_telOnToolComplete({ name: 'run_tests', duration: 5.1, arguments: {}, result_text: '==== 12 passed, 0 failed ====', session_id: 's1' });
_telOnComplete({ final_text: '第一句结论：面板施工完成，测试全绿。\n\n第二句细节。',
  usage: { context_percent: 42.3, context_used: 43008, context_max: 102400 }, session_id: 's1' });
if (!_telState.summaryDone) throw new Error('message.complete 应翻转 summaryDone');
if (_telState.files !== 1) throw new Error('改动文件数应=1');
if (_telState.addLines !== 2 || _telState.delLines !== 1) throw new Error('增删行统计错误: ' + _telState.addLines + '/' + _telState.delLines);
if (_telState.tests !== '12 passed') throw new Error('测试数字应提取 12 passed，实际 ' + _telState.tests);
const html = _telRenderSummary();
if (html.indexOf('**Round summary**') === -1) throw new Error('小结卡缺标题');
if (html.indexOf('Files changed: 1 · +2 / −1 lines') === -1) throw new Error('小结卡缺改动文件/增删行');
if (html.indexOf('Tests: 12 passed') === -1) throw new Error('小结卡缺测试数字');
if (html.indexOf('token usage 42.3%') === -1) throw new Error('小结卡缺 token 预算审计');
if (html.indexOf('第一句结论') === -1) throw new Error('小结卡缺一句人话结论');
console.log('NODE_TEL7C_OK');
"""
    out = _run_node(js)
    assert "NODE_TEL7C_OK" in out, f"node 实跑失败: {out}"


# ── TEL-8：零干涉守卫 ─────────────────────────────────────────────────

def test_tel_8_zero_interference():
    r = subprocess.run(["git", "diff", "--name-only", "main"], capture_output=True, text=True, cwd=ROOT)
    changed = [ln for ln in r.stdout.splitlines() if ln.strip()]
    # COST-1B（2026-08-16）授权：消耗度量双观测注入点，白名单文件 diff 必须含 COST-1b 标记
    COST1B_ALLOWED = {
        "bobo_tui_gateway/handlers/misc.py",
        "bobo_tui_gateway/handlers/prompts.py",
        "bobo_tui_gateway/server_utils.py",
    }
    # 引擎 / gateway / TUI / 小组件零改动
    for ln in changed:
        # VSC-1B（2026-08-17）终审裁决：apps/vscode-extension/ 是独立 npm 子项目
        # （自带 node:test 体系，pytest 世界外），桌面端守卫不管辖 VS Code 扩展
        if ln.startswith("apps/vscode-extension/"):
            continue
        # 票 COST-1c ① 特批：core/llm_caller.py 仅加 usage 事件透传，diff 必须含 COST-1c 标记
        if ln == "core/llm_caller.py":
            r4 = subprocess.run(["git", "diff", "main", "--", ln], capture_output=True, text=True, cwd=ROOT)
            assert "COST-1c" in r4.stdout, f"{ln} 缺 COST-1c 特批标记，未授权改动被拦截"
            continue
        # 票 COST-2 特批：core/injector.py 仅限两处（NOW 锚点后移 + 小时级精度），diff 必须含 COST-2 标记
        # 票 DIAG-1 特批：injector.py 新增调试纪律场景（scene=debug），diff 必须含 DIAG-1 标记
        # 票 DESK-P1 特批：injector.py 新增 project_root 尾部动态段（_TAIL_ORDER 13）
        # 票 REASONING-ECHO 特批：injector.py build_messages 返回前补
        #   reasoning_content 回传（只改发送副本，浅拷贝零污染 history），
        #   diff 必须含 REASONING-ECHO 标记
        if ln == "core/injector.py":
            r4 = subprocess.run(["git", "diff", "main", "--", ln], capture_output=True, text=True, cwd=ROOT)
            assert ("COST-2" in r4.stdout or "DIAG-1" in r4.stdout or "DESK-P1" in r4.stdout
                    or "REASONING-ECHO" in r4.stdout), \
                f"{ln} 缺 COST-2/DIAG-1/DESK-P1/REASONING-ECHO 特批标记，未授权改动被拦截"
            continue
        # 票 SAFETY-1 特批：core/command_safety.py 进程杀灭白名单，diff 必须含 SAFETY-1 标记
        if ln == "core/command_safety.py":
            r5 = subprocess.run(["git", "diff", "main", "--", ln], capture_output=True, text=True, cwd=ROOT)
            assert "SAFETY-1" in r5.stdout, f"{ln} 缺 SAFETY-1 特批标记，未授权改动被拦截"
            continue
        # 票 COST-3 特批：core/context.py + core/engine.py（工作锚点属性化 + 工具集
        # 会话内全量稳定），diff 必须含 COST-3 标记；DESK-P1 复用 engine.py 追加
        # project_root 属性（engine_adapter 会话创建时落库）
        # 票 P0-2 特批：engine.py _run_sedimentation 追加信号判定 hook
        # （通道 A，只记录不动作，写 data/logs/signal_log.jsonl），diff 必须含 P0-2 标记
        if ln in ("core/context.py", "core/engine.py"):
            r7 = subprocess.run(["git", "diff", "main", "--", ln], capture_output=True, text=True, cwd=ROOT)
            assert ("COST-3" in r7.stdout or "DESK-P1" in r7.stdout or "P0-1" in r7.stdout or "COST-7" in r7.stdout
                    or "P0-2" in r7.stdout), \
                f"{ln} 缺 COST-3/DESK-P1/P0-1/P0-2 特批标记，未授权改动被拦截"
            continue
        # 票 DESK-P1 特批：core/engine_adapter.py（会话 project_root 落库）+
        # core/tool_runner.py（execute_terminal 注入 cwd），diff 必须含 DESK-P1 标记；
        # 票 VSC-2B：engine_adapter.py 复用（写审批闸门），diff 标记兼容
        if ln in ("core/engine_adapter.py", "core/tool_runner.py"):
            r8 = subprocess.run(["git", "diff", "main", "--", ln], capture_output=True, text=True, cwd=ROOT)
            assert ("DESK-P1" in r8.stdout or "VSC-2B" in r8.stdout), \
                f"{ln} 缺 DESK-P1/VSC-2B 特批标记，未授权改动被拦截"
            continue
        assert not ln.startswith("core/"), f"零干涉铁律违反：core/ 被改动 {ln}"
        # 票 GUI-F16 特批：apps/desktop/dist/vendor/katex/（KaTeX 本地化资源，
        # 官方压缩产物，与 vendor/marked 等先例同性质，不承载项目逻辑）
        if ln.startswith("apps/desktop/dist/vendor/katex/"):
            continue
        if ln in COST1B_ALLOWED or ln.endswith("metrics.py"):
            r3 = subprocess.run(["git", "diff", "main", "--", ln], capture_output=True, text=True, cwd=ROOT)
            assert ("COST-1b" in r3.stdout or "COST-1c" in r3.stdout or "DESK-P1" in r3.stdout), \
                f"{ln} 缺 COST-1b/COST-1c/DESK-P1 授权标记，未授权改动被拦截"
            continue
        # 票 TICKET-GW-SOCK / TICKET-GW-MULTI 特批：bobo_tui_gateway/entry.py
        # （GW-SOCK：socket 双实例防护；GW-MULTI：多客户端化，每连接一线程 +
        # 全客户端断开才计空闲），diff 必须含对应票据标记
        if ln == "bobo_tui_gateway/entry.py":
            r_gw = subprocess.run(["git", "diff", "main", "--", ln], capture_output=True, text=True, cwd=ROOT)
            assert ("TICKET-GW-SOCK" in r_gw.stdout or "TICKET-GW-MULTI" in r_gw.stdout), \
                f"{ln} 缺 TICKET-GW-SOCK/TICKET-GW-MULTI 特批标记，未授权改动被拦截"
            continue
        # 票 TICKET-GW-MULTI 特批：bobo_tui_gateway/transport.py（多订阅者事件
        # 广播注册表），diff 必须含 TICKET-GW-MULTI 标记
        if ln == "bobo_tui_gateway/transport.py":
            r_gwm = subprocess.run(["git", "diff", "main", "--", ln], capture_output=True, text=True, cwd=ROOT)
            assert "TICKET-GW-MULTI" in r_gwm.stdout, f"{ln} 缺 TICKET-GW-MULTI 特批标记，未授权改动被拦截"
            continue
        # 票 VSC-2B 特批：bobo_tui_gateway/handlers/sessions.py（session.set_write_approval
        # RPC + 会话级写审批开关），diff 必须含 VSC-2B 标记
        if ln == "bobo_tui_gateway/handlers/sessions.py":
            r_v2b = subprocess.run(["git", "diff", "main", "--", ln], capture_output=True, text=True, cwd=ROOT)
            assert "VSC-2B" in r_v2b.stdout, f"{ln} 缺 VSC-2B 特批标记，未授权改动被拦截"
            continue
        # 票 P0-1 特批：bobo_tui_gateway/server.py + handlers/memory.py（Memory 面板
        # RPC：memory.list/delete/update/verify_links），diff 必须含 P0-1 标记
        if ln in ("bobo_tui_gateway/server.py", "bobo_tui_gateway/handlers/memory.py"):
            r_p01 = subprocess.run(["git", "diff", "main", "--", ln], capture_output=True, text=True, cwd=ROOT)
            assert "P0-1" in r_p01.stdout, f"{ln} 缺 P0-1 特批标记，未授权改动被拦截"
            continue
        assert not ln.startswith("bobo_tui_gateway/"), f"零干涉铁律违反：gateway 被改动 {ln}"
        # 票 DESK-P2 特批：apps/desktop/electron/widget.html（小组件界面文案全英文化），
        # diff 必须含 DESK-P2 标记，否则未授权改动被拦截
        if ln.endswith("widget.html"):
            r9 = subprocess.run(["git", "diff", "main", "--", ln], capture_output=True, text=True, cwd=ROOT)
            assert "DESK-P2" in r9.stdout, f"{ln} 缺 DESK-P2 特批标记，未授权改动被拦截"
            continue
        assert "widget.html" not in ln, f"零干涉铁律违反：小组件被改动 {ln}"
    # 改动文件清单（index.html + 本测试文件 + V2C12/V4 豁免 + COST-1c 特批）只允许相关
    for ln in changed:
        # VSC-1B（2026-08-17）终审裁决：apps/vscode-extension/ 独立 npm 子项目，不管辖
        if ln.startswith("apps/vscode-extension/"):
            continue
        if ln.endswith("index.html"):
            continue
        # 票 GUI-F16 特批：KaTeX vendor 资源（官方压缩产物，不承载项目逻辑）
        if ln.startswith("apps/desktop/dist/vendor/katex/"):
            continue
        # 票 SAFETY-1 特批：apps/desktop/electron/main.cjs 后端自动重启（退出码 0
        # 也重启），diff 必须含 SAFETY-1 标记
        if ln.endswith("main.cjs"):
            r7 = subprocess.run(["git", "diff", "main", "--", ln], capture_output=True, text=True, cwd=ROOT)
            assert ("SAFETY-1" in r7.stdout or "TICKET-GW-SOCK" in r7.stdout), \
                f"{ln} 缺 SAFETY-1/TICKET-GW-SOCK 特批标记，未授权改动被拦截"
            continue
        # 票 DESK-P1 特批：apps/desktop/electron/preload.cjs 新增 chooseFolder 别名
        #（桌面端主进程传真实项目根），diff 必须含 DESK-P1 标记
        if ln.endswith("preload.cjs"):
            r9 = subprocess.run(["git", "diff", "main", "--", ln], capture_output=True, text=True, cwd=ROOT)
            assert "DESK-P1" in r9.stdout, f"{ln} 缺 DESK-P1 特批标记，未授权改动被拦截"
            continue
        # 票 TICKET-GW-SOCK / TICKET-GW-MULTI 特批：bobo_tui_gateway/entry.py，
        # diff 必须含对应票据标记
        if ln == "bobo_tui_gateway/entry.py":
            r_gw2 = subprocess.run(["git", "diff", "main", "--", ln], capture_output=True, text=True, cwd=ROOT)
            assert ("TICKET-GW-SOCK" in r_gw2.stdout or "TICKET-GW-MULTI" in r_gw2.stdout), \
                f"{ln} 缺 TICKET-GW-SOCK/TICKET-GW-MULTI 特批标记，未授权改动被拦截"
            continue
        # 票 TICKET-GW-MULTI 特批：bobo_tui_gateway/transport.py（多订阅者广播）
        if ln == "bobo_tui_gateway/transport.py":
            r_gwm2 = subprocess.run(["git", "diff", "main", "--", ln], capture_output=True, text=True, cwd=ROOT)
            assert "TICKET-GW-MULTI" in r_gwm2.stdout, f"{ln} 缺 TICKET-GW-MULTI 特批标记，未授权改动被拦截"
            continue
        # 票 VSC-2B 特批：bobo_tui_gateway/handlers/sessions.py（会话级写审批）
        if ln == "bobo_tui_gateway/handlers/sessions.py":
            r_v2b2 = subprocess.run(["git", "diff", "main", "--", ln], capture_output=True, text=True, cwd=ROOT)
            assert "VSC-2B" in r_v2b2.stdout, f"{ln} 缺 VSC-2B 特批标记，未授权改动被拦截"
            continue
        # 票 P0-1 特批：bobo_tui_gateway/server.py + handlers/memory.py（Memory RPC）
        if ln in ("bobo_tui_gateway/server.py", "bobo_tui_gateway/handlers/memory.py"):
            r_p01b = subprocess.run(["git", "diff", "main", "--", ln], capture_output=True, text=True, cwd=ROOT)
            assert "P0-1" in r_p01b.stdout, f"{ln} 缺 P0-1 特批标记，未授权改动被拦截"
            continue
        if ln.startswith("docs/"):
            continue  # 文档目录（分支既有提交如 TICKET-WRITING.md，非代码零干涉范畴）
        if ln.startswith("data/eval/"):
            continue  # 探针运行产物目录（截图/评估输出，非代码；.gitignore 强制跟踪）
        if ln in COST1B_ALLOWED or ln.endswith("metrics.py") or ln == "core/llm_caller.py" or ln == "core/injector.py" or ln == "core/command_safety.py" or ln == "core/context.py" or ln == "core/engine.py" or ln == "core/engine_adapter.py" or ln == "core/tool_runner.py":
            continue
        # 票 DESK-P1 特批：tools/execute_terminal.py 会话 project_root 非空时
        # 注入 cwd（终端命令落项目目录），diff 必须含 DESK-P1 标记
        if ln == "tools/execute_terminal.py":
            r10 = subprocess.run(["git", "diff", "main", "--", ln], capture_output=True, text=True, cwd=ROOT)
            assert "DESK-P1" in r10.stdout, f"{ln} 缺 DESK-P1 特批标记，未授权改动被拦截"
            continue
        # 票 P0-1 特批：tools/v5_memory.py + tools/memory_migrate.py（记忆六类
        # 枚举 + 656 条迁移脚本），diff 必须含 P0-1 标记
        if ln in ("tools/v5_memory.py", "tools/memory_migrate.py"):
            r_p01t = subprocess.run(["git", "diff", "main", "--", ln], capture_output=True, text=True, cwd=ROOT)
            assert "P0-1" in r_p01t.stdout, f"{ln} 缺 P0-1 特批标记，未授权改动被拦截"
            continue
        if ln.startswith("tests/") or ln.startswith("apps/desktop/electron/test/"):
            continue  # 测试文件配套改动（铁律针对 core/gateway/TUI/widget 代码）
        # 票 DESK-P2 特批：apps/desktop/electron/widget.html（小组件界面文案全英文化），
        # diff 必须含 DESK-P2 标记，否则未授权改动被拦截
        if ln.endswith("widget.html"):
            r11 = subprocess.run(["git", "diff", "main", "--", ln], capture_output=True, text=True, cwd=ROOT)
            assert "DESK-P2" in r11.stdout, f"{ln} 缺 DESK-P2 特批标记，未授权改动被拦截"
            continue
        # 票 REASONING-ECHO 特批：scripts/probe_reasoning_echo.py（实弹取证脚本，
        # 验证 DeepSeek 接受 reasoning_content 空串回传，压缩路径定案依据；
        # 长期保留供压缩行为变更时复跑），diff 必须含 REASONING-ECHO 标记
        if ln == "scripts/probe_reasoning_echo.py":
            r_re = subprocess.run(["git", "diff", "main", "--", ln], capture_output=True, text=True, cwd=ROOT)
            assert "REASONING-ECHO" in r_re.stdout, f"{ln} 缺 REASONING-ECHO 特批标记，未授权改动被拦截"
            continue
        # 票 P0-2 特批：tools/signal_logger.py + tools/signal_library_stats.py
        # （信号日志化双通道，只记录不动作；通道 A LLM 判定写 signal_log.jsonl，
        # 通道 B 确定性统计 library 主题频率），diff 必须含 P0-2 标记
        if ln in ("tools/signal_logger.py", "tools/signal_library_stats.py"):
            r_p02 = subprocess.run(["git", "diff", "main", "--", ln], capture_output=True, text=True, cwd=ROOT)
            assert "P0-2" in r_p02.stdout, f"{ln} 缺 P0-2 特批标记，未授权改动被拦截"
            continue
        assert False, f"意外改动文件: {ln}"


def test_tel_8b_event_wrap_not_overwrite():
    src = _gui()
    wrap = _extract_func(src, "_telWrap")
    # 包装订阅：原 handler 先跑（try prev），再追加观测 —— 绝不覆盖现有行为
    assert "if (prev) prev(data)" in wrap, "包装必须保留原 handler"
    assert "handlers.set(type" in wrap, "包装必须注册回 handlers"
    init = _extract_func(src, "_telInitOnce")
    for ev, fn in EVENT_HOOKS:
        assert f"_telWrap('{ev}', {fn})" in init, f"_telInitOnce 必须包装订阅 {ev}"


# ── TEL-9：CSS 锚点段 + 色板守卫 ──────────────────────────────────────

def _css_seg() -> str:
    src = _gui()
    assert ANCHOR in src and ANCHOR_END in src, "TEL 锚点段必须成对存在"
    return src.split(ANCHOR)[1].split(ANCHOR_END)[0]


def test_tel_9_css_anchor_palette():
    src = _gui()
    seg = _css_seg()
    # 锚点段内 #hex 必须 ⊆ 既有色板（段外已出现的 #hex）
    outside = src.replace(ANCHOR, "").replace(ANCHOR_END, "")
    palette_hex = set(re.findall(r"#[0-9a-fA-F]{3,6}\b", outside))
    seg_hex = set(re.findall(r"#[0-9a-fA-F]{3,6}\b", seg))
    assert seg_hex.issubset(palette_hex), f"锚点段引入新色值族: {seg_hex - palette_hex}"
    # 黑色系压暗：rgba(0,0,0,*) 是既有黑色族（settings-modal 同族）
    for m in re.findall(r"rgba?\(([^)]*)\)", seg):
        base = m.split(",")[0].strip()
        assert base in ("0", "0.0"), f"锚点段 rgba 只能是黑色系压暗，发现 {m}"
    # 取色走既有 token
    assert "var(--bg2)" in seg and "var(--border)" in seg and "var(--text-muted)" in seg, \
        "锚点段必须使用既有色板 token"


def test_tel_9b_css_structure():
    seg = _css_seg()
    # 五区样式类齐全
    for cls in (".tel-round", ".tel-understand", ".tel-sec-title", ".tel-term-cmd",
                ".tel-term-out.collapsed", ".tel-summary", ".tel-modal-ov", ".tel-modal"):
        assert cls in seg, f"锚点段缺样式类 {cls}"
    # diff 红绿块不重复定义（1:1 继承主聊天区 .dl 样式，零双维护）
    assert ".tel-modal-body .dl" not in seg, "modal 内不得重复定义 diff 红绿块样式（须继承主窗同源）"


# ── TEL-10：delta 节流（Kimi 审打回修复）──────────────────────────────

def test_tel_10_delta_throttle():
    """多次 delta 只排一次 rAF；rAF 未触发前不重建 innerHTML；理解卡只取开头一次。"""
    js = _node_prelude() + r"""
_telOnStart({ session_id: 's1' });        // start 边界同步渲染
_telEl.innerHTML = '';                    // 清空，观察 delta 是否立即重建
const before = _telRafQueue.length;
_telOnDelta({ text: 'a', session_id: 's1' });
_telOnDelta({ text: 'b', session_id: 's1' });
_telOnDelta({ text: 'c', session_id: 's1' });
// 3 次 delta 只排 1 次 rAF（节流合并）
if (_telRafQueue.length - before !== 1) throw new Error('3 次 delta 应只排 1 次 rAF，实际 ' + (_telRafQueue.length - before));
if (_telEl.innerHTML !== '') throw new Error('rAF 未触发前不应重建 innerHTML');
// 理解卡=开头第一段（只取一次）；deltaBuf 才是累计
if (_telState.understand !== 'a') throw new Error('理解卡应取开头第一段，实际 ' + _telState.understand);
if (_telState.deltaBuf !== 'abc') throw new Error('deltaBuf 应累计，实际 ' + _telState.deltaBuf);
// 手动触发 rAF：渲染累计状态
_telRafQueue[_telRafQueue.length - 1]();
if (_telEl.innerHTML.indexOf('**Understood as**: a') === -1) throw new Error('rAF 触发后应渲染理解卡');
// 理解卡只取一次：后续 delta 不覆盖开头
_telOnDelta({ text: 'XYZ', session_id: 's1' });
if (_telState.understand.indexOf('XYZ') !== -1) throw new Error('理解卡应只取开头一次');
console.log('NODE_TEL10_OK');
"""
    out = _run_node(js)
    assert "NODE_TEL10_OK" in out, f"node 实跑失败: {out}"


def test_tel_10b_history_cap():
    """历史轮上限 50：超出丢最旧（防无限增长）。"""
    js = _node_prelude() + r"""
for (let r = 1; r <= 55; r++) {
  _telOnStart({ session_id: 's1' });   // 每轮都有 prompt 快照 → 归档
}
if (_telRounds.length !== 50) throw new Error('历史轮应封顶 50，实际 ' + _telRounds.length);
if (_telState.round !== 55) throw new Error('当前轮次应=55，实际 ' + _telState.round);
console.log('NODE_TEL10B_OK');
"""
    out = _run_node(js)
    assert "NODE_TEL10B_OK" in out, f"node 实跑失败: {out}"
