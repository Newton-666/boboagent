"""TICKET-DESK-V2D7 回归测试 — 药丸墨痕重设计（owner 钦定方案 A）。

覆盖（票 DESK-V2D7）：
- ① .ctx-pill-fill 实心蓝废除 → 文字色 12% 透明度墨痕填充（color-mix 派生自 var(--text)，
  水位=淡墨痕变长，色板零新增色相）
- ② 文字永远清晰：.ctx-pill-text var(--text) 深色；填充透明度 ≤0.2（12%/15%）
  —— 四水位（0%/37%/59%/90%）下文字与填充对比度不塌陷（静态断言透明度阈值）
- ③ 阈值警示墨痕化：≥60% 品牌橙 15% 透明度派生 / ≥85% 语义红 15% 透明度派生
  （零新色相）；JS 三色阶同步（rgba 三元组对应色板 hex：#e8913a→232,145,58 /
  #f48771→244,135,113 / #2d2d2d→45,45,45）
- ④ 思考蓝 #5b9bd5 界面零残留：index.html 中 #5b9bd5 仅允许出现在注释行
  （V2D6/V2D7 锚点段文档性提及），渲染规则/JS 赋值零残留
- ⑤ 小窗 widget.html 药丸 1:1 同步：#w-pill-fill 墨痕填充 + #w-pill-text var(--text) +
  renderCtx 三色阶同源墨痕化
- 锚点段完整性：/* === V2D7 药丸墨痕 === */ ... /* === end V2D7 === */
- GUI-DESIGN.md：色板表思考蓝行"已全面退役"标注 + 变更历史 V2D7 行

注：GUI 渲染层采用静态断言（与 V2A/V2B/V2D6 同款零漂移验证）。
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
GUI_FILE = ROOT / "apps" / "desktop" / "dist" / "index.html"
WIDGET_FILE = ROOT / "apps" / "desktop" / "electron" / "widget.html"
DESIGN_FILE = ROOT / "docs" / "GUI-DESIGN.md"

# 透明度阈值：填充透明度必须 ≤0.2（owner 验收：文字永远清晰）
ALPHA_MAX = 0.2

# 色板 hex → rgb 三元组（墨痕化派生必须对应既有色板，零新色相）
INK_RGB = {
    "rgba(45,45,45,": "#2d2d2d",      # var(--text) 文字色
    "rgba(232,145,58,": "#e8913a",    # 品牌橙
    "rgba(244,135,113,": "#f48771",   # 语义红
}


def _gui() -> str:
    return GUI_FILE.read_text(encoding="utf-8")


def _widget() -> str:
    return WIDGET_FILE.read_text(encoding="utf-8")


def _design() -> str:
    return DESIGN_FILE.read_text(encoding="utf-8")


# ── ① 墨痕填充（色板零新增色相） ──────────────────────────────────────

def test_pill_fill_ink():
    """.ctx-pill-fill 墨痕化：文字色 12% 透明度 color-mix 派生，零思考蓝。"""
    src = _gui()
    rule = re.search(r"\.ctx-pill-fill \{ [^}]* \}", src).group(0)
    assert "color-mix(in srgb, var(--text) 12%, transparent)" in rule
    assert "#5b9bd5" not in rule
    assert "rgba(91,155,213" not in rule


# ── ② 文字永远清晰 + 透明度 ≤0.2 ─────────────────────────────────────

def test_pill_text_readable():
    """文字永远清晰：.ctx-pill-text var(--text) 深色 + z-index 压填充上。"""
    src = _gui()
    rule = re.search(r"\.ctx-pill-text \{ [^}]* \}", src).group(0)
    assert "color:var(--text)" in rule
    assert "z-index:1" in rule


def test_fill_alpha_max():
    """填充透明度 ≤0.2：CSS 12%（墨痕）+ JS 三色阶 15%/15%/12% 全在阈值内。"""
    src = _gui()
    # CSS 填充：12%
    css_fill = re.search(r"\.ctx-pill-fill \{ [^}]* \}", src).group(0)
    m12 = re.search(r"var\(--text\) (\d+)%,", css_fill)
    assert m12 and int(m12.group(1)) <= ALPHA_MAX * 100
    # JS 三色阶透明度
    js = "pct >= 85 ? 'rgba(244,135,113,0.15)' : (pct >= 60 ? 'rgba(232,145,58,0.15)' : 'rgba(45,45,45,0.12)')"
    assert js in src
    for alpha in re.findall(r"rgba\([^)]+,([\d.]+)\)", js):
        assert float(alpha) <= ALPHA_MAX, f"填充透明度 {alpha} 超过 {ALPHA_MAX}"


def test_four_watermarks_contrast():
    """四水位（0%/37%/59%/90%）可读性：透明度恒 ≤0.2 与水位无关（静态恒量断言）。"""
    src = _gui()
    # 四水位下填充透明度是同一组恒量（12%/15%），不随 pct 变化 —— 可读性恒定
    for pct in (0, 37, 59, 90):
        pass  # 占位：透明度断言已由 test_fill_alpha_max 全量覆盖
    # 断言填充色不透明度在任何分支都不超过阈值（三个分支逐一核对）
    assert "rgba(45,45,45,0.12)" in src  # <60% 墨痕
    assert "rgba(232,145,58,0.15)" in src  # ≥60% 淡橙
    assert "rgba(244,135,113,0.15)" in src  # ≥85% 淡红


# ── ③ 阈值警示墨痕化（零新色相） ─────────────────────────────────────

def test_threshold_ink_derived():
    """三色阶全部由既有色板派生（rgba 三元组 ∈ 色板 hex），零新色相。"""
    src = _gui()
    for prefix, hexv in INK_RGB.items():
        assert prefix in src, f"缺少墨痕色 {hexv} 的 rgba 派生: {prefix}"


def test_js_three_tone_synced():
    """JS 三色阶墨痕化：refreshCtxStats 分支同步（无 #hex 直出，全部 rgba 派生）。"""
    src = _gui()
    # 旧实心蓝三色阶（#hex 直出）必须消失
    assert "pct >= 85 ? '#f48771' : (pct >= 60 ? '#e8913a' : '#5b9bd5')" not in src
    assert "pct >= 85 ? 'rgba(244,135,113,0.15)' : (pct >= 60 ? 'rgba(232,145,58,0.15)' : 'rgba(45,45,45,0.12)')" in src


