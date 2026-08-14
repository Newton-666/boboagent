"""TICKET-GUI-F12 回归测试 — 历史重放工具链聚合渲染（owner 2026-08-14 方案）。

根因：index.html 历史渲染 role==='tool' 分支只在 inline_diff 存在时
renderHistToolDiff，普通工具调用全丢 → 历史重放看不到工具动作。

修法（owner 定调两条）：
1. 过往回合的"思考→工具×N"链收进聚合卡（复用 F6C .tool-agg 组件，考古模式）
2. 最新一轮完整展开（历史末尾最近一条 assistant 消息对应的工具链逐个平铺）
3. inline_diff 红绿块语义不变（聚合卡考古内照常渲染）

覆盖（票验收）：
- F12-1 静态断言：renderFullHistory 含最新一轮预扫描 + 聚合分支；
  renderHistAggCard / renderHistToolFlat 存在；CSS 锚点段 /* === F12 历史聚合 === */；
  F8 字面（thinking 平铺 / diff 渲染）保留；取色走色板（无新增颜色 token）
- F12-2 node 实跑：构造"思考+3 工具+正文"×3 回合 transcript 重放（提取真实
  renderFullHistory + renderHistAggCard + renderHistToolFlat 等，桩化 DOM）：
  * 前两回合各成一张聚合卡（.hist-agg）
  * 最后一回合（最新一轮）工具卡平铺 + diff 块仍在
- F12-3 后端无关（GUI 纯前端票，无 Python 后端改动）
"""

import json
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
GUI_FILE = ROOT / "apps" / "desktop" / "dist" / "index.html"


def _extract_func(src: str, fname: str) -> str:
    """按 { } 括号配对提取 function <fname> 的完整源码（含 async 前缀）。"""
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


def _run_node(js: str) -> str:
    r = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        raise AssertionError(f"node 执行失败: {r.stderr}")
    return r.stdout


# ── F12-1：静态断言 ───────────────────────────────────────────────────

