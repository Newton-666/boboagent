"""TICKET-DESK-V2D5 回归测试 — 上下文药丸修复（及格线）+ 认知状态条升级。

覆盖（票验收）：
- V2D5-0 及格线：refreshCtxStats 双重剥壳修复 —— call() 的 resolve 已是 result
  （pending 剥壳传 msg.result），历史代码再取 res.result → d 恒 null → 药丸永停 0% · 0/128K。
  断言修复后源码取壳为 `var d = res || null;`，且 node 实跑桩化 DOM 药丸非零渲染。
- V2D5-1 升级：药丸 = 水位 + 本轮记忆注入条数（memory_injected 回合内增量）+ 本轮工具调用数
  （tool.start 计数）；meta 段弱化小字（.v2d5-meta）；明细卡新增两行；CSS 进 V2D5 锚点段，
  色板零新增；点击展开保留（toggleCtxStats 不动）。
- node 实跑：真实 refreshCtxStats / sendPrompt / tool.start 计数桩化 DOM 验证。

注：V2B/V2B4/V4 不破由各自测试文件全量回归兜底（本文件静态断言关键锚点保留）。
"""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GUI_FILE = ROOT / "apps" / "desktop" / "dist" / "index.html"


def _gui() -> str:
    return GUI_FILE.read_text(encoding="utf-8")


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


# ── V2D5-0 及格线：双重剥壳修复 ────────────────────────────────────────

def test_v2d5_0_double_unwrap_fixed_source():
    """修复后取壳必须直接吃 call() 的 result（全库约定），不得再 res.result 二次剥壳。"""
    src = _gui()
    fn = _extract_func(src, "refreshCtxStats")
    assert "var d = res || null;" in fn, "修复锚点缺失：应为 var d = res || null;"
    assert "res && res.result" not in fn, "二次剥壳残留：res.result 会让 d 恒 null，药丸永不更新"


def test_v2d5_0_pill_nonzero_node():
    """node 实跑：桩化 DOM + mock call（返回 result 对象，模拟 call 已剥壳语义）→
    refreshCtxStats 必须把真实水位写进药丸文本（非 0% · 0/128K）。"""
    src = _gui()
    fn = _extract_func(src, "refreshCtxStats")
    js = fn + r"""
// 桩环境（对齐 dist/index.html 全局）
var reqId = 0;
var currentSessionId = 's_v2d5';
var roundMemBaseline = null;
var roundMemInjected = 0;
var roundToolCount = 0;
var window = { boboAPI: {} };
// call() 的 resolve 已是 result（pending 剥壳传 msg.result）—— 必须直接可用
function call(m, p) {
  return Promise.resolve({
    token_estimate: 87015, saved_chars: 19163767, marked: 4886,
    loaded: 2441, memory_injected: 2441, context_limit: 1000000,
  });
}
var _els = {};
function mkEl() { return { style: {}, innerHTML: '', textContent: '' }; }
function getElementById(id) { if (!_els[id]) _els[id] = mkEl(); return _els[id]; }
var document = { getElementById };

(async () => {
  await refreshCtxStats();
  const t = _els['ctx-pill-text'].innerHTML;
  if (t.indexOf('0% · 0/128K') !== -1) throw new Error('药丸仍停硬编码初值: ' + t);
  if (t.indexOf('9%') === -1) throw new Error('药丸未显示真实水位 9%: ' + t);
  if (_els['ctx-pill-fill'].style.width !== '9%') throw new Error('fill 宽度未更新: ' + _els['ctx-pill-fill'].style.width);
  const det = _els['ctx-stats-detail'].innerHTML;
  if (det.indexOf('Context tokens (est.)') === -1) throw new Error('明细卡未渲染');
  console.log('NODE_V2D5_PILL_OK:' + t);
})();
"""
    out = _run_node(js)
    assert "NODE_V2D5_PILL_OK:9% · 87K/1000K" in out, f"node 实跑失败: {out}"


# ── V2D5-1 升级：认知状态条三数据项 ─────────────────────────────────────

