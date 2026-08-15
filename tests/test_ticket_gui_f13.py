"""TICKET-GUI-F13 专项测试 — 历史回放考古模式开关（owner 2026-08-15 定调）。

根因（复盘 2026-08-14）：F12 把过往回合强制收进聚合卡，破坏了"历史=现场原样"
的直觉（用户看历史回放看不到自己当时实际看到的工具链）。

修法：历史回放与实时同一条渲染链 —— 思考框一律 buildHistThinkBox 平铺、
工具卡一律 buildHistToolCard 平铺（diff 红绿块保留）；聚合卡降级为
考古模式（默认关），仅 setHistArchMode(true) 后开启 F12 行为。

覆盖（票验收）：
- F13-1 静态断言：histArchMode/setHistArchMode 存在；renderFullHistory
  含 archMode 分支（默认关平铺，开则聚合）；聚合路径仅 archMode 下进入
- F13-2 node 实跑（默认关）："思考+3 工具+正文"×3 回合 transcript 重放
  → 无任何 .hist-agg 聚合卡；思考框/工具卡/diff 块全部平铺为 chatEl 直接子元素
- F13-3 node 实跑（开）：同一 transcript → 前两回合各一张聚合卡，最新一轮平铺
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


# ── F13-1：静态断言 ───────────────────────────────────────────────────

def test_f13_1_static_arch_mode_switch():
    src = GUI_FILE.read_text(encoding="utf-8")
    # 考古模式开关函数存在
    assert "function histArchMode()" in src, "缺考古模式开关读取函数"
    assert "function setHistArchMode(on)" in src, "缺考古模式开关写入函数"
    # renderFullHistory 读开关（默认关=平铺）
    full = _extract_func(src, "renderFullHistory")
    assert "var archMode = histArchMode();" in full, "renderFullHistory 应读取考古开关"
    # 平铺路径：思考框 buildHistThinkBox、工具卡 buildHistToolCard 直接 appendChild
    assert "buildHistThinkBox(m.thinking)" in full, "历史思考框应一律平铺"
    assert "buildHistToolCard(m.name" in full, "历史工具卡应一律平铺"
    # 聚合路径仅考古模式：缓冲进 aggThink/aggTools
    assert "archMode && !histLatest" in full, "聚合缓冲应仅考古模式且非最新一轮"
    # 现场原样：默认关时无聚合卡（flushHistAgg 仅在聚合缓冲非空时出卡）
    assert "if (aggTools.length === 0)" in full, "空聚合链不应出卡"
    # 姿势持久化钩子（F13 附带）：回放末尾 applyPose
    assert "applyPose(sid)" in full, "回放末尾应按持久化姿势还原"


# ── F13-2/3：node 实跑 transcript 重放（默认关 vs 考古开）───────────────

TRANSCRIPT = [
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
    {"role": "tool", "name": "edit_file", "content": "修好了", "inline_diff": ""},
    {"role": "tool", "name": "run_tests", "content": "全绿", "inline_diff": ""},
    {"role": "tool", "name": "git_commit", "content": "提交", "inline_diff": ""},
    {"role": "assistant", "text": "回答3：已修复"},
]


def _build_js(arch_on: bool) -> str:
    src = GUI_FILE.read_text(encoding="utf-8")
    funcs = []
    for fn in ("renderFullHistory", "renderHistAggCard", "buildHistThinkBox",
               "buildHistToolCard", "diffBlock", "toolSummary", "diffStats",
               "esc", "toolIcon"):
        funcs.append(_extract_func(src, fn))
    tr_json = json.dumps(TRANSCRIPT)
    return r"""
// ── node 桩 DOM（最小集）──
function makeEl(tag) {
  const el = {
    tagName: tag, _className: '', _innerHTML: '', textContent: '', style: {},
    _children: [], _attrs: {}, parentNode: null, _qs: {}, _firstChild: null,
    appendChild(c) { if (c) { c.parentNode = this; this._children.push(c); } return c; },
    setAttribute(k, v) { this._attrs[k] = v; },
    getAttribute(k) { return this._attrs[k]; },
    querySelector(sel) {
      if (!this._qs[sel]) {
        const sub = makeEl(sel); sub.parentNode = this; this._qs[sel] = sub;
        if (sel === '.tool-agg-body') this._children.push(sub);
      }
      return this._qs[sel];
    },
    querySelectorAll() { return []; },
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
// ── 考古模式开关 stub（node 桩无 localStorage）──
let _arch = """ + ("true" if arch_on else "false") + r""";
function histArchMode() { return _arch; }
function setHistArchMode(on) { _arch = !!on; }
function applyPose() {}
function readPose() { return {}; }
function writePose() {}
let histAggSeq = 0;

(async () => {
  const result = { session_id: 's1', messages: TRANSCRIPT, user_named: false };
  await renderFullHistory('s1', result);

  let aggCards = 0, flatTools = 0, flatThinks = 0, flatDiffs = 0;
  function scan(el) {
    const cls = String(el.className || '');
    const tokens = cls.split(/\s+/).filter(Boolean);
    if (tokens.includes('hist-agg')) aggCards++;
    if (tokens.includes('tool') && el.parentNode === chatEl) flatTools++;
    if (cls.indexOf('think-box') >= 0 && el.parentNode === chatEl) flatThinks++;
    if (cls.indexOf('diff-block') >= 0 && el.parentNode === chatEl) flatDiffs++;
    (el._children || []).forEach(scan);
  }
  chatEl._children.forEach(scan);

  console.log('NODE_F13 ' + JSON.stringify({ aggCards, flatTools, flatThinks, flatDiffs }));
})().catch(e => { console.error('ERR', e); process.exit(1); });
""".replace("TRANSCRIPT", tr_json)


def test_f13_2_node_default_flat():
    """默认关（现场原样）：无聚合卡；思考/工具/diff 全平铺。"""
    out = _run_node(_build_js(arch_on=False))
    assert "NODE_F13" in out, f"node 实跑失败: {out}"
    m = re.search(r"NODE_F13 (\{.*\})", out)
    stats = json.loads(m.group(1))
    assert stats["aggCards"] == 0, f"默认关不应出聚合卡，实际 {stats}"
    # archMode=false 全平铺：3 回合思考框 + 9 工具卡 + 1 diff 块
    assert stats["flatThinks"] == 3, f"思考框应 3 个全平铺，实际 {stats}"
    assert stats["flatTools"] == 9, f"工具卡应 9 张全平铺，实际 {stats}"
    assert stats["flatDiffs"] == 1, f"diff 块应 1 个平铺，实际 {stats}"


def test_f13_3_node_arch_on_aggregates():
    """考古开：前两回合聚合卡 2 张；最新一轮平铺（思考1+工具3+diff1）。"""
    out = _run_node(_build_js(arch_on=True))
    assert "NODE_F13" in out, f"node 实跑失败: {out}"
    m = re.search(r"NODE_F13 (\{.*\})", out)
    stats = json.loads(m.group(1))
    assert stats["aggCards"] == 2, f"考古开应出 2 张聚合卡，实际 {stats}"
    assert stats["flatThinks"] == 1, f"最新一轮思考应平铺 1 个，实际 {stats}"
    assert stats["flatTools"] == 3, f"最新一轮工具应平铺 3 张，实际 {stats}"
    assert stats["flatDiffs"] == 0, f"最新一轮 3 工具均无 diff，实际 {stats}"