def test_f12_1_static_asserts():
    """现行页面含 F12 聚合渲染要素；F8 字面保留；取色走色板。"""
    src = GUI_FILE.read_text(encoding="utf-8")

    full = _extract_func(src, "renderFullHistory")

    # 最新一轮预扫描（最后一条 assistant 消息起点）
    assert "histLatestStart" in full, "缺最新一轮起点预扫描"
    assert "msgs[hi].role === 'assistant'" in full, "预扫描应按 assistant 定位"

    # 聚合缓冲 + flush
    assert "aggThink" in full and "aggTools" in full, "缺聚合缓冲"
    assert "renderHistAggCard(aggThink, aggTools)" in full, "缺聚合卡渲染调用"

    # 最新一轮平铺分支：带 diff 保留 F8 字面；无 diff 走 renderHistToolFlat
    assert "if (m.inline_diff) renderHistToolDiff" in full, \
        "F8 字面（diff 渲染）必须保留"
    assert "renderHistToolFlat(m.name || 'tool', m.content || '')" in full, \
        "最新一轮无 diff 工具应平铺渲染"

    # F8 字面：最新一轮思考平铺保留
    assert "if (m.thinking) addHistThinking(m.thinking)" in full, \
        "F8 字面（thinking 平铺）必须保留"

    # 新函数存在
    assert "function renderHistAggCard" in src, "缺历史聚合卡函数"
    assert "function renderHistToolFlat" in src, "缺最新一轮无 diff 平铺函数"

    # 聚合卡复用 F6C 组件：.tool-agg 头 + body + 展开/收起箭头
    agg = _extract_func(src, "renderHistAggCard")
    assert "tool-agg hist-agg" in agg, "聚合卡应复用 .tool-agg 组件"
    assert "tool-agg-head" in agg and "tool-agg-body" in agg
    # 审查修复：思考框/工具卡构造抽公用函数（buildHistThinkBox 内含折叠样式）
    assert "buildHistThinkBox(thinkText)" in agg, "考古内思考框应复用 buildHistThinkBox"
    assert "buildHistToolCard(name" in agg, "考古内工具卡应复用 buildHistToolCard"
    # 审查修复（问题1）：onclick guard 补 .think-box/.diff-block —— 点思考框不误收卡
    assert "closest('.tool') || e.target.closest('.think-box') || e.target.closest('.diff-block')" in agg, \
        "聚合卡 onclick guard 必须含 .think-box/.diff-block"
    # 审查修复（问题2）：空链不丢思考 —— flushHistAgg 空 aggTools 时 aggThink 落 addHistThinking
    assert "if (aggThink) addHistThinking(aggThink)" in full, "空链 aggThink 应落 addHistThinking"
    # 审查修复（问题3）：user 分支重置 histLatest（孤儿 tool 跨 user 不误判最新轮）
    assert "histLatest = false" in full, "user 分支必须重置 histLatest"
    # 审查修复（问题4）：scrollTop 统一到 renderFullHistory 末尾滚一次
    assert "flushHistAgg();" in full and "chatEl.scrollTop = chatEl.scrollHeight;" in full, \
        "renderFullHistory 末尾应有统一 scrollTop"
    assert "function buildHistThinkBox" in src, "缺公用思考框构造函数"
    assert "function buildHistToolCard" in src, "缺公用工具卡构造函数"
    hist_think = _extract_func(src, "addHistThinking")
    assert "buildHistThinkBox(thinkingText)" in hist_think, "addHistThinking 应复用 buildHistThinkBox"

    # 红绿块语义不变：聚合卡考古内也挂 diffBlock（F3-5 语义）
    assert "diffBlock(inlineDiff)" in agg, "聚合卡考古内 diff 块必须保留"

    # CSS 锚点段（GUI-DESIGN 规则 6）+ 取色只走色板
    assert "/* === F12 历史聚合 ===" in src and "/* === end F12 历史聚合 === */" in src, \
        "F12 CSS 必须进锚点段"
    assert ".hist-agg .tool-agg-body .think-box" in src
    # 零新增颜色 token：锚点段内无 #hex 或 rgb() 新值
    css_seg = src.split("/* === F12 历史聚合 === */")[1].split("/* === end F12")[0]
    assert "#" not in css_seg and "rgb(" not in css_seg, \
        f"F12 CSS 段不得引入新颜色: {css_seg}"

    # L1 教训：新函数不引顶层 DOM（无 getElementById 在函数级直出）
    for fn_name in ("renderHistAggCard", "renderHistToolFlat"):
        fn_src = _extract_func(src, fn_name)
        assert "getElementById" not in fn_src, f"{fn_name} 不得顶层引用 DOM"


# ── F12-2：node 实跑 transcript 重放 ─────────────────────────────────

