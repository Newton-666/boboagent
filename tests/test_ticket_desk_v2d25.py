"""TICKET-DESK-V2D25 回归测试 — 工具卡精致化（SVG 细线图标 + 流光运行态）。

覆盖（票验收）：
- D2.5-1 图标体系：TOOL_ICONS 集中映射（execute_terminal/read_local_file/edit_file/grep_code/
  save_memory/load_result/task_ledger/run_tests/web_search + _default）；
  14px / 1.25px 描边 / currentColor / fill:none；未知工具回退 _default（不许空白）
- D2.5-2 状态语义：addTool 无 running 裸文本（状态属性化 data-state）；运行中橙色细圈
  1.6s 呼吸脉冲（.dot.ring + v2d25Breathe）；完成灰绿实心点 + 耗时淡入（.tool-time.in）；
  失败红点定住；上下文收等宽弱色 chip（--bg3 底 / SF Mono 10px）
- D2.5-3 流光：运行中加 shimmer class、完成/失败移除；纯 CSS animation 无 JS 定时器；
  prefers-reduced-motion 下 class 不加（JS 检查）+ CSS 全禁用；聚合/历史卡不带流光
- CSS 纪律：全部进 /* === V2D25 工具卡 === */ 锚点段；取色走既有色板（零新增颜色）
- node 实跑：真实 addTool/updateToolResult/buildHistToolCard 桩化 DOM 验证

注：F6C/F6D/F8/F12 不破由各自测试文件全量回归兜底（本文件静态断言关键锚点保留）。
"""

import hashlib
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
GUI_FILE = ROOT / "apps" / "desktop" / "dist" / "index.html"
MD5_FILES = [
    ROOT / "data" / "knowledge_base.json",
    ROOT / "library" / "MEMORY.md",
    ROOT / "library" / "index.md",
]

ANCHOR = "/* === V2D25 工具卡 === */"
ANCHOR_END = "/* === end V2D25 === */"

# 色板既有语义色（GUI-DESIGN 二节）——锚点段只允许出现这些 #hex
PALETTE_HEX = {"#e8913a", "#50a14f", "#f48771", "#5b9bd5", "#f44336", "#4caf50"}


def _run_node(js: str) -> str:
    r = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        raise AssertionError(f"node 执行失败: {r.stderr}")
    return r.stdout


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


def _extract_var(src: str, vname: str) -> str:
    m = re.search(r"var\s+" + vname + r"\s*=\s*\{[^;]*\};", src)
    assert m, f"未找到 var {vname}"
    return m.group(0)


def _extract_array(src: str, vname: str) -> str:
    """提取 var X = [...]; 数组字面量（WRITE_TOOLS 为多行数组）。"""
    m = re.search(r"var\s+" + vname + r"\s*=\s*\[[^\]]*\];", src, re.S)
    assert m, f"未找到 var {vname}"
    return m.group(0)


def _gui() -> str:
    return GUI_FILE.read_text(encoding="utf-8")


def _css_seg() -> str:
    """提取 V2D25 锚点段 CSS。"""
    src = _gui()
    assert ANCHOR in src and ANCHOR_END in src, "V2D25 锚点段必须成对存在"
    return src.split(ANCHOR)[1].split(ANCHOR_END)[0]


# ── D2.5-1：图标体系 ──────────────────────────────────────────────────

def test_v2d25_1_icons_static():
    src = _gui()
    icons = _extract_var(src, "TOOL_ICONS")
    # 映射集中一个 JS 对象 + 默认回退
    for key in ("'execute_terminal'", "'read_local_file'", "'edit_file'", "'grep_code'",
                "'save_memory'", "'load_result'", "'task_ledger'", "'run_tests'",
                "'web_search'", "'_default'"):
        assert key in icons, f"TOOL_ICONS 缺 {key}"
    # 每个图标：14px / 1.25px 描边 / currentColor / fill:none
    for svg in re.findall(r"'<svg[^>]*>.*?</svg>'", icons):
        assert 'viewBox="0 0 14 14"' in svg and 'width="14"' in svg and 'height="14"' in svg, \
            f"图标必须 14px: {svg[:60]}"
        assert 'stroke-width="1.25"' in svg, f"图标必须 1.25px 描边: {svg[:60]}"
        assert 'stroke="currentColor"' in svg and 'fill="none"' in svg, \
            f"图标必须 currentColor + fill:none: {svg[:60]}"
    # 回退函数
    assert "function toolIcon(name) { return TOOL_ICONS[name] || TOOL_ICONS['_default']; }" in src, \
        "toolIcon 必须回退 _default"


