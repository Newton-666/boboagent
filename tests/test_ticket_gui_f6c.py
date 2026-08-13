"""TICKET-GUI-F6C 回归测试 — 思考段随工具一并吞并（屏幕只留聚合卡+最新思考+最新工具）。

覆盖：
- F6C-1 静态断言（GUI 闸门）：swallowThinkBox 存在（think-box + collapsed +
  previousElementSibling + 隔聚合卡向前找档）；两处吞并循环均先移入配对思考框；
  F6B 合并判定 / tool.start 收束 / F4-1 聚合语义全部保留不破
- F6C-2 node 实跑 5 步施工模拟（提取真实 addTool/swallowThinkBox/aggHeadArrowText）：
  * 每步带配对思考：任意时刻 chatEl 无连续思考框（思考墙）；最终结构
    [聚合卡][最新思考][最新工具]；聚合卡体内 思考→工具 成对顺序
  * 中间某步无思考：目标态仍成立，无思考残留
  * 无思考的连续工具步：聚合卡正常吞并，无思考墙

注：GUI 渲染层无法无头全自动化，采用静态断言 + node 实跑（与 F2/F3/F4/F6/F6B 同款，
零漂移验证当前 HTML 内真实函数）。
"""

import json
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
GUI_FILE = ROOT / "apps" / "desktop" / "dist" / "index.html"


# ── 辅助：提取当前 HTML 内真实 JS 函数（零漂移，与 F4/F6 同款） ──────────

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


# ── F6C-1：静态断言 ────────────────────────────────────────────────────

def test_f6c_1_static_asserts():
    """swallowThinkBox 存在且语义正确；两处吞并均先移入配对思考框；F6B/F4 不破。"""
    src = GUI_FILE.read_text(encoding="utf-8")

    # ── F6C 核心：swallowThinkBox 函数 ──
    assert "function swallowThinkBox(d)" in src, "F6C: 需要 swallowThinkBox 辅助函数"
    assert "previousElementSibling" in src, \
        "F6C: 必须用 previousElementSibling 找前方紧邻元素"
    assert "contains('think-box')" in src, "F6C: 前方紧邻须是思考框"
    assert "contains('collapsed')" in src, "F6C: 只吞已折叠思考框（打开框不吞）"
    # 隔聚合卡向前找档（聚合卡插在 最新思考 与 最新工具 之间）
    assert "contains('tool-agg')" in src, "F6C: 需支持隔聚合卡向前找配对思考"

    # ── F6C 核心：两处吞并循环均先移入配对思考框 ──
    assert "if (tb2) aggBody2.appendChild(tb2);" in src, \
        "F6C: 已有聚合卡吞并须先移入配对思考框（思考在前）"
    assert "if (tb) aggBody.appendChild(tb);" in src, \
        "F6C: 建聚合卡吞并须先移入配对思考框（思考在前）"
    assert "aggBody2.appendChild(d);" in src and "aggBody.appendChild(d);" in src, \
        "F6C: 工具卡吞并保留（F4-1 语义不破）"

    # ── F6B 协同：合并判定保留 ──
    md = _extract_event_block(src, "message.delta")
    assert "lastElementChild" in md and "contains('think-box')" in md and \
        "contains('collapsed')" in md, "F6B 合并判定不破（真正相邻思考仍合并）"

    # ── F6 不破：tool.start 收束 ──
    ts = _extract_event_block(src, "tool.start")
    assert "collapseThinkBox(thinkBoxEl, thinkText)" in ts, "F6 tool.start 收束不破"
    assert "thinkBoxEl = null" in ts and "thinkText = ''" in ts, "F6 置空不破"

    # ── F4-1 不破：聚合语义保留 ──
    assert "roundTotalCount >= 2" in src, "第 2 步起建聚合卡不破"
    assert "roundToolEls = []" in src, "吞并后清空不破"
    assert "已执行 ' + roundTotalCount + ' 步操作" in src, "标题实时涨不破"
    assert "roundToolEls = []; roundAggregated = false; roundTotalCount = 0; roundAggregateHead = null;" in src, \
        "回合结束重置不破"
    # 视觉样式零新增：无新 class 引入
    assert "think-agg" not in src, "F6C 不得引入新视觉 class"


# ── F6C-2：node 实跑 5 步施工模拟 ──────────────────────────────────────