def test_f12_2_hist_replay_aggregation_node():
    """构造"思考+3 工具+正文"×3 回合 transcript，走真实 renderFullHistory：
    - 前两回合各成一张聚合卡（.hist-agg，含思考框 + 3 工具卡）
    - 最后一回合（最新一轮）工具卡平铺（带 diff 的走 renderHistToolDiff，
      无 diff 走 renderHistToolFlat）→ chatEl 直接子元素含 3 张平铺工具卡
    - diff 红绿块仍在（diffBlock 输出含 dl add / dl del）"""
    src = GUI_FILE.read_text(encoding="utf-8")
    funcs = []
    for fn in ("renderFullHistory", "renderHistAggCard", "renderHistToolFlat",
               "renderHistToolDiff", "addHistThinking", "buildHistThinkBox",
               "buildHistToolCard", "diffBlock",
               "toolSummary", "diffStats", "esc", "toolIcon"):
        funcs.append(_extract_func(src, fn))

    transcript = [
        {"role": "user", "text": "问题1：查一下项目结构"},
        {"role": "assistant", "thinking": "思考1：先看目录", "text": "",
         "tool_calls": [{"id": "a1"}, {"id": "a2"}, {"id": "a3"}]},
        {"role": "tool", "name": "list_directory", "content": "src/ lib/ tests/", "inline_diff": ""},
        {"role": "tool", "name": "read_local_file", "content": "package.json", "inline_diff": ""},
        {"role": "tool", "name": "edit_file", "content": "改配置", "inline_diff": "@@ -1,3 +1,3 @@\n-旧行\n+新行\n 上下文"},
        {"role": "assistant", "text": "回答1：结构已查清"},
        {"role": "user", "text": "问题2：继续"},
        {"role": "assistant", "thinking": "思考2：再深挖", "text": "",
         "tool_calls": [{"id": "b1"}, {"id": "b2"}, {"id": "b3"}]},
        {"role": "tool", "name": "grep_code", "content": "找到 3 处", "inline_diff": ""},
        {"role": "tool", "name": "read_local_file", "content": "core/engine.py", "inline_diff": ""},
        {"role": "tool", "name": "list_directory", "content": "tools/", "inline_diff": ""},
        {"role": "assistant", "text": "回答2：已定位"},
        {"role": "user", "text": "问题3：修复"},
        {"role": "assistant", "thinking": "思考3：动手改", "text": "",
         "tool_calls": [{"id": "c1"}, {"id": "c2"}, {"id": "c3"}]},
        {"role": "tool", "name": "execute_terminal", "content": "pytest 通过", "inline_diff": ""},
        {"role": "tool", "name": "grep_code", "content": "定位 2 处", "inline_diff": ""},
        {"role": "tool", "name": "edit_file", "content": "修复完成", "inline_diff": "@@ -1,5 +1,5 @@\n-坏行\n+好行\n 保持"},
        {"role": "assistant", "text": "回答3：修好了"},
    ]
    tr_json = json.dumps(transcript, ensure_ascii=False)

    js = r"""
const assert = require('assert');

// ── 增强 DOM 桩（支持 className/innerHTML/firstChild/querySelector 最小集）──
function makeEl(tag) {
  const el = {
    tagName: tag, _className: '', _innerHTML: '', textContent: '', style: {},
    _children: [], _attrs: {}, parentNode: null, _qs: {},
    scrollTop: 0, scrollHeight: 0,
    setAttribute(k, v) { this._attrs[k] = v; },
    appendChild(c) { if (c) { c.parentNode = this; this._children.push(c); } return c; },
    insertBefore(c, ref) {
      if (!c) return c;
      c.parentNode = this;
      const i = this._children.indexOf(ref);
      if (i < 0) this._children.push(c); else this._children.splice(i, 0, c);
      return c;
    },
    querySelector(sel) {
      if (!this._qs[sel]) {
        const sub = makeEl(sel);
        sub.parentNode = this;
        this._qs[sel] = sub;
        if (sel === '.tool-agg-body') this._children.push(sub);
      }
      return this._qs[sel];
    },
    querySelectorAll() { return []; },
    get firstChild() { return this._firstChild || null; },
    set innerHTML(v) {
      this._innerHTML = v || '';
      if (v) {
        this._firstChild = makeEl('div');
        this._firstChild._innerHTML = v;
        // 解析 class 属性：diffBlock 输出的 <div class="diff-block"> 可被检测
        const cm = v.match(/class="([^"]+)"/);
        if (cm) this._firstChild._className = cm[1];
      }
    },
    get innerHTML() { return this._innerHTML || ''; },
    get previousElementSibling() {
      if (!this.parentNode) return null;
      const kids = this.parentNode._children;
      const i = kids.indexOf(this);
      return i > 0 ? kids[i - 1] : null;
    },
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
      const want = force === undefined ? !has : !!force;
      if (want && !has) el._className = (el._className + ' ' + c).trim();
      if (!want && has) el._className = (el._className || '').split(/\s+/).filter(Boolean).filter(x => x !== c).join(' ');
    },
  };
  return el;
}

const chatEl = makeEl('div');
const document = { createElement: makeEl };
const window = {};
const welcomeEl = { style: {} };
const statusLog = [];
const msgLog = [];
const thinkLog = [];
function toggleThinkBox() {}
function addStatus(t) { statusLog.push(t); }
function addMsg(kind, text, id) {
  msgLog.push({ kind, text });
  const el = makeEl('div'); el.className = 'msg ' + kind; el.textContent = text;
  chatEl.appendChild(el);
}
""" + "\n" + _extract_var(src, "TOOL_ICONS") + "\n" + _extract_var(src, "TOOL_FRIENDLY") + "\n" + "\n".join(funcs) + r"""

// 桩覆盖：addHistThinking 记录 thinkLog（真实实现只 appendChild，无法观测调用）
function addHistThinking(t) {
  thinkLog.push(t);
  chatEl.appendChild(buildHistThinkBox(t));
}

(async () => {
  const result = { session_id: 's1', messages: TRANSCRIPT, user_named: false };
  await renderFullHistory('s1', result);

  // 统计 chatEl 直接子元素分类
  let aggCards = 0, flatTools = 0, flatDiffs = 0;
  const aggBodies = [];
  function scan(el, depth) {
    const cls = String(el.className || '');
    const tokens = cls.split(/\s+/).filter(Boolean);
    if (tokens.includes('hist-agg')) { aggCards++; aggBodies.push(el); }
    // 平铺工具卡 = 类 token 含 'tool' 且是 chatEl 直接子元素（聚合卡 'tool-agg' 不算）
    if (tokens.includes('tool') && el.parentNode === chatEl) flatTools++;
    if (cls.indexOf('diff-block') >= 0 && el.parentNode === chatEl) flatDiffs++;
    (el._children || []).forEach(c => scan(c, depth + 1));
  }
  chatEl._children.forEach(c => scan(c, 0));

  // 断言 1：前两回合各一张聚合卡
  assert(aggCards === 2, '应有 2 张聚合卡（前两回合），实际 ' + aggCards);

  // 断言 2：每张聚合卡 body = 思考框 + 3 工具卡（diff 块数按 transcript 区分：
  // 第一回合第 3 工具 edit_file 带 inline_diff → 1 个；第二回合 3 工具均无 diff → 0 个）
  aggBodies.forEach((agg, i) => {
    const body = agg.querySelector('.tool-agg-body');
    const bodyKids = body._children;
    const thinks = bodyKids.filter(c => String(c.className || '').indexOf('think-box') >= 0).length;
    const tools = bodyKids.filter(c => String(c.className || '').indexOf('tool') === 0).length;
    const diffs = bodyKids.filter(c => String(c.className || '').indexOf('diff-block') >= 0).length;
    assert(thinks === 1, `聚合卡${i} 应有 1 思考框，实际 ${thinks}`);
    assert(tools === 3, `聚合卡${i} 应有 3 工具卡，实际 ${tools}`);
    const expectDiffs = i === 0 ? 1 : 0;
    assert(diffs === expectDiffs, `聚合卡${i} 应有 ${expectDiffs} 个 diff 块，实际 ${diffs}`);
  });

  // 断言 3：最新一轮工具平铺（3 个直接子工具卡 + 1 个 diff 块平铺）
  assert(flatTools === 3, '最新一轮应平铺 3 张工具卡，实际 ' + flatTools);
  assert(flatDiffs === 1, '最新一轮应平铺 1 个 diff 块，实际 ' + flatDiffs);

  // 断言 4：最新一轮思考平铺（thinkLog 捕获 addHistThinking 调用）
  assert(thinkLog.length === 1 && thinkLog[0].indexOf('思考3') >= 0,
    '最新一轮思考应平铺渲染，实际 ' + JSON.stringify(thinkLog));

  // 断言 5：diffBlock 红绿语义（dl add / dl del）
  const dhtml = diffBlock('@@ -1,3 +1,3 @@\n-旧行\n+新行\n 上下文');
  assert(dhtml.indexOf('dl add') >= 0 && dhtml.indexOf('dl del') >= 0,
    'diffBlock 红绿块语义不破');

  console.log('NODE_F12_OK ' + JSON.stringify({ aggCards, flatTools, flatDiffs,
    thinkLog: thinkLog.length, bodyKids: aggBodies.map(b => b.querySelector('.tool-agg-body')._children.length) }));
})().catch(e => { console.error('ERR', e); process.exit(1); });
""".replace("TRANSCRIPT", tr_json)
    out = _run_node(js)
    assert "NODE_F12_OK" in out, f"node 实跑失败: {out}"


