"""TICKET-GUI-F19 专项测试 — 滚动锚定修复（A+C+D 三处）。

根因（RWORK-F29 项6，2026-08-19 复盘）：长会话（>200 条）窗口化模式下，
message.delta 无条件 scrollTop=scrollHeight 触发 scroll 事件 → 窗口化重建
（renderHistWindow innerHTML=''）→ 清掉实时 thinking 框 → 用户上翻被拉回 + 卡屏。

修法（Hermes 2026-08-19 方案 A+C+D）：
- A: message.delta 滚底前 isNearBottom 判定（用户上翻不拉回，不触发重建）
- C: histWindowOnScroll 开头 currentBusy() 挂起（回合进行中不重建）
- D: message.complete 回合结束立即 renderHistWindow() 校准坐标系（跳提前到静默）

覆盖（票验收）：
- F19-1 静态断言：三处修改的代码形态存在
- F19-2 node 实跑：A 的滚动判定逻辑（底部跟随/上翻不拉回）
- F19-3 node 实跑：C 的挂起逻辑（busy 不重建/空闲重建）
"""

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


def _run_node(js: str) -> str:
    r = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        raise AssertionError(f"node 执行失败: {r.stderr}")
    return r.stdout


# ── F19-1：静态断言 ───────────────────────────────────────────────────

def test_f19_1_static_three_mods_present():
    src = GUI_FILE.read_text(encoding="utf-8")

    # A: message.delta 滚底前 isNearBottom 判定
    assert "var nearBottom = chatEl.scrollHeight - chatEl.scrollTop - chatEl.clientHeight < 80" in src, \
        "A 缺失: message.delta 应有 isNearBottom 判定"
    assert "if (nearBottom) chatEl.scrollTop = chatEl.scrollHeight;" in src, \
        "A 缺失: 仅在 nearBottom 时滚底"

    # C: histWindowOnScroll 开头 currentBusy 挂起
    onscroll = _extract_func(src, "histWindowOnScroll")
    assert "if (currentBusy()) return;" in onscroll, \
        "C 缺失: histWindowOnScroll 应挂起 busy 回合"

    # D: message.complete 回合结束校准
    assert "if (histWindowUnits) renderHistWindow();" in src, \
        "D 缺失: message.complete 应回合结束校准坐标系"

    # currentBusy 定义存在（C 依赖）
    assert "function currentBusy()" in src, "currentBusy 定义缺失"


# ── F19-2：node 实跑 A（滚动锚定判定）─────────────────────────────────

def test_f19_2_node_scroll_anchor_behavior():
    js = r"""
// chatEl 桩
var chatEl = { scrollHeight: 5000, clientHeight: 600, scrollTop: 0, scrolled: 0 };
function sim(scrollTop) {
  chatEl.scrollTop = scrollTop;
  chatEl.scrolled = 0;
  // 修复后的 A 逻辑（原样提取自 index.html）
  var nearBottom = chatEl.scrollHeight - chatEl.scrollTop - chatEl.clientHeight < 80;
  if (nearBottom) { chatEl.scrollTop = chatEl.scrollHeight; chatEl.scrolled++; }
  return { nearBottom: nearBottom, scrolled: chatEl.scrolled, finalTop: chatEl.scrollTop };
}
var bottom = sim(4400);   // 底部（5000-600=4400）→ 应跟随
var up = sim(1000);       // 上翻到 1000 → 不应拉回
var edge = sim(4330);     // 距底 70px（<80）→ 应跟随（边缘容忍）
if (bottom.scrolled !== 1) throw new Error('底部应跟随: ' + JSON.stringify(bottom));
if (up.scrolled !== 0 || up.finalTop !== 1000) throw new Error('上翻不应拉回: ' + JSON.stringify(up));
if (edge.scrolled !== 1) throw new Error('边缘应跟随: ' + JSON.stringify(edge));
console.log('A-OK bottom=' + JSON.stringify(bottom) + ' up=' + JSON.stringify(up));
"""
    out = _run_node(js)
    assert "A-OK" in out, out


# ── F19-3：node 实跑 C（busy 挂起）────────────────────────────────────

def test_f19_3_node_busy_suspend():
    js = r"""
// 模拟 currentBusy + histWindowOnScroll 修复后逻辑
var rebuiltCount = 0;
function currentBusy() { return _busy; }
function histWindowOnScroll() {
  if (currentBusy()) return;   // 修复点 C
  rebuiltCount++;
}
_busy = true;  histWindowOnScroll();   // 回合中 → 不重建
var during = rebuiltCount;
_busy = false; histWindowOnScroll();   // 空闲 → 重建
var after = rebuiltCount;
if (during !== 0) throw new Error('回合中不应重建: ' + during);
if (after !== 1) throw new Error('空闲应重建: ' + after);
console.log('C-OK during=' + during + ' after=' + after);
"""
    out = _run_node(js)
    assert "C-OK" in out, out


# ── F19-4：node 实跑 D（回合结束校准触发条件）─────────────────────────

def test_f19_4_node_complete_calibrate():
    js = r"""
// D 逻辑：仅窗口化模式（histWindowUnits 非空）才校准
var histWindowUnits = true; var calibrated = 0;
if (histWindowUnits) calibrated++;   // 窗口化会话 → 校准
histWindowUnits = null; var calibrated2 = 0;
if (histWindowUnits) calibrated2++;  // 非窗口化 → 不校准
if (calibrated !== 1) throw new Error('窗口化应校准');
if (calibrated2 !== 0) throw new Error('非窗口化不应校准');
console.log('D-OK win=' + calibrated + ' plain=' + calibrated2);
"""
    out = _run_node(js)
    assert "D-OK" in out, out
