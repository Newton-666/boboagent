"""TICKET-GUI-F14 回归测试 — 初始化链解耦（loadSession 不得拖死整链）。

覆盖：
- F14-1 静态守卫（GUI 闸门）：
  * renderPluginList / Plugin 区默认折叠 / refreshCtxStats / loadSlashCatalog
    调用点在代码顺序上先于 loadSession 调用点（解耦，不等会话历史）
  * loadSession 包 try/catch（失败 toast + 空态可发新消息，绝不静默）
  * 15s 超时兜底（Promise.race，LOAD_TIMEOUT_MS = 15000）
  * newChat 分支同样带 withTimeout（不阻塞后续初始化）
  * debug('Ready')/inputEl.focus() 在 if/else 之后无条件执行（无论成败超时）
- F14-2 node 实跑：loadSession 永久 hang → 50ms 快速超时触发 → 四行初始化仍执行、
  失败提示出现（toast/status）、clearChat 空态、renderSessions 侧栏渲染、handler 不 hang 死
- F14-3 node 实跑：loadSession reject → 不静默（toast 含原因）、后续初始化仍执行、
  空态可发新消息、侧栏仍渲染
- F14-4 node 实跑：正常路径回归 → ready 后插件列表 4 项渲染（真实 renderPluginList）、
  药丸刷新触发（refreshCtxStats 被调用）、命令目录加载、无失败提示

注：GUI 渲染层无头全自动化受限，采用静态断言 + node 实跑（与 F10/F13 同款零漂移
验证当前 HTML 内真实函数）。药丸真实百分比渲染由实弹验收（Playwright CDP）覆盖。
"""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GUI_FILE = ROOT / "apps" / "desktop" / "dist" / "index.html"


# ── 辅助：提取当前 HTML 内真实 JS（零漂移，与 F10 同款） ──────────────

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
    """提取 on('<event>', async function(...) { ... }); 的完整块（括号配对到闭合 );）。"""
    pat = re.compile(r"on\('" + re.escape(event) + r"',\s*async\s+function[^)]*\)\s*\{")
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
    """在 node 中执行 JS，返回 stdout（async IIFE 自行 await）。"""
    r = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        raise AssertionError(f"node 执行失败: {r.stderr}")
    return r.stdout


def _node_prelude() -> str:
    """F14 桩：全部符号对应 dist/index.html 真实存在的全局（L14）。"""
    return r"""
// ── F14 桩：事件注册 + 调用记录 ──
var handlers = new Map();
function on(e, h) { handlers.set(e, h); }
var calls = [];
function record(name) { calls.push(name); }
function debug() {}
function setConnected() {}
function hideOverlay() {}
var _ovlType = null;
var _everConnected = null;
var currentSessionId = null;
var sessions = [{ id: 's1', title: 'S1' }];
function showToast(type, msg) { record('toast:' + type + ':' + msg); }
function addStatus(t) { record('status:' + t); }
function clearChat() { record('clearChat'); }
function renderSessions() { record('renderSessions'); }
function renderPluginList() { record('renderPluginList'); }
function refreshCtxStats() { record('refreshCtxStats'); }
function loadSlashCatalog() { record('loadSlashCatalog'); }
var inputEl = { focus: function() { record('inputFocus'); } };
var document = {
  getElementById: function(id) {
    if (id === 'body-plugin' || id === 'arr-plugin') return { classList: { add: function() {} } };
    if (id === 'plugin-list') return pluginListEl;
    return null;
  }
};
"""


def _node_ready_body(behavior: str) -> str:
    """ready 处理器源码（真实提取），LOAD_TIMEOUT 注入 50ms 快速超时，行为由桩控制。"""
    src = GUI_FILE.read_text(encoding="utf-8")
    block = _extract_event_block(src, "gateway.ready")
    # 测试注入：15000ms → 50ms（只动测试侧字符串，生产代码 15s 不变）
    block = block.replace("15000", "50")
    # 会话加载行为桩（由测试场景注入）
    pre = f"""
var LOAD_BEHAVIOR = '{behavior}';
async function loadSessions() {{ record('loadSessions'); }}
function loadSession(sid) {{
  record('loadSession:' + sid);
  if (LOAD_BEHAVIOR === 'hang') return new Promise(function() {{}});       // 永久 pending
  if (LOAD_BEHAVIOR === 'reject') return Promise.reject(new Error('boom')); // 显式失败
  return Promise.resolve({{ session_id: sid, messages: [] }});              // 正常
}}
async function newChat() {{
  record('newChat');
  if (LOAD_BEHAVIOR === 'hang') return new Promise(function() {{}});
  if (LOAD_BEHAVIOR === 'reject') return Promise.reject(new Error('newchat-boom'));
  return Promise.resolve({{ session_id: 'n1' }});
}}
"""
    return pre + block + "\n);"  # _extract_event_block 只到 }，补 on(...) 的闭合 );