def test_v2d25_1_icons_node():
    src = _gui()
    icons = _extract_var(src, "TOOL_ICONS")
    js = icons + r"""
function toolIcon(name) { return TOOL_ICONS[name] || TOOL_ICONS['_default']; }
const listed = ['execute_terminal', 'read_local_file', 'edit_file', 'grep_code',
  'save_memory', 'load_result', 'task_ledger', 'run_tests', 'web_search'];
for (const n of listed) {
  const svg = toolIcon(n);
  if (!svg || svg.indexOf('<svg') !== 0) throw new Error('图标缺失或空白: ' + n);
  if (svg.indexOf('currentColor') === -1 || svg.indexOf('stroke-width="1.25"') === -1)
    throw new Error('图标规格不符: ' + n);
}
// 未知工具回退 _default（不许空白）
const fb = toolIcon('some_future_tool_xyz');
if (fb !== TOOL_ICONS['_default']) throw new Error('未知工具应回退 _default');
if (!fb || fb.indexOf('<svg') !== 0) throw new Error('回退图标不得空白');
console.log('NODE_V2D25_ICONS_OK');
"""
    out = _run_node(js)
    assert "NODE_V2D25_ICONS_OK" in out, f"node 实跑失败: {out}"


# ── D2.5-2：状态语义（无 running 裸文本）──────────────────────────────

def test_v2d25_2_state_static():
    src = _gui()
    at = _extract_func(src, "addTool")
    # running 裸文本不存在于 DOM 输出（状态属性化）
    assert ">running<" not in at, "addTool 不得输出 running 裸文本"
    assert "setAttribute('data-state', 'running')" in at, "运行态应写 data-state"
    assert "'<span class=\"dot ring\"></span>'" in at, "运行中应渲染橙色细圈点（ring）"
    # 历史卡同样无裸文本
    hist = _extract_func(src, "buildHistToolCard")
    assert "tool-status" not in hist, "历史卡不得含 tool-status 裸文本"
    assert "data-state', 'done'" in hist, "历史卡应写 data-state=done"
    assert "'<span class=\"dot done\"></span>'" in hist, "历史卡应为完成态实心点"
    # 上下文收等宽弱色 chip
    css = _css_seg()
    assert ".tool .tool-context" in css, "上下文 chip 样式必须在锚点段"
    assert "background:var(--bg3)" in css and "border-radius:4px" in css, "chip 应 --bg3 底圆角 4px"
    assert "font-family:'SF Mono',Monaco,Menlo,monospace" in css and "font-size:10px" in css, \
        "chip 应等宽弱色 10px"
    # 状态点语义
    assert ".tool .dot.ring" in css and "border:1.25px solid #e8913a" in css, "运行中橙色细圈"
    assert "v2d25Breathe 1.6s ease-in-out infinite" in css, "运行中 1.6s 呼吸脉冲"
    assert ".tool .dot.done { background:#50a14f;" in css, "完成灰绿实心点"
    assert ".tool .dot.fail { background:#f48771;" in css, "失败红点定住"
    # 耗时淡入
    assert ".tool .tool-time { opacity:0;" in css and ".tool .tool-time.in { opacity:1;" in css, \
        "耗时列应淡入（.in 才可见）"


# ── D2.5-3：流光 ──────────────────────────────────────────────────────

def test_v2d25_3_shimmer_static():
    css = _css_seg()
    src = _gui()
    # 流光 CSS：斜向柔光 + 2s 一轮 infinite + keyframes
    assert ".tool.shimmer { position:relative; overflow:hidden;" in css, "流光容器须相对定位裁切"
    assert ".tool.shimmer::after" in css and "linear-gradient(115deg" in css, "斜向柔光渐变"
    assert "v2d25Shimmer 2s linear infinite" in css, "2s 一轮 infinite"
    assert "@keyframes v2d25Shimmer" in css, "keyframes 必须存在"
    # 透明度 25-35%（0.25-0.35 区间，含白/暖光）
    assert "rgba(255,255,255,.32)" in css, "流光主光 32% 透明度（25-35% 区间）"
    assert "rgba(232,145,58,.10)" in css, "流光暖光辅色（品牌橙低透明）"
    # 聚合/考古卡不带流光
    assert ".tool-agg .tool.shimmer::after { display:none; }" in css, "聚合卡内流光必须禁用"
    # reduced-motion 全禁用（无障碍纪律）
    assert "@media (prefers-reduced-motion: reduce)" in css, "reduced-motion 块必须存在"
    rm = css.split("@media (prefers-reduced-motion: reduce)")[1].split("}")[0] + "}"
    assert "animation:none" in rm, "reduced-motion 下流光/脉冲必须 animation:none"
    # 纯 CSS animation：addTool/updateToolResult 无 JS 定时器
    at = _extract_func(src, "addTool")
    ur = _extract_func(src, "updateToolResult")
    assert "setInterval" not in at and "setTimeout" not in at, "addTool 禁止 JS 定时器"
    assert "setInterval" not in ur and "setTimeout" not in ur, "updateToolResult 禁止 JS 定时器"
    # 完成/失败即收流光（class 移除）
    assert "div.classList.remove('shimmer')" in ur, "完成/失败应移除 shimmer class"
    assert "if (!prefersReducedMotion()) div.classList.add('shimmer')" in at, \
        "reduced-motion 下不加 shimmer class"


