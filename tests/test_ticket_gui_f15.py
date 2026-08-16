"""票 GUI-F15 专项测试：Plugin 区三个老图标 emoji → 细线 SVG（Telescope 同款工艺）。

票面验收口径（全部实跑）：
- G1  plugins 数组四项 icon 均含 <svg 且不含 emoji 正则区间字符
- G2  SVG 五属性齐全（fill / stroke / stroke-width / viewBox / aria-hidden），
      且与 Telescope 同款工艺（0 0 16 16 / none / currentColor / 1.25）
- G3  telescope 项零改动（与 rollback/pre-gui-f15 标签基线逐字一致）
- G4  node --check 通过（提取 <script> 内容实跑，防 SVG 破坏 JS 结构）
- G5  plugins 数组恰好 4 项（实弹验收 #plugin-list .pitem = 4 的静态前提）
"""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GUI_FILE = ROOT / "apps" / "desktop" / "dist" / "index.html"
TAG = "rollback/pre-gui-f15"

# emoji 正则区间（含杂项符号 + 变体选择符）：命中即视为 emoji
EMOJI_RE = re.compile(
    r"[\U0001F300-\U0001FAFF\u2600-\u27BF\uFE0F\u2B50\u2764]"
)

# Telescope 同款工艺五属性（严格子串匹配）
FIVE_ATTRS = (
    'viewBox="0 0 16 16"',
    'fill="none"',
    'stroke="currentColor"',
    'stroke-width="1.25"',
    'aria-hidden="true"',
)


def _plugins_icons(src: str) -> list[tuple[str, str]]:
    """提取 plugins 数组每一项的 (id, icon)。"""
    m = re.search(r"var plugins = \[(.*?)\];", src, re.S)
    assert m, "未找到 plugins 数组"
    body = m.group(1)
    items = re.findall(r"\{ id:'(\w+)', icon:'([^']*)'", body)
    assert len(items) >= 1, f"plugins 数组解析失败: {body[:200]}"
    return items


def _git_show(path_in_tag: str) -> str:
    r = subprocess.run(["git", "show", f"{TAG}:{path_in_tag}"],
                       capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, f"git show {TAG} 失败: {r.stderr}"
    return r.stdout


# ── G1：四项 icon 均含 <svg 且无 emoji ──

def test_g1_four_icons_all_svg_no_emoji():
    src = GUI_FILE.read_text(encoding="utf-8")
    icons = _plugins_icons(src)
    assert len(icons) == 4, f"plugins 应 4 项，实际 {len(icons)}"
    for pid, icon in icons:
        assert "<svg" in icon, f"{pid} icon 不是 SVG: {icon[:80]}"
        assert not EMOJI_RE.search(icon), f"{pid} icon 含 emoji: {icon[:80]}"


# ── G2：SVG 五属性齐全（Telescope 同款工艺） ──

def test_g2_five_attrs_present():
    src = GUI_FILE.read_text(encoding="utf-8")
    for pid, icon in _plugins_icons(src):
        for attr in FIVE_ATTRS:
            assert attr in icon, f"{pid} icon 缺属性 {attr}: {icon[:120]}"


# ── G3：telescope 项零改动（对照回滚标签基线） ──

def test_g3_telescope_untouched():
    base = _git_show("apps/desktop/dist/index.html")
    src = GUI_FILE.read_text(encoding="utf-8")
    m_base = re.search(r"\{ id:'telescope', icon:'[^']*'", base)
    m_now = re.search(r"\{ id:'telescope', icon:'[^']*'", src)
    assert m_base and m_now, "telescope 行未找到"
    assert m_base.group(0) == m_now.group(0), "telescope 项被改动，违反票面约束"


# ── G4：node --check 通过（提取 <script> 实跑） ──

def test_g4_node_check_passes():
    src = GUI_FILE.read_text(encoding="utf-8")
    scripts = re.findall(r"<script[^>]*>(.*?)</script>", src, re.S)
    assert len(scripts) >= 1, "未找到 script 块"
    tmp = Path("/tmp/gui_f15_test_check.js")
    tmp.write_text("\n".join(scripts), encoding="utf-8")
    r = subprocess.run(["node", "--check", str(tmp)],
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, f"node --check 失败: {r.stderr[:500]}"


# ── G5：恰好 4 项（实弹验收静态前提） ──

def test_g5_exactly_four_plugins():
    src = GUI_FILE.read_text(encoding="utf-8")
    icons = _plugins_icons(src)
    assert len(icons) == 4, f"plugins 应恰好 4 项，实际 {len(icons)}: {[i for i, _ in icons]}"
    ids = [i for i, _ in icons]
    assert ids == ["notes", "project", "terminal", "telescope"], f"插件顺序/id 异常: {ids}"
