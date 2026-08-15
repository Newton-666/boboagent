"""TICKET-DESK-V2D6 回归测试 — 思考框中性化（去 emoji / 去蓝 / 与折叠卡同族）。

覆盖（票 DESK-V2D6）：
- ① 完成态标签纯 thinking：addTool 完成态 innerHTML='thinking' + classList.add('done')
  （.think-box.done 复用 fadeIn 0.2s 淡入，无 opacity 跳变）；历史重放 buildHistThinkBox
  与实时收束折叠标签统一 thinking；渲染产物零 💭、零"思考过程"、零 'Thought'
- ② 思考框去蓝：.think-box 底 var(--bg2)（比页面背景深半阶）/边 var(--border) 发丝线/
  标签 var(--text-muted)；思考中三跳点 .think-dot 弱橙 #e8913a 呼吸"活着"（色板既有品牌橙）
- ③ 折叠聚合卡 .tool-agg 与思考框同族同阶：底 var(--bg2)/边 var(--border)/文字 var(--text2)
  完全相同的一组值——过程性内容一眼同族
- ④ 思考蓝 #5b9bd5 仅保留药丸 <60% 水位（.ctx-pill-fill + JS 三色阶，信息语义）；
  ovl-spinner（连接中）/v2a-loader（加载中）过程动画同步退役为 var(--text2)
- 锚点段完整性：/* === V2D6 思考框中性化 === */ ... /* === end V2D6 === */
- GUI-DESIGN.md：色板表思考蓝行语义迁移标注 / 组件表思考框行 / 变更历史表 V2D6 行

豁免声明：剥离正则中的 ── 💭 思考过程 ── 为上游 final_text 数据分隔符契约
（兼容历史数据，改了匹配不到），不在"渲染标签"断言范围内，明确豁免。

注：GUI 渲染层采用静态断言 + node 实跑（与 V2A/V2B 同款零漂移验证）。
"""

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
GUI_FILE = ROOT / "apps" / "desktop" / "dist" / "index.html"
DESIGN_FILE = ROOT / "docs" / "GUI-DESIGN.md"


def _gui() -> str:
    return GUI_FILE.read_text(encoding="utf-8")


def _design() -> str:
    return DESIGN_FILE.read_text(encoding="utf-8")


def _run_node(js: str) -> str:
    r = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        raise AssertionError(f"node 执行失败: {r.stderr}")
    return r.stdout


def _extract_func(src: str, fname: str) -> str:
    """按 { } 括号配对提取 function <fname> 的完整源码。"""
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


# ── ① 完成态标签纯 thinking（无 emoji 无中文） ──────────────────────────

def test_label_completed_pure_thinking():
    """addTool 完成态：标签纯 thinking + classList.add('done') 淡入，无 'Thought' 无 opacity 跳变。"""
    src = _gui()
    assert "thinkBoxEl.querySelector('.think-label').innerHTML = 'thinking';" in src
    assert "thinkBoxEl.classList.add('done');" in src
    assert "innerHTML = 'Thought'" not in src
    assert "thinkBoxEl.style.opacity = '0.6'" not in src


def test_label_hist_replay_pure_thinking():
    """历史重放与实时收束折叠标签统一 thinking；渲染产物零 💭 零"思考过程"。"""
    src = _gui()
    assert src.count("<span>thinking</span>") >= 2  # buildHistThinkBox + 收束折叠
    # 渲染产物层面（innerHTML 赋值）不得再出现旧标签
    assert "<span>💭 思考过程</span>" not in src
    assert "💭 思考过程" not in src.replace("💭", "")  # 兜底：任何含 💭 思考过程 的渲染产物
    # 思考中标签保持 Thinking + 三跳点不变
    assert "<span>Thinking</span>" in src


def test_fadein_02s_no_jump():
    """.think-box.done 复用 fadeIn 0.2s 淡入；无跳变（无 opacity 硬切）。"""
    src = _gui()
    assert ".think-box.done { animation:fadeIn 0.2s ease-out; }" in src
    assert "@keyframes fadeIn" in src


# ── ② 思考框去蓝（同族不同阶） ─────────────────────────────────────────

def test_thinkbox_deblued():
    """思考框底/边/标签全部迁米白灰系，零思考蓝残留。"""
    src = _gui()
    assert "background:var(--bg2)" in src          # 底：比页面背景 --bg 深半阶
    assert "border:1px solid var(--border)" in src  # 边：发丝线
    assert "color:var(--text-muted)" in src         # 标签：muted 灰
    # think-box 规则内不得再有思考蓝
    thinkbox_rule = re.search(r"\.think-box \{ [^}]* \}", src).group(0)
    assert "rgba(91,155,213" not in thinkbox_rule
    assert "#5b9bd5" not in thinkbox_rule
    thinklabel_rule = re.search(r"\.think-box \.think-label \{ [^}]* \}", src).group(0)
    assert "#5b9bd5" not in thinklabel_rule
    thinkdot_rule = re.search(r"\.think-dot \{ [^}]* \}", src).group(0)
    assert "#5b9bd5" not in thinkdot_rule
    assert "#e8913a" in thinkdot_rule  # 思考中弱橙呼吸"活着"