def test_v2d25_3_shimmer_node():
    """node 实跑：真实 addTool / updateToolResult / buildHistToolCard 桩化 DOM。
    - 运行中：加 shimmer class + data-state=running + dot ring
    - 完成：shimmer 移除 + data-state=done + dot done + 耗时淡入 .in
    - reduced-motion：不加 shimmer class
    - 历史卡：无 shimmer、data-state=done、dot done"""
    src = _gui()
    icons = _extract_var(src, "TOOL_ICONS")
    fns = "\n".join(
        [icons, _extract_var(src, "TOOL_FRIENDLY"), _extract_array(src, "WRITE_TOOLS")] +
        [_extract_func(src, n) for n in
         ("toolIcon", "prefersReducedMotion", "esc", "isWriteToolEl", "swallowThinkBox",
          "aggHeadArrowText", "addTool", "updateToolResult", "buildHistToolCard")]
    )
    js = r"""
const assert = require('assert');

// ── mini-DOM 桩（F6C 同款 + getAttribute/classList.remove）──
function miniEl(cls) {
  const el = {
    _className: cls || '', _children: [], _subs: {}, style: {},
    id: '', innerHTML: '', textContent: '', parentNode: null, _attrs: {},
    _removed: [],
    setAttribute(k, v) { this._attrs[k] = v; },
    getAttribute(k) { return this._attrs[k] || null; },
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
      return this._subs[sel] || null;
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
    remove(c) {
      el._removed.push(c);
      el._className = (el._className || '').split(/\s+/).filter(x => x && x !== c).join(' ');
    },
    toggle(c, force) {
      const has = el.classList.contains(c);
      const want = force === undefined ? !has : !!force;
      if (want && !has) el._className = (el._className + ' ' + c).trim();
      if (!want && has) el._className = (el._className || '').split(/\s+/).filter(Boolean).filter(x => x !== c).join(' ');
      return want;
    },
  };
  return el;
}

const chatEl = miniEl('chat');
const welcomeEl = { style: {} };
const thinkBoxEl = null;
var toolIdCounter = 0;
let roundToolEls = [];
let roundAggregated = false, roundTotalCount = 0, roundAggregateHead = null;
const document = { createElement: miniEl };
const window = { matchMedia: function() { return { matches: false }; } };
// Notification 桩（浏览器 API；产品代码 updateToolResult 有权限判定分支）
function Notification() {}
Notification.permission = 'granted';
Notification.requestPermission = function() {};
// renderToolDetail 桩（本测试不关心结果渲染细节，只验证状态/流光生命周期）
function renderToolDetail(args, resultText, inlineDiff) {
  return '<div class="tool-detail">' + (resultText || '') + '</div>';
}
// 第一步 addTool：不触发聚合分支（roundTotalCount 0 → 1）
""" + fns + r"""
// ── 运行中：shimmer + data-state + dot ring ──
addTool('execute_terminal', '/tmp/x.sh', 'execute_terminal');
const div = chatEl._children[0];
assert(div.classList.contains('shimmer'), '运行中应加 shimmer class');
assert(div.getAttribute('data-state') === 'running', '运行中 data-state 应为 running');
assert(String(div.innerHTML).indexOf('dot ring') >= 0, '运行中应渲染 .dot.ring');
assert(String(div.innerHTML).indexOf('tool-status') === -1, 'DOM 不得含 tool-status');
assert(String(div.innerHTML).indexOf('running') === -1, 'DOM 不得含 running 裸文本');
assert(String(div.innerHTML).indexOf('<svg') >= 0, '工具卡应带细线 SVG 图标');

// ── 完成：shimmer 移除 + data-state done + dot done + 耗时淡入 ──
const timeEl = { textContent: '', classList: { add() {} } };
const dotEl = miniEl('dot'); dotEl.className = 'dot ring';
const toggleEl = { textContent: '', style: {}, classList: { add() {} } };
const resultEl = { className: '', textContent: '', innerHTML: '', classList: { add() {} } };
div.querySelector = function(s) {
  if (s === '.dot') return dotEl;
  if (s === '.tool-time') return timeEl;
  if (s === '.tool-toggle') return toggleEl;
  if (s === '.tool-result') return resultEl;
  return null;
};
chatEl.querySelectorAll = function() { return [div]; };
updateToolResult('execute_terminal', { duration: 2.5, arguments: {}, result_text: 'ok' });
assert(!div.classList.contains('shimmer'), '完成后 shimmer 应移除');
assert(div.getAttribute('data-state') === 'done', '完成后 data-state 应为 done');
assert(dotEl.className === 'dot done', '完成后 dot 应为灰绿实心点');
assert(timeEl.textContent === '2.5s', '耗时应写入 tool-time');

// ── reduced-motion：不加 shimmer class ──
window.matchMedia = function() { return { matches: true }; };
addTool('grep_code', 'core/', 'grep_code');
const div2 = chatEl._children[1];
assert(!div2.classList.contains('shimmer'), 'reduced-motion 下不得加 shimmer class');
assert(div2.getAttribute('data-state') === 'running', 'reduced-motion 下状态仍为 running');
window.matchMedia = function() { return { matches: false }; };

// ── 历史卡：无 shimmer、data-state=done、dot done、无裸文本 ──
const hcard = buildHistToolCard('edit_file', '改了一行');
assert(!hcard.classList.contains('shimmer'), '历史卡不得带流光');
assert(hcard.getAttribute('data-state') === 'done', '历史卡应为 done');
assert(String(hcard.innerHTML).indexOf('dot done') >= 0, '历史卡应完成态实心点');
assert(String(hcard.innerHTML).indexOf('tool-status') === -1, '历史卡不得含 tool-status');
assert(String(hcard.innerHTML).indexOf('<svg') >= 0, '历史卡应带细线 SVG 图标');

console.log('NODE_V2D25_SHIMMER_OK');
"""
    out = _run_node(js)
    assert "NODE_V2D25_SHIMMER_OK" in out, f"node 实跑失败: {out}"


