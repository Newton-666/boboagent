"""TICKET-GUI-F6B 回归测试 — 连续思考合并（分段只发生在工具边界）。

覆盖：
- F6B-1 静态断言（GUI 闸门）：message.delta 块含末尾元素检查（lastElementChild
  + think-box + collapsed）；createThinkBox 仍在 else 分支（F6 行为保留）；
  F6-1 原有断言不破（if (!thinkBoxEl) / createThinkBox() / tool.start 收束）
- F6B-2 node 实跑（合并/分段行为）：提取真实 message.delta 事件块，桩化 DOM：
  * 场景 A：末尾紧邻折叠思考框（中间无工具卡）→ 新思考追加进该框（换行衔接），
    不新建框（created===0），thinkText 续接
  * 场景 B：末尾是工具卡 → 照常新建框（F6 分段保留）
  * 场景 C：末尾无元素 / 正文消息 → 新建框

注：GUI 渲染层无法无头全自动化，采用静态断言 + node 实跑（与 F3/F4/F6 同款，
零漂移验证当前 HTML 内真实事件块）。
"""

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
GUI_FILE = ROOT / "apps" / "desktop" / "dist" / "index.html"


# ── 辅助：提取当前 HTML 内真实事件块（零漂移，与 F6 同款） ─────────────

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


# ── F6B-1：静态断言 ────────────────────────────────────────────────────

def test_f6b_1_delta_merge_static_asserts():
    """message.delta 必须有末尾紧邻折叠框检查；createThinkBox 保留（F6 不破）。"""
    src = GUI_FILE.read_text(encoding="utf-8")
    md = _extract_event_block(src, "message.delta")

    # F6B：合并检查 —— 末尾紧邻元素判定（lastElementChild + think-box + collapsed）
    assert "lastElementChild" in md, \
        "F6B: message.delta 应检查消息流末尾元素: " + md[:400]
    assert "contains('think-box')" in md, \
        "F6B: 应检查末尾元素是思考框: " + md[:400]
    assert "contains('collapsed')" in md, \
        "F6B: 应检查末尾思考框已收束（折叠）: " + md[:400]
    # 追加衔接：换行分隔续接已有思考文本
    assert "textContent + '\\n'" in md, \
        "F6B: 追加应换行衔接已有思考内容: " + md[:400]

    # F6 保留：无打开框仍走开框逻辑（else 分支 createThinkBox）
    assert "if (!thinkBoxEl)" in md, "F6-1 断言不破: if (!thinkBoxEl)"
    assert "createThinkBox()" in md, "F6-1 断言不破: createThinkBox()"

    # tool.start 收束路径不动（F6 已验收：工具边界分段）
    ts = _extract_event_block(src, "tool.start")
    assert "collapseThinkBox(thinkBoxEl, thinkText)" in ts, "tool.start 收束断言不破"
    assert "thinkBoxEl = null" in ts and "thinkText = ''" in ts, \
        "tool.start 置空断言不破"

    # message.complete 兼容置空态不动（F6 已验收）
    mc = _extract_event_block(src, "message.complete")
    assert "if (!thinkBoxEl) thinkBoxEl = createThinkBox();" in mc, \
        "message.complete 收束断言不破"

    # 铁律回归：F3-5 diff 显示 / F6 thinking 分段要素仍在
    for keep in ("diffHighlight", "function diffBlock", "collapseThinkBox",
                 "createThinkBox", "toolSummary"):
        assert keep in src, f"回归破坏（要素缺失）: {keep}"


# ── F6B-2：node 实跑合并/分段行为 ──────────────────────────────────────