# ── ③ 折叠聚合卡同族同阶 ──────────────────────────────────────────────

def test_tool_agg_same_family_same_grade():
    """.tool-agg 与 .think-box 底/边完全同组值（同族同阶）。"""
    src = _gui()
    tool_agg = re.search(r"\.tool-agg \{ [^}]* \}", src).group(0)
    thinkbox = re.search(r"\.think-box \{ [^}]* \}", src).group(0)
    assert "background:var(--bg2)" in tool_agg
    assert "border:1px solid var(--border)" in tool_agg
    assert "background:var(--bg2)" in thinkbox
    assert "border:1px solid var(--border)" in thinkbox
    # 文字同族：tool-agg-head 用 var(--text2)
    assert ".tool-agg-head" in src and "color:var(--text2)" in src


# ── ④ 思考蓝全面退役（V2D7 收口）；过程动画退役 ────────────────────────

def test_pill_ink_marks():
    """V2D7 药丸墨痕化：填充=文字色 12% 透明度（color-mix 派生），透明度 ≤0.2，三色阶墨痕化（零思考蓝）。"""
    src = _gui()
    assert ".ctx-pill-fill" in src
    pill_rule = re.search(r"\.ctx-pill-fill \{ [^}]* \}", src).group(0)
    assert "color-mix(in srgb, var(--text) 12%, transparent)" in pill_rule
    assert "#5b9bd5" not in pill_rule
    # JS 三色阶：<60% 文字墨痕 12% / ≥60% 品牌橙 15% / ≥85% 语义红 15%（透明度均 ≤0.2）
    assert "pct >= 85 ? 'rgba(244,135,113,0.15)' : (pct >= 60 ? 'rgba(232,145,58,0.15)' : 'rgba(45,45,45,0.12)')" in src
    # 文字永远清晰：药丸文字 var(--text) 深色
    text_rule = re.search(r"\.ctx-pill-text \{ [^}]* \}", src).group(0)
    assert "color:var(--text)" in text_rule


def test_process_animations_deblued():
    """过程性动画（连接中 ovl-spinner / 加载中 v2a-loader）思考蓝退役为 --text2。"""
    src = _gui()
    ovl = re.search(r"\.ovl-spinner span \{ [^}]* \}", src).group(0)
    assert "background:var(--text2)" in ovl
    assert "#5b9bd5" not in ovl
    v2a = re.search(r"\.v2a-loader \.sp span \{ [^}]* \}", src).group(0)
    assert "background:var(--text2)" in v2a
    assert "#5b9bd5" not in v2a


# ── 锚点段完整性 ───────────────────────────────────────────────────────

def test_anchor_section_complete():
    """V2D6 锚点段完整（开始/结束标记 + .think-box.done 规则）。"""
    src = _gui()
    assert "/* === V2D6 思考框中性化 ===" in src
    assert "/* === end V2D6 === */" in src
    i0 = src.index("/* === V2D6 思考框中性化 ===")
    i1 = src.index("/* === end V2D6 === */")
    assert i0 < i1
    assert ".think-box.done { animation:fadeIn 0.2s ease-out; }" in src[i0:i1]


# ── GUI-DESIGN.md 同步标注 ─────────────────────────────────────────────

def test_gui_design_synced():
    """色板表思考蓝行语义迁移（V2D7 收口） / 组件表思考框行 / 变更历史 V2D6 行。"""
    d = _design()
    assert "已全面退役（V2D6 过程面 + V2D7 药丸墨痕化，界面零残留）" in d
    assert "米白灰框" in d
    assert "DESK-V2D6" in d
    assert "思考框中性化" in d


# ── node 实跑：buildHistThinkBox 渲染产物零 emoji 零中文 ────────────────

def test_node_hist_thinkbox_render():
    """node 实跑 buildHistThinkBox：返回标签纯 thinking，无 💭 无中文。"""
    src = _gui()
    func = _extract_func(src, "buildHistThinkBox")
    js = r"""
var captured = null;
var fakeTxt = { textContent: '' };
var fakeEl = {
  className: '', innerHTML: '',
  querySelector: function (sel) {
    if (sel === '.think-text') return fakeTxt;
    return null;
  }
};
global.document = { createElement: function () { return fakeEl; } };
eval(%r);
var tb = buildHistThinkBox('sample');
captured = tb.innerHTML;
console.log(captured);
""" % func
    out = _run_node(js)
    assert "thinking" in out
    assert "💭" not in out
    assert "思考" not in out