# ── F14-1：静态守卫（GUI 闸门） ───────────────────────────────────────

def test_f14_1_ready_init_order():
    """解耦守卫：无依赖初始化必须先于 loadSession 调用（代码顺序）。"""
    src = GUI_FILE.read_text(encoding="utf-8")
    block = _extract_event_block(src, "gateway.ready")
    i_plugin = block.index("renderPluginList()")
    i_ctx = block.index("refreshCtxStats()")
    i_slash = block.index("loadSlashCatalog()")
    i_fold1 = block.index("body-plugin")
    i_fold2 = block.index("arr-plugin")
    i_load = block.index("loadSession(sessions[0].id)")
    for name, i in (("renderPluginList", i_plugin), ("refreshCtxStats", i_ctx),
                    ("loadSlashCatalog", i_slash), ("Plugin 折叠", i_fold1),
                    ("arr-plugin 折叠", i_fold2)):
        assert i < i_load, f"F14: {name} 调用点必须先于 loadSession（解耦不等会话历史）"
    # 四行初始化必须在 try 之前（不被 try/catch 包裹）
    i_try = block.index("try {")
    assert i_plugin < i_try and i_ctx < i_try and i_slash < i_try, \
        "F14: 无依赖初始化必须在 try 块之前（loadSession 成败都不影响）"


def test_f14_1_timeout_and_fallback():
    """兜底守卫：15s 超时 + try/catch + 失败 toast + 空态可发新消息 + newChat 同款。"""
    src = GUI_FILE.read_text(encoding="utf-8")
    block = _extract_event_block(src, "gateway.ready")
    assert "LOAD_TIMEOUT_MS = 15000" in block, "F14: 必须 15s 超时常量"
    assert "Promise.race" in block, "F14: 必须 Promise.race 超时兜底"
    assert "try {" in block and "} catch (e) {" in block, "F14: loadSession 必须包 try/catch"
    assert "showToast('fail', '会话加载失败：' + em" in block, "F14: 失败必须 toast 提示（绝不静默）"
    assert "addStatus('⚠ 加载会话失败：' + em" in block, "F14: 失败必须状态栏提示"
    assert "clearChat()" in block, "F14: 失败必须清聊天区显示空态（可发新消息）"
    assert "withTimeout(newChat(), '新建会话')" in block, "F14: newChat 分支同样必须超时兜底（不阻塞后续）"
    assert "renderSessions()" in block, "F14: 失败路径也必须渲染侧栏会话列表"
    # 无论成功失败超时，收尾初始化必须执行到（debug/inputEl.focus 在 if/else 之后）
    i_debug = block.index("debug('Ready'); inputEl.focus();")
    i_else = block.index("} else {")
    assert i_debug > i_else, "F14: debug('Ready')/inputEl.focus() 必须在 if/else 之后无条件执行"


def test_f14_1_fallback_path_has_init():
    """守卫：readyFallback 路径（gateway.ready 丢失时的兜底接管）同样必须执行四行无依赖初始化——
    否则该路径下插件区空白/药丸恒 0%/命令目录不加载，与 loadSession 拖死同症状（实弹验收实证）。"""
    src = GUI_FILE.read_text(encoding="utf-8")
    m = re.search(r"var readyFallbackTimer = setTimeout\(async function\(\) \{.*?\n\}, 5000\);", src, re.S)
    assert m, "未找到 readyFallback"
    body = m.group(0)
    # 四行初始化在 fallback 接管分支内（setConnected(true) 之后、await loadSessions() 之前）
    i_set = body.index("setConnected(true)")
    i_load = body.index("await loadSessions()")
    for frag in ("renderPluginList()", "refreshCtxStats()", "loadSlashCatalog()",
                 "document.getElementById('body-plugin').classList.add('closed')",
                 "document.getElementById('arr-plugin').classList.add('closed')"):
        i = body.index(frag)
        assert i_set < i < i_load, f"F14: fallback 路径 {frag} 必须在 setConnected 后、loadSessions 前"


# ── F14-2：loadSession 永久 hang → 超时兜底不拖死整链 ────────────────