# ── F12-3：TUI 零干扰 ────────────────────────────────────────────────

def test_f12_3_tui_zero_change():
    """TUI 零干扰铁律：本票不改 TUI 源码（git diff 无 ui-tui 路径）。"""
    try:
        r = subprocess.run(
            ["git", "diff", "--name-only", "--", "ui-tui/"],
            cwd=ROOT, capture_output=True, text=True, timeout=10,
        )
    except Exception:
        pytest.skip("git 不可用，跳过 diff 检查")
    assert r.returncode == 0, f"git diff 失败: {r.stderr}"
    assert r.stdout.strip() == "", f"TUI 目录有改动（铁律零变化）: {r.stdout}"


# ── F12-4：审查修复 node 实跑（问题1 必跑：展开聚合卡→点思考框→卡不收起）──

def test_f12_4_review_fixes_node():
    """审查修复四项的 node 实跑：
    - 问题1：聚合卡展开后点击考古内思考框 —— 事件冒泡到聚合卡 onclick，
      guard（.think-box/.diff-block）必须拦截 → 卡不收起（body 仍 display:block）
    - 问题2：过往 assistant 带 tool_calls 但工具消息缺失（归档裁剪）——
      flushHistAgg 空链时 aggThink 落 addHistThinking 平铺，思考不丢
    - 问题4：renderFullHistory 末尾统一 scrollTop（循环内渲染函数不再逐条滚）"""
    src = GUI_FILE.read_text(encoding="utf-8")
    funcs = []
    for fn in ("renderFullHistory", "renderHistAggCard", "renderHistToolFlat",
               "renderHistToolDiff", "addHistThinking", "buildHistThinkBox",
               "buildHistToolCard", "diffBlock", "toolSummary", "diffStats", "esc", "toolIcon"):
        funcs.append(_extract_func(src, fn))

    # 问题1 transcript：两回合，前回合收聚合卡（含思考框），最新轮平铺
    transcript1 = [
        {"role": "user", "text": "q1"},
        {"role": "assistant", "thinking": "思考1", "text": "",
         "tool_calls": [{"id": "a1"}]},
        {"role": "tool", "name": "list_directory", "content": "src/", "inline_diff": ""},
        {"role": "assistant", "text": "答1"},
        {"role": "user", "text": "q2"},
        {"role": "assistant", "thinking": "思考2", "text": "",
         "tool_calls": [{"id": "b1"}, {"id": "b2"}]},
        {"role": "tool", "name": "grep_code", "content": "hit", "inline_diff": ""},
        {"role": "tool", "name": "edit_file", "content": "改", "inline_diff": "@@ -1,2 +1,2 @@\n-旧\n+新\n 上下文"},
        {"role": "assistant", "text": "答2"},
    ]
    # 问题2 transcript：过往 assistant 声明 tool_calls 但无 tool 消息（裁剪）
    transcript2 = [
        {"role": "user", "text": "q1"},
        {"role": "assistant", "thinking": "思考A", "text": "",
         "tool_calls": [{"id": "x1"}]},
        {"role": "user", "text": "q2"},
        {"role": "assistant", "thinking": "思考B", "text": "",
         "tool_calls": [{"id": "y1"}]},
        {"role": "tool", "name": "grep_code", "content": "hit", "inline_diff": ""},
        {"role": "assistant", "text": "答"},
    ]
    tr1 = json.dumps(transcript1, ensure_ascii=False)
    tr2 = json.dumps(transcript2, ensure_ascii=False)

    js = r"""
const assert = require('assert');

function makeEl(tag) {
  const el = {
    tagName: tag, _className: '', _innerHTML: '', textContent: '', style: {},
    _children: [], _attrs: {}, parentNode: null, _qs: {},
    scrollTop: 0, scrollHeight: 0,
    setAttribute(k, v) { this._attrs[k] = v; },
    appendChild(c) { if (c) { c.parentNode = this; this._children.push(c); } return c; },
    insertBefore(c, ref) {
      if (!c) return c;
      c.parentNode = this;
      const i = this._children.indexOf(ref);
      if (i < 0) this._children.push(c); else this._children.splice(i, 0, c);
      return c;
    },
    querySelector(sel) {
      if (!this._qs[sel]) {
        const sub = makeEl(sel);
        sub.parentNode = this;
        this._qs[sel] = sub;
        if (sel === '.tool-agg-body') {
          // 模拟真实 DOM：innerHTML 中 style="display:none"（桩不解析 style）
          sub.style.display = 'none';
          this._children.push(sub);
        }
      }
      return this._qs[sel];
    },
    querySelectorAll() { return []; },
    closest(sel) {
      // 沿父链匹配 className（含点号选择器）
      const cls = sel.replace('.', '');
      let cur = this;
      while (cur) {
        const c = String(cur.className || '');
        if (c.split(/\s+/).filter(Boolean).includes(cls)) return cur;
        cur = cur.parentNode;
      }
      return null;
    },
    get firstChild() { return this._firstChild || null; },
    set innerHTML(v) {
      this._innerHTML = v || '';
      if (v) {
        this._firstChild = makeEl('div');
        this._firstChild._innerHTML = v;
        // 解析 class 属性：diffBlock 输出的 <div class="diff-block"> 可被检测
        const cm = v.match(/class="([^"]+)"/);
        if (cm) this._firstChild._className = cm[1];
      }
    },
    get innerHTML() { return this._innerHTML || ''; },
    onclick: null,
  };
  Object.defineProperty(el, 'className', {
    get() { return el._className; },
    set(v) { el._className = v || ''; },
  });
  return el;
}

const chatEl = makeEl('div');
const document = { createElement: makeEl };
const window = {};
function toggleThinkBox(tb) { tb.classList.toggle('show'); }
function addStatus() {}
function addMsg(kind, text, id) {
  const el = makeEl('div'); el.className = 'msg ' + kind; el.textContent = text;
  chatEl.appendChild(el);
}
""" + "\n" + _extract_var(src, "TOOL_ICONS") + "\n" + _extract_var(src, "TOOL_FRIENDLY") + "\n" + "\n".join(funcs) + r"""

(async () => {
  // ── 问题1：点思考框不误收聚合卡 ──
  await renderFullHistory('s1', { session_id: 's1', messages: T1, user_named: false });
  let agg = chatEl._children.find(c => String(c.className || '').indexOf('hist-agg') >= 0);
  assert(agg, '应有聚合卡');
  const body = agg.querySelector('.tool-agg-body');
  // 先展开聚合卡（模拟点头）
  const head = makeEl('span'); head.className = 'tool-agg-head';
  head.parentNode = agg;
  agg.onclick({ target: head });
  assert(body.style.display === 'block', '点头后聚合卡应展开，实际 ' + body.style.display);
  // 点考古内思考框（事件冒泡到聚合卡 onclick，guard 必须拦截）
  const tb = agg.querySelector('.tool-agg-body')._children
    .find(c => String(c.className || '').indexOf('think-box') >= 0);
  assert(tb, '聚合卡内应有思考框');
  tb.parentNode = agg.querySelector('.tool-agg-body');
  agg.onclick({ target: tb });
  assert(body.style.display === 'block',
    '问题1失败：点思考框误收聚合卡（guard 未拦截冒泡）');

  // ── 问题2：空链思考不丢（归档裁剪）──
  await renderFullHistory('s2', { session_id: 's2', messages: T2, user_named: false });
  const thinkBoxes = [];
  (function collect(el) {
    if (String(el.className || '').indexOf('think-box') >= 0) {
      // 桩语义：思考文本写在 .think-text 子节点（querySelector 缓存）上
      const txt = el._qs && el._qs['.think-text'];
      thinkBoxes.push(txt ? txt.textContent : el.textContent);
    }
    (el._children || []).forEach(collect);
  })(chatEl);
  assert(thinkBoxes.some(t => t.indexOf('思考A') >= 0),
    '问题2失败：空链思考应平铺不丢，实际 thinkBoxes=' + JSON.stringify(thinkBoxes));

  console.log('NODE_F12_REVIEW_OK');
})().catch(e => { console.error('ERR', e); process.exit(1); });
""".replace("T1", tr1).replace("T2", tr2)
    out = _run_node(js)
    assert "NODE_F12_REVIEW_OK" in out, f"审查修复 node 实跑失败: {out}"

    # ── 问题4（Python 侧静态）：循环内渲染函数无 scrollTop，末尾统一滚一次 ──
    for fn in ("addHistThinking", "renderHistToolDiff", "renderHistToolFlat",
               "renderHistAggCard", "buildHistThinkBox", "buildHistToolCard"):
        fn_src = _extract_func(src, fn)
        assert "scrollTop" not in fn_src, f"{fn} 内不应有 scrollTop（已统一到 renderFullHistory 末尾）"
    full = _extract_func(src, "renderFullHistory")
    assert full.count("chatEl.scrollTop") == 1, \
        f"renderFullHistory 内 scrollTop 应恰好 1 次（末尾统一滚），实际 {full.count('chatEl.scrollTop')} 次"
    assert full.rstrip().endswith("chatEl.scrollTop = chatEl.scrollHeight;\n}"), \
        "renderFullHistory 应以末尾统一 scrollTop 收尾"