def _node_simulation_script(with_missing_think: bool, no_think_second: bool = False) -> str:
    """构造 node 脚本：提取真实 addTool 等函数，桩化 DOM，模拟 5 步施工。

    with_missing_think: 第 3 步无思考（工具3 无配对思考）
    no_think_second: 第 2 步无思考（测隔聚合卡吞并 + 无思考残留）
    """
    src = GUI_FILE.read_text(encoding="utf-8")
    # F6D 配套：提取写类名单常量 + isWriteToolEl（addTool 现在引用它，桩必须带上）
    wt_m = re.search(r"var WRITE_TOOLS = \[[^\]]*\];", src)
    assert wt_m, "F6D: 需要 var WRITE_TOOLS 名单"
    fns = "\n".join(
        [wt_m.group(0), _extract_func(src, "isWriteToolEl")] +
        [_extract_func(src, n) for n in ("esc", "addTool", "swallowThinkBox", "aggHeadArrowText")]
    )
    # 每步 (思考文本或 None, 工具 id)；默认每步带思考
    steps = [(f"思考{i}", f"t{i}") for i in range(1, 6)]
    if with_missing_think:
        steps[2] = (None, "t3")  # 第 3 步无思考
    if no_think_second:
        steps[1] = (None, "t2")  # 第 2 步无思考
    steps_json = json.dumps(steps, ensure_ascii=False)
    # 期望聚合卡体顺序（前 4 步被吞；思考在前工具在后）
    body_order = []
    for think, tid in steps[:-1]:
        if think:
            body_order.append(think)
        body_order.append("tool")
    # 期望最终消息流直接子元素（最后一步的思考+工具保留摊开）
    final_kids = ["聚合卡"]
    last_think, last_tool = steps[-1]
    if last_think:
        final_kids.append(last_think)
    final_kids.append("tool")
    body_json = json.dumps(body_order, ensure_ascii=False)
    final_json = json.dumps(final_kids, ensure_ascii=False)
    js = f"""
const assert = require('assert');

// ── mini-DOM 桩（classList 实时读 className——DOM 里 className 赋值后 classList 同步）──
function miniEl(cls) {{
  const el = {{
    _className: cls || '',
    _children: [], _subs: {{}}, style: {{}},
    id: '', innerHTML: '', textContent: '', parentNode: null, _attrs: {{}},
    setAttribute(k, v) {{ this._attrs[k] = v; }},
    appendChild(ch) {{
      // 真实 DOM 语义：移动节点（从旧父级移除）
      if (ch.parentNode) {{
        const oldKids = ch.parentNode._children;
        const i = oldKids.indexOf(ch);
        if (i >= 0) oldKids.splice(i, 1);
      }}
      ch.parentNode = this;
      this._children.push(ch);
      return ch;
    }},
    insertBefore(ch, ref) {{
      const i = this._children.indexOf(ref);
      ch.parentNode = this;
      if (i < 0) this._children.push(ch); else this._children.splice(i, 0, ch);
      return ch;
    }},
    get previousElementSibling() {{
      if (!this.parentNode) return null;
      const kids = this.parentNode._children;
      const i = kids.indexOf(this);
      return i > 0 ? kids[i - 1] : null;
    }},
    querySelector(sel) {{
      if (sel === '.tool-agg-head' || sel === '.tool-agg-arrow' || sel === '.tool-agg-body') {{
        if (!this._subs[sel]) {{
          const sub = miniEl(sel.slice(1));
          sub.parentNode = this;
          this._subs[sel] = sub;
          if (sel === '.tool-agg-body') this._children.push(sub);
        }}
        return this._subs[sel];
      }}
      if (sel === '.think-text') {{
        if (!this._thinkTextEl) this._thinkTextEl = {{ textContent: this._thinkText || '' }};
        return this._thinkTextEl;
      }}
      return null;  // .tool-result / .tool-toggle（onclick 内用，本模拟不触发）
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
let thinkBoxEl = null;      // tool.start 收束后置空；模拟中直接构造已折叠思考框
let toolIdCounter = 0;
let roundToolEls = [], roundAggregated = false, roundTotalCount = 0, roundAggregateHead = null;
const document = {{ createElement: (tag) => miniEl(tag) }};

{fns}

function thinkBox(text) {{
  const el = miniEl('think-box collapsed');
  el._thinkText = text;
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
function directClasses(el) {{
  return el._children.map(c => c.classList.contains('think-box') ? 'think:' + (c._thinkText || '') : c.className);
}}

// ── 模拟 5 步施工流（每步：思考折叠 → 工具卡；think=null 则无思考）──
const steps = {steps_json};
for (const [think, tid] of steps) {{
  if (think) chatEl.appendChild(thinkBox(think));
  addTool('tool_' + tid, '', tid);
  assert(maxConsecThink(chatEl) <= 1,
    '步骤' + tid + '后无思考墙: ' + JSON.stringify(directClasses(chatEl)));
}}

// ── 目标态断言 ──
const kids = chatEl._children;
const expectKids = {final_json};
const gotKids = directClasses(chatEl).map((c) => {{
  if (c.startsWith('think:')) return c.slice('think:'.length);
  if (c === 'tool-agg') return '聚合卡';
  return c;
}});
assert(JSON.stringify(gotKids) === JSON.stringify(expectKids),
  '最终结构应为 ' + JSON.stringify(expectKids) + '，实际: ' + JSON.stringify(gotKids));

// ── 聚合卡标题计数 ──
const head = kids[0].querySelector('.tool-agg-head');
assert(head.textContent.includes('已执行 5 步操作'), '标题应计 5 步: ' + head.textContent);

// ── 聚合卡体内：思考→工具 成对顺序 ──
const aggBody = kids[0].querySelector('.tool-agg-body');
const order = aggBody._children.map(c => c._thinkText || c.className);
const expectOrder = {body_json};
assert(JSON.stringify(order) === JSON.stringify(expectOrder),
  '聚合卡体应为 ' + JSON.stringify(expectOrder) + '，实际: ' + JSON.stringify(order));

console.log('NODE_F6C_5STEP_OK');
"""
    return js


def test_f6c_2_five_step_simulation():
    """5 步施工（每步带思考）：任意时刻无思考墙；最终聚合卡+最新思考+最新工具；成对考古。"""
    out = _run_node(_node_simulation_script(with_missing_think=False))
    assert "NODE_F6C_5STEP_OK" in out, f"node 实跑失败: {out}"


def test_f6c_2_missing_think_step():
    """中间某步无思考（工具3 无配对思考）：聚合卡正常吞并，目标态仍成立。"""
    out = _run_node(_node_simulation_script(with_missing_think=True))
    assert "NODE_F6C_5STEP_OK" in out, f"node 实跑失败: {out}"


def test_f6c_2_second_step_no_think():
    """第 2 步无思考：思考1 随工具1 入卡；无思考残留。"""
    out = _run_node(_node_simulation_script(with_missing_think=False, no_think_second=True))
    assert "NODE_F6C_5STEP_OK" in out, f"node 实跑失败: {out}"