def test_f6b_2_delta_merge_node():
    """提取真实 message.delta 事件块，桩化 DOM：
    - 末尾紧邻折叠思考框 → 追加合并（不新建）
    - 末尾工具卡 / 无元素 / 正文 → 新建框（分段保留）"""
    src = GUI_FILE.read_text(encoding="utf-8")
    block = _extract_event_block(src, "message.delta")
    # on('message.delta', function(data) {...}); → deltaHandler = function(data) {...};
    handler = re.sub(
        r"^on\('message\.delta',\s*function",
        "deltaHandler = function",
        block,
    )
    assert handler.strip().startswith("deltaHandler = function(data) {"), \
        "事件块转 handler 失败: " + handler[:80]
    assert handler.rstrip().endswith("}"), \
        "事件块未闭合到 }（_extract_event_block 到 } 结束，不含末尾 );）: " + handler[-40:]

    js = f"""
const assert = require('assert');

// 桩化 delta 依赖
let thinkBoxEl = null;
let thinkText = '';
let created = 0;
const chatEl = {{
  lastElementChild: null,
  scrollTop: 0,
  scrollHeight: 0,
  appendChild() {{}},
  querySelectorAll() {{ return []; }},
}};
function createThinkBox() {{
  created++;
  return {{
    className: 'think-box show',
    classList: {{ contains(c) {{ return c === 'think-box' || c === 'show'; }} }},
    querySelector(sel) {{ return sel === '.think-text' ? {{ textContent: '' }} : null; }},
  }};
}}
function collapsedThinkBox(text) {{
  return {{
    className: 'think-box collapsed',
    classList: {{ contains(c) {{ return c === 'think-box' || c === 'collapsed'; }} }},
    querySelector(sel) {{ return sel === '.think-text' ? {{ textContent: text }} : null; }},
  }};
}}
function toolCard() {{
  return {{ className: 'tool-card', classList: {{ contains(c) {{ return c === 'tool-card'; }} }} }};
}}
function bodyMsg() {{
  return {{ className: 'msg', classList: {{ contains(c) {{ return c === 'msg'; }} }} }};
}}

{handler}

// ── 场景 A：末尾紧邻折叠思考框（中间无工具卡）→ 追加合并，不新建 ──
thinkBoxEl = null; thinkText = ''; created = 0;
chatEl.lastElementChild = collapsedThinkBox('第一段思考');
deltaHandler({{ text: '第二段思考' }});
assert(created === 0, '连续思考不应新建框: created=' + created);
assert(thinkBoxEl === chatEl.lastElementChild, '应复用末尾折叠思考框');
assert(thinkText === '第一段思考\\n第二段思考', '追加应换行衔接: ' + JSON.stringify(thinkText));

// 同框再续一段（thinkBoxEl 非空直接追加）
deltaHandler({{ text: '第三段' }});
assert(thinkText === '第一段思考\\n第二段思考第三段', '同框追加: ' + JSON.stringify(thinkText));

// ── 场景 B：末尾是工具卡 → 照常新建框（F6 分段保留）──
thinkBoxEl = null; thinkText = ''; created = 0;
chatEl.lastElementChild = toolCard();
deltaHandler({{ text: '工具后的思考' }});
assert(created === 1, '工具卡后应新建框（F6 分段）: created=' + created);
assert(thinkText === '工具后的思考', '新框从零开始: ' + JSON.stringify(thinkText));

// ── 场景 C：末尾无元素 → 新建框 ──
thinkBoxEl = null; thinkText = ''; created = 0;
chatEl.lastElementChild = null;
deltaHandler({{ text: '首个思考' }});
assert(created === 1, '无末尾元素应新建框: created=' + created);

// ── 场景 D：末尾是正文消息 → 新建框（正文也是分段边界）──
thinkBoxEl = null; thinkText = ''; created = 0;
chatEl.lastElementChild = bodyMsg();
deltaHandler({{ text: '正文后的思考' }});
assert(created === 1, '正文消息后应新建框: created=' + created);

console.log('NODE_F6B_DELTA_MERGE_OK');
"""
    out = _run_node(js)
    assert "NODE_F6B_DELTA_MERGE_OK" in out, f"node 实跑失败: {out}"
