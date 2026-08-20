"""TICKET-PROFILE-3 专项测试 — profile.update 前端工具卡（24.8 设计落地）。

覆盖（票验收）：
- F20-1 静态断言：TOOL_ICONS 含 profile_update（14×14 细线 SVG，stroke-width=1.25/
  linecap/linejoin=round）、TOOL_LABELS（TOOL_FRIENDLY）含 'profile_update': 'Edit profile'、
  on('profile.update') 监听存在
- F20-2 静态断言：CSS 纯新增 .profile-update-card（存在 + 复用 .diff-block）；
  回调不走 addTool 完整工具卡逻辑（无 tool_id/状态）
- F20-3 node 桩实跑：模拟 profile.update 事件 → 档案更新卡出现在 chatEl
  （图标 + Edit profile 标题 + diff 红绿块）
- F20-4 node 桩实跑：空 payload（无 entry/diff）→ 不渲染
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


def _extract_profile_update_handler(src: str) -> str:
    """提取 on('profile.update', function(data) {...}) 的 function 体（括号配对）。"""
    m = re.search(r"on\('profile\.update', function\(data\)", src)
    assert m, "未找到 on('profile.update') 监听"
    func_start = src.index("function", m.start())
    open_i = src.index("{", func_start)
    depth = 0
    for i in range(open_i, len(src)):
        c = src[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return src[func_start:i + 1]
    raise AssertionError("on('profile.update') 括号不闭合")


def _run_node(js: str) -> str:
    r = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        raise AssertionError(f"node 执行失败: {r.stderr}")
    return r.stdout


# ── F20-1：静态断言（图标/标签/监听）───────────────────────────────────

def test_f20_1_static_mappings_and_listener():
    src = GUI_FILE.read_text(encoding="utf-8")

    # TOOL_ICONS 含 profile_update 键，SVG 风格合规（14×14 / 1.25px / round / currentColor）
    assert "'profile_update':" in src, "TOOL_ICONS 缺 profile_update 键"
    m = re.search(
        r"'profile_update':\s*'<svg class=\"tool-ic\" viewBox=\"0 0 14 14\" width=\"14\" height=\"14\" "
        r"fill=\"none\" stroke=\"currentColor\" stroke-width=\"1\.25\" stroke-linecap=\"round\" "
        r"stroke-linejoin=\"round\"",
        src,
    )
    assert m, "profile_update SVG 风格不合规（须 14×14 / 1.25px / round / currentColor）"

    # TOOL_LABELS（实际变量名 TOOL_FRIENDLY）映射
    assert "'profile_update': 'Edit profile'" in src, "TOOL_LABELS 缺 'profile_update': 'Edit profile'"

    # on('profile.update') 监听存在
    assert "on('profile.update', function(data)" in src, "缺 on('profile.update') 监听"


def test_f20_2_lightweight_card_and_css():
    src = GUI_FILE.read_text(encoding="utf-8")
    handler = _extract_profile_update_handler(src)

    # 轻量卡：不走 addTool 完整工具卡逻辑（无 tool_id/状态/toggle）
    assert "addTool(" not in handler, "档案更新卡不应走 addTool 完整工具卡逻辑"
    assert "tool_id" not in handler, "profile.update 事件无 tool_id，不应引用"
    # diff 复用 diffBlock()
    assert "diffBlock(" in handler, "档案更新卡应复用 diffBlock() 渲染 diff"

    # CSS 纯新增：.profile-update-card 存在 + 复用既有 .diff-block
    assert ".profile-update-card" in src, "缺 .profile-update-card class"
    assert ".profile-update-card .diff-block" in src, "diff 块应复用既有 .diff-block"


# ── F20-3：node 桩实跑（事件 → 工具卡出现在 chatEl）───────────────────

def test_f20_3_node_renders_profile_card():
    src = GUI_FILE.read_text(encoding="utf-8")
    diff_block = _extract_func(src, "diffBlock")
    handler = _extract_profile_update_handler(src)

    js = r"""