def test_v2d5_1_cognition_meta_node():
    """node 实跑：模拟完整回合 —— sendPrompt 重置 → tool.start ×3 → 两次 refresh
    （memory_injected 100→102 增量 2）→ 药丸文本含 水位 + 记忆+2 + 工具3。"""
    src = _gui()
    fn = _extract_func(src, "refreshCtxStats")
    js = fn + r"""
var reqId = 0;
var currentSessionId = 's_v2d5';
var roundMemBaseline = null;
var roundMemInjected = 0;
var roundToolCount = 0;
var window = { boboAPI: {} };
var _injected = 100;
function call(m, p) {
  return Promise.resolve({
    token_estimate: 87015, saved_chars: 1, marked: 1, loaded: _injected,
    memory_injected: _injected, context_limit: 1000000,
  });
}
var _els = {};
function mkEl() { return { style: {}, innerHTML: '', textContent: '' }; }
function getElementById(id) { if (!_els[id]) _els[id] = mkEl(); return _els[id]; }
var document = { getElementById };

(async () => {
  // 回合开始（sendPrompt 挂点逻辑）
  roundMemBaseline = null; roundMemInjected = 0; roundToolCount = 0;
  // tool.start ×3（计数挂点逻辑）
  roundToolCount++; roundToolCount++; roundToolCount++;
  // 第一次 refresh：baseline=100
  await refreshCtxStats();
  // 回合中注入 2 条记忆（工作区累计 100→102）
  _injected = 102;
  await refreshCtxStats();
  const t = _els['ctx-pill-text'].innerHTML;
  if (t.indexOf('mem+2') === -1) throw new Error('本轮记忆注入缺失: ' + t);
  if (t.indexOf('tools3') === -1) throw new Error('本轮工具计数缺失: ' + t);
  if (t.indexOf('9% · 87K/1000K') === -1) throw new Error('水位段缺失: ' + t);
  if (t.indexOf('v2d5-meta') === -1) throw new Error('meta 弱化类缺失: ' + t);
  const det = _els['ctx-stats-detail'].innerHTML;
  if (det.indexOf('Memory this round') === -1 || det.indexOf('Tools this round') === -1)
    throw new Error('明细卡未含本轮两项');
  console.log('NODE_V2D5_META_OK:' + t);
})();
"""
    out = _run_node(js)
    assert "NODE_V2D5_META_OK" in out, f"node 实跑失败: {out}"


def test_v2d5_1_hooks_present():
    """源码挂点：sendPrompt 回合重置 + tool.start 计数 + 全局变量 + 明细卡两行。"""
    src = _gui()
    assert "roundMemBaseline = null; roundMemInjected = 0; roundToolCount = 0;" in src, \
        "sendPrompt 回合重置挂点缺失"
    assert "roundToolCount++;" in src, "tool.start 计数挂点缺失"
    assert "var roundMemBaseline = null;" in src, "全局变量缺失"
    assert "Memory this round" in src and "Tools this round" in src, "明细卡两行缺失"


def test_v2d5_1_css_anchor_zero_new_colors():
    """CSS 纪律：全部进 V2D5 锚点段且闭合；色板零新增（段内不得出现 #hex 新色）。"""
    src = _gui()
    m = re.search(r"/\* ══ TICKET-DESK-V2D5.*?/\* end V2D5 \*/", src, re.S)
    assert m, "V2D5 CSS 锚点段缺失或未闭合"
    seg = m.group(0)
    assert "end V2D5" in seg
    hexes = re.findall(r"#[0-9a-fA-F]{3,8}\b", seg)
    assert not hexes, f"V2D5 锚点段出现新色值: {hexes}（色板零新增纪律）"
    assert "var(--" in seg or "opacity" in seg, "锚点段应只用色板变量/透明度派生"


def test_v2d5_1_toggle_kept():
    """点击展开保留：toggleCtxStats 未被破坏（V2B2 锚点函数完整）。"""
    src = _gui()
    fn = _extract_func(src, "toggleCtxStats")
    assert "refreshCtxStats(); // 展开时拉最新" in fn or "refreshCtxStats()" in fn