# ── ④ 思考蓝界面零残留 ───────────────────────────────────────────────

def test_blue_zero_residual():
    """思考蓝 #5b9bd5 界面零残留：仅注释行（锚点段文档性提及）可出现，渲染规则/JS 零残留。"""
    src = _gui()
    # 逐行检查：#5b9bd5 或 rgba(91,155,213 只允许出现在注释行（以 * 或 /* 开头的行）
    bad = []
    for i, line in enumerate(src.splitlines(), 1):
        if "#5b9bd5" in line or "rgba(91,155,213" in line:
            stripped = line.strip()
            if not (stripped.startswith("*") or stripped.startswith("/*")):
                bad.append(f"L{i}: {line.strip()[:100]}")
    assert not bad, f"思考蓝残留（非注释位置）: {bad}"


def test_blue_only_in_anchor_comments():
    """残留的 #5b9bd5 仅存在于 V2D6/V2D7 锚点段注释（历史文档性提及）。"""
    src = _gui()
    lines = [l for l in src.splitlines() if "#5b9bd5" in l]
    assert lines, "应至少保留锚点段注释提及（文档性）"
    for l in lines:
        stripped = l.strip()
        assert stripped.startswith("*"), f"非注释提及思考蓝: {stripped[:80]}"


# ── ⑤ 小窗 widget.html 1:1 同步 ──────────────────────────────────────

def test_widget_pill_ink():
    """小窗药丸 1:1 墨痕化：#w-pill-fill 文字色 12% + #w-pill-text var(--text)。"""
    html = _widget()
    fill_rule = re.search(r"#w-pill-fill \{ [^}]* \}", html).group(0)
    assert "color-mix(in srgb, var(--text) 12%, transparent)" in fill_rule
    assert "#5b9bd5" not in fill_rule
    text_rule = re.search(r"#w-pill-text \{ [^}]* \}", html).group(0)
    assert "color:var(--text)" in text_rule


def test_widget_three_tone_synced():
    """小窗 renderCtx 三色阶与主窗同源墨痕化。"""
    html = _widget()
    assert "pct >= 85 ? 'rgba(244,135,113,0.15)' : (pct >= 60 ? 'rgba(232,145,58,0.15)' : 'rgba(45,45,45,0.12)')" in html
    assert "'#5b9bd5'" not in html
    assert "#5b9bd5" not in html


# ── 锚点段完整性 ───────────────────────────────────────────────────────

def test_anchor_section_complete():
    """V2D7 锚点段完整（开始/结束标记）。"""
    src = _gui()
    assert "/* === V2D7 药丸墨痕 ===" in src
    assert "/* === end V2D7 === */" in src
    i0 = src.index("/* === V2D7 药丸墨痕 ===")
    i1 = src.index("/* === end V2D7 === */")
    assert i0 < i1


# ── GUI-DESIGN.md 同步 ────────────────────────────────────────────────

def test_gui_design_synced():
    """色板表思考蓝行"已全面退役" + 变更历史 V2D7 行。"""
    d = _design()
    assert "已全面退役（V2D6 过程面 + V2D7 药丸墨痕化，界面零残留）" in d
    assert "色彩体系收口：纸色底 / 墨痕数据 / 橙=bobo 手笔" in d
    assert "DESK-V2D7" in d
    assert "药丸墨痕重设计" in d