def test_f14_2_hang_timeout_recovers():
    js = _node_prelude() + _node_ready_body("hang") + r"""
(async function() {
  var handler = handlers.get('gateway.ready');
  await handler();   // 内部 50ms 超时 reject → catch，handler 必须能返回（不 hang 死）
  // 四行无依赖初始化必须已执行（解耦核心：不等 loadSession）
  for (var need of ['renderPluginList', 'refreshCtxStats', 'loadSlashCatalog']) {
    if (calls.indexOf(need) === -1) throw new Error('hang 场景 ' + need + ' 未被调用');
  }
  // 超时视同失败：toast + 状态栏 + 空态 + 侧栏渲染，绝不静默
  var toasts = calls.filter(function(c) { return c.indexOf('toast:fail:') === 0; });
  if (!toasts.length) throw new Error('hang 场景必须出现失败 toast');
  if (toasts[0].indexOf('超时') === -1) throw new Error('hang 场景 toast 必须含超时原因: ' + toasts[0]);
  if (!calls.some(function(c) { return c.indexOf('status:') === 0; })) throw new Error('hang 场景必须状态栏提示');
  if (calls.indexOf('clearChat') === -1) throw new Error('hang 场景必须清聊天区（空态可发新消息）');
  if (calls.indexOf('renderSessions') === -1) throw new Error('hang 场景必须渲染侧栏');
  // 收尾初始化执行到
  if (calls.indexOf('inputFocus') === -1) throw new Error('hang 场景 inputEl.focus 必须执行到');
  console.log('NODE_F14_HANG_OK');
})().catch(function(e) { console.error(e); process.exit(1); });
"""
    out = _run_node(js)
    assert "NODE_F14_HANG_OK" in out, f"node 实跑失败: {out}"


# ── F14-3：loadSession reject → 不静默、后续初始化仍执行 ──────────────

def test_f14_3_reject_not_silent():
    js = _node_prelude() + _node_ready_body("reject") + r"""
(async function() {
  var handler = handlers.get('gateway.ready');
  await handler();
  for (var need of ['renderPluginList', 'refreshCtxStats', 'loadSlashCatalog']) {
    if (calls.indexOf(need) === -1) throw new Error('reject 场景 ' + need + ' 未被调用');
  }
  var toasts = calls.filter(function(c) { return c.indexOf('toast:fail:') === 0; });
  if (!toasts.length) throw new Error('reject 场景必须出现失败 toast');
  if (toasts[0].indexOf('boom') === -1) throw new Error('reject 场景 toast 必须含失败原因: ' + toasts[0]);
  if (calls.indexOf('clearChat') === -1) throw new Error('reject 场景必须清聊天区（空态可发新消息）');
  if (calls.indexOf('renderSessions') === -1) throw new Error('reject 场景必须渲染侧栏');
  console.log('NODE_F14_REJECT_OK');
})().catch(function(e) { console.error(e); process.exit(1); });
"""
    out = _run_node(js)
    assert "NODE_F14_REJECT_OK" in out, f"node 实跑失败: {out}"


# ── F14-4：正常路径回归（真实 renderPluginList 渲染 4 项） ───────────

def test_f14_4_normal_path_renders_plugins():
    src = GUI_FILE.read_text(encoding="utf-8")
    render_plugin = _extract_func(src, "renderPluginList")
    js = _node_prelude() + _node_ready_body("ok") + r"""
// 正常路径：真实 renderPluginList + 4 个插件 + 桩 DOM（L14：全部真实符号）
var pluginListEl = { innerHTML: '', querySelectorAll: function() { return []; } };
var plugins = [
  { id: 'notes', icon: '📝', name: '笔记', desc: 'd1' },
  { id: 'project', icon: '📁', name: '项目', desc: 'd2' },
  { id: 'terminal', icon: '🖥', name: '终端', desc: 'd3' },
  { id: 'telescope', icon: '🔭', name: 'Telescope', desc: 'd4' },
];
""" + render_plugin + r"""
(async function() {
  var handler = handlers.get('gateway.ready');
  await handler();
  // 四行初始化执行
  if (calls.indexOf('refreshCtxStats') === -1) throw new Error('正常路径 refreshCtxStats 未触发（药丸刷新）');
  if (calls.indexOf('loadSlashCatalog') === -1) throw new Error('正常路径 loadSlashCatalog 未触发');
  // 插件列表 4 项真实渲染
  var n = (pluginListEl.innerHTML.match(/class="pitem"/g) || []).length;
  if (n !== 4) throw new Error('插件列表应 4 项，实际 ' + n);
  // loadSession 用首会话 id
  if (calls.indexOf('loadSession:s1') === -1) throw new Error('loadSession 应用首会话 id');
  // 无失败提示（正常路径零 toast:fail）
  if (calls.some(function(c) { return c.indexOf('toast:fail') === 0; }))
    throw new Error('正常路径不应出现失败 toast');
  // 收尾执行到
  if (calls.indexOf('inputFocus') === -1) throw new Error('正常路径 inputEl.focus 必须执行到');
  console.log('NODE_F14_OK_OK');
})().catch(function(e) { console.error(e); process.exit(1); });
"""
    out = _run_node(js)
    assert "NODE_F14_OK_OK" in out, f"node 实跑失败: {out}"