var _handlers = {};
function on(ev, fn) { _handlers[ev] = fn; }
// ── DOM 桩 ──
function makeEl(tag) {
  return { tagName: (tag || 'div').toUpperCase(), className: '', innerHTML: '', children: [],
    attrs: {}, setAttribute: function(k, v) { this.attrs[k] = v; },
    appendChild: function(c) { this.children.push(c); return c; } };
}
var document = { createElement: function(t) { return makeEl(t); } };
var chatEl = { children: [], scrollTop: 0, scrollHeight: 10,
  appendChild: function(c) { this.children.push(c); this.scrollTop = this.scrollHeight; } };
// ── 依赖桩 ──
function isForeignSession(d) { return false; }
function esc(s) { return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
function toolIcon(n) { return n === 'profile_update' ? '<svg class="tool-ic"></svg>' : ''; }
""" + diff_block + "\n" + "_handlers['profile.update'] = " + handler + ";\n" + r"""
_handlers['profile.update']({ category: 'preference', entry: '用户偏好直接执行工具调用', diff: '+ 用户偏好直接执行工具调用，不说明、不道歉。\n- 旧值' });
var card = chatEl.children[0];
console.log('NODE_F20_3 ' + JSON.stringify({
  count: chatEl.children.length,
  cls: card ? card.className : null,
  dataTool: card ? card.attrs['data-tool'] : null,
  titleHtml: card ? card.innerHTML : null,
  diffCls: card && card.children[0] ? card.children[0].className : null,
  diffHtml: card && card.children[0] ? card.children[0].innerHTML : null
}));
"""
    out = _run_node(js)
    m = re.search(r"NODE_F20_3 (\{.*\})", out)
    assert m, f"未输出 NODE_F20_3 标记: {out}"
    st = json.loads(m.group(1))

    assert st["count"] == 1, "应渲染 1 张档案更新卡"
    assert st["cls"] == "profile-update-card"
    assert st["dataTool"] == "profile_update"
    # 图标 + 标题
    assert "tool-ic" in st["titleHtml"], "卡片应含图标"
    assert "Edit profile" in st["titleHtml"], "卡片应含 Edit profile 标题"
    # diff 复用 diffBlock：红绿块
    assert st["diffCls"] == "profile-update-diff"
    assert "diff-block" in st["diffHtml"]
    assert "dl add" in st["diffHtml"], "diff 应含 + 绿块"
    assert "dl del" in st["diffHtml"], "diff 应含 - 红块"


# ── F20-4：node 桩实跑（空 payload 不渲染）─────────────────────────────

def test_f20_4_node_empty_payload_no_card():
    src = GUI_FILE.read_text(encoding="utf-8")
    diff_block = _extract_func(src, "diffBlock")
    handler = _extract_profile_update_handler(src)

    js = r"""
var _handlers = {};
function on(ev, fn) { _handlers[ev] = fn; }
function makeEl(tag) {
  return { tagName: (tag || 'div').toUpperCase(), className: '', innerHTML: '', children: [],
    attrs: {}, setAttribute: function(k, v) { this.attrs[k] = v; },
    appendChild: function(c) { this.children.push(c); return c; } };
}
var document = { createElement: function(t) { return makeEl(t); } };
var chatEl = { children: [], scrollTop: 0, scrollHeight: 10,
  appendChild: function(c) { this.children.push(c); this.scrollTop = this.scrollHeight; } };
function isForeignSession(d) { return false; }
function esc(s) { return String(s); }
function toolIcon(n) { return ''; }
""" + diff_block + "\n" + "_handlers['profile.update'] = " + handler + ";\n" + r"""
_handlers['profile.update']({ category: 'preference', entry: '', diff: '' });
console.log('NODE_F20_4 ' + JSON.stringify({ count: chatEl.children.length }));
"""
    out = _run_node(js)
    m = re.search(r"NODE_F20_4 (\{.*\})", out)
    assert m, f"未输出 NODE_F20_4 标记: {out}"
    st = json.loads(m.group(1))
    assert st["count"] == 0, "空 payload 不应渲染工具卡"