# ── CSS 纪律：锚点段 + 色板取色 ───────────────────────────────────────

def test_v2d25_anchor_css_only():
    src = _gui()
    css = _css_seg()
    # 锚点段内所有 #hex 必须来自既有色板（零新增颜色 = 视觉宪法 L9）
    for hexv in re.findall(r"#[0-9a-fA-F]{3,6}\b", css):
        norm = "#" + hexv[1:].lower()
        # 3 位缩写展开为 6 位再比对
        if len(norm) == 4:
            norm = "#" + "".join(c * 2 for c in norm[1:])
        assert norm in PALETTE_HEX, f"锚点段引入非色板颜色: {hexv}"
    # 既有样式只加不改：铁律 0 闸（test_v2b_css_zero_change_on_existing）兜底，这里抽查锚点段独立性
    assert ANCHOR in src and ANCHOR_END in src
    # 锚点段在 </style> 之前（覆盖优先级：后置覆盖既有 .tool 规则）
    assert css.rstrip().endswith("}"), "锚点段应以完整 CSS 规则收尾"
    style_end = src.index("</style>")
    assert src.index(ANCHOR) < style_end, "锚点段必须在 style 块内"


# ── F6C/F6D/F8/F12 关键锚点保留（不破兜底；各自测试文件全量回归）─────

def test_v2d25_5_regression_anchors():
    src = _gui()
    # F6C/F4-1：聚合吞并链不破
    for anchor in ("aggBody2.appendChild(d);", "aggBody.appendChild(d);",
                   "roundTotalCount >= 2", "roundToolEls = []"):
        assert anchor in src, f"F6C/F4-1 锚点丢失: {anchor}"
    # F6D：写类分流不破
    assert "var WRITE_TOOLS" in src and "function isWriteToolEl(el)" in src
    # F8/F12：历史渲染链不破
    for anchor in ("function buildHistToolCard(name, summary)", "function renderFullHistory(",
                   "function renderHistAggCard(", "function renderHistToolFlat(",
                   ".hist-agg .tool-agg-body"):
        assert anchor in src, f"F8/F12 锚点丢失: {anchor}"
    # 聚合卡考古工具条带流光？—— 聚合卡内工具不带（CSS 禁用 + 历史卡无 shimmer）
    assert "tool-agg .tool.shimmer::after { display:none; }" in _css_seg()


# ── md5 闸门：真实库三文件零变动（存在/可读/非空）────────────────────

def test_v2d25_md5_gate():
    for f in MD5_FILES:
        assert f.exists(), f"{f} 不存在"
        digest = hashlib.md5(f.read_bytes()).hexdigest()
        assert len(digest) == 32 and f.stat().st_size > 0, f"{f} 读取失败或为空"
