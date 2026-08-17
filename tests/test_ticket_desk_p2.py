"""票 DESK-P2 验收测试：界面文案全英文化 + 欢迎屏极简 + 侧栏折叠图标。

对应票据验收（专项部分）：
  1. 用户可见字符串零中文残留（HTML/JS 注释豁免；backend 匹配数据格式串豁免）
  2. 欢迎屏极简：#welcome-title 36px（Charter 700 不变）；.welcome-sub 已删；
     #sidebar-footer 连接指示（绿点+文字）已删，JS 引用 null 守卫
  3. 侧栏折叠：#sidebar-header 顶部 panel-left 细线 SVG 按钮；点击切 #sidebar.closed；
     折叠后左上角浮动同款图标展开；CSS 全进 /* === DESK-P2 === */ 锚点段
  4. 色板零新增：新增 CSS 内不出现新 hex/rgb 色值
  5. widget.html 文案英文化零残留
"""

import re

from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
INDEX = REPO / "apps" / "desktop" / "dist" / "index.html"
WIDGET = REPO / "apps" / "desktop" / "electron" / "widget.html"

# 数据格式串豁免清单（backend 输出的中文匹配串，按票据边界不动）
EXEMPT_PATTERNS = [
    "── 工作区实况",
    "── 实况对账",
    "工作区实况（收工对账",
    "📋 待人工执行清单",
    "仍在工作",           # backend heartbeat 文本匹配
    "──  思考过程 ──",     # backend 思考段分隔标记
    "加载 N 个工具",       # backend 状态文本匹配
    "准备执行",           # backend 状态文本匹配
    "工具执行完成",       # backend 状态文本匹配
    "正在思考",           # backend 状态文本匹配
    "已用 N/M 步",        # backend 状态文本匹配
    "正在压缩历史上下文",  # backend 状态文本匹配
    "搜索 'x' 跨平台",    # backend 状态文本匹配
    "思考过程",           # backend 思考段分隔标记正则
    "思考结束",           # backend 思考段分隔标记正则
    r"加载 \d+ 个工具",  # backend 状态正则
]


def _strip_comments(src):
    """剥除 /* */、// 行注释、<!-- -->，返回非注释文本（行号保持）。"""
    out = list(src)
    spans = []
    for m in re.finditer(r"/\*.*?\*/", src, re.S):
        spans.append((m.start(), m.end()))
    for m in re.finditer(r"//(?![a-zA-Z]+:)[^\n]*", src):
        spans.append((m.start(), m.end()))
    for m in re.finditer(r"<!--.*?-->", src, re.S):
        spans.append((m.start(), m.end()))
    for a, b in spans:
        for i in range(a, b):
            if src[i] != "\n":
                out[i] = " "
    return "".join(out)


def _visible_chinese_lines(src):
    """返回非注释文本中含中文的行号列表。"""
    clean = _strip_comments(src)
    return [
        i + 1
        for i, ln in enumerate(clean.splitlines())
        if re.search(r"[\u4e00-\u9fff]", ln)
    ]


def _exempt(line_text):
    return any(p in line_text for p in EXEMPT_PATTERNS)


# ═══════════════════════════════════════════════════════════════════════
# ① 文案英文化零残留
# ═══════════════════════════════════════════════════════════════════════

class TestI18nClean:

    def test_index_no_visible_chinese(self):
        """金标准 1：index.html 非注释区零中文（豁免 backend 匹配串除外）。"""
        src = INDEX.read_text(encoding="utf-8")
        lines = src.splitlines()
        offending = []
        for ln in _visible_chinese_lines(src):
            if not _exempt(lines[ln - 1]):
                offending.append((ln, lines[ln - 1].strip()[:80]))
        assert not offending, f"index.html 残留可见中文: {offending}"

    def test_index_key_mappings(self):
        """金标准 2：关键映射逐条落地。"""
        html = INDEX.read_text(encoding="utf-8")
        must_have = [
            ">New chat<",
            'placeholder="Search..."',
            "No sessions yet",
            "No matches",
            ">Delete all<",
            ">⚙ Settings<",
            ">Save &amp; Launch<",
            ">Save<",
            ">Cancel<",
            ">Copy<",
            "✓ Copied",
            "Connecting…",
            "Connection failed",
            ">Retry<",
            ">Reconnect<",
            "⚠ Approval needed",
            "Context tokens (est.)",
            "Context limit",
            ">Delete<",
            ">Preview<",
            ">Details<",
            ">Deny<",
            ">Allow once<",
            "Leave empty for Provider default",
            "Leave empty to auto-detect",
            ">Timeout (s)<",
            "First run — configure API Key",
            ">Widget<",
        ]
        missing = [m for m in must_have if m not in html]
        assert not missing, f"关键映射缺失: {missing}"

    def test_widget_no_visible_chinese(self):
        """金标准 3：widget.html 非注释区零中文。"""
        src = WIDGET.read_text(encoding="utf-8")
        lines = src.splitlines()
        offending = []
        for ln in _visible_chinese_lines(src):
            if not _exempt(lines[ln - 1]):
                offending.append((ln, lines[ln - 1].strip()[:80]))
        assert not offending, f"widget.html 残留可见中文: {offending}"

    def test_widget_key_mappings(self):
        """金标准 4：widget 关键映射落地。"""
        html = WIDGET.read_text(encoding="utf-8")
        must_have = [
            "<title>Bobo Live</title>",
            ">Bobo Live</span>",
            "Follow main",
            ">Approval</span>",
            "<b>Command</b>",
            "<b>Task</b>",
            "No tool calls",
            "Approval pending",
            ">Idle</span>",
            "Pin · ",
            "Pinned: ",
            "Replying…",
            "Reply done",
            "Chat cleared",
            "Backend exited",
        ]
        missing = [m for m in must_have if m not in html]
        assert not missing, f"widget 关键映射缺失: {missing}"


# ═══════════════════════════════════════════════════════════════════════
# ② 欢迎屏极简
# ═══════════════════════════════════════════════════════════════════════

class TestWelcomeMinimal:

    def test_welcome_sub_removed(self):
        """金标准 5：.welcome-sub 元素与 CSS 均已删除。"""
        html = INDEX.read_text(encoding="utf-8")
        assert "welcome-sub" not in html, ".welcome-sub 应已删除（元素+CSS）"

    def test_welcome_title_36px(self):
        """金标准 6：#welcome-title font-size 36px，Charter 700 不变。"""
        css = INDEX.read_text(encoding="utf-8")
        idx = css.find("#welcome-title")
        assert idx != -1, "#welcome-title CSS 规则应存在"
        seg = css[idx:idx + 300]
        assert "font-size:36px" in seg, f"font-size 应为 36px: {seg[:120]}"
        assert "font-weight:700" in seg, "Charter 700 不变"
        assert "var(--font-reply)" in seg, "字体仍走 vendored Charter"

    def test_sidebar_footer_conn_indicator_removed(self):
        """金标准 7：#sidebar-footer 连接指示（绿点+文字）已删，功能按钮保留。"""
        html = INDEX.read_text(encoding="utf-8")
        assert 'id="status-dot"' not in html, "绿点 status-dot 应删除"
        assert 'id="status-text"' not in html, "状态文字 status-text 应删除"
        assert 'id="widget-toggle"' in html, "小组件开关应保留"
        assert 'id="settings-icon"' in html, "设置按钮应保留"

    def test_status_refs_null_safe(self):
        """金标准 8：JS 引用 statusDot/statusText 均带 null 守卫。"""
        html = INDEX.read_text(encoding="utf-8")
        # 删除 DOM 后 getElementById 返回 null，所有使用点必须守卫
        for pat in ["if (statusText)", "if (statusDot)"]:
            assert pat in html, f"缺少 null 守卫: {pat}"


# ═══════════════════════════════════════════════════════════════════════
# ③ 侧栏折叠图标
# ═══════════════════════════════════════════════════════════════════════

class TestSidebarFold:

    def test_collapse_button_in_header(self):
        """金标准 9：#sidebar-header 顶部有折叠按钮（panel-left 细线 SVG）。"""
        html = INDEX.read_text(encoding="utf-8")
        idx = html.find('id="sidebar-header"')
        assert idx != -1, "#sidebar-header 应存在"
        seg = html[idx:idx + 700]
        assert 'id="sidebar-collapse"' in seg, "折叠按钮应在 header 内"
        assert "viewBox=\"0 0 16 16\"" in seg, "SVG viewBox 16"
        assert 'stroke-width="1.25"' in seg, "细线 1.25 工艺"
        assert "svg" in seg and "rect" in seg, "panel-left 图标（rect + 分隔线）"
        assert "onclick=\"toggleSidebar()\"" in seg, "点击调用 toggleSidebar"

    def test_toggle_function(self):
        """金标准 10：toggleSidebar 切换 #sidebar.closed + body.sidebar-collapsed。"""
        html = INDEX.read_text(encoding="utf-8")
        assert "function toggleSidebar()" in html
        assert "classList.toggle('closed')" in html, "切换 closed class"
        assert "sidebar-collapsed" in html, "body 标记用于浮动按钮显隐"

    def test_float_expand_button(self):
        """金标准 11：折叠后左上角浮动展开按钮（同款图标）。"""
        html = INDEX.read_text(encoding="utf-8")
        assert 'id="sidebar-expand-btn"' in html, "浮动展开按钮应存在"
        assert 'onclick="toggleSidebar()"' in html
        assert "body.sidebar-collapsed #sidebar-expand-btn" in html, "折叠时显示浮动按钮"

    def test_css_in_desk_p2_anchor(self):
        """金标准 12：新增 CSS 全进 /* === DESK-P2 === */ 锚点段。"""
        html = INDEX.read_text(encoding="utf-8")
        assert "/* === DESK-P2 === */" in html, "DESK-P2 锚点段应存在"
        assert "/* === end DESK-P2 === */" in html, "锚点段应有结束标记"
        idx_start = html.find("/* === DESK-P2 === */")
        idx_end = html.find("/* === end DESK-P2 === */")
        assert idx_start < idx_end
        seg = html[idx_start:idx_end]
        # 新增规则必须都在锚点段内
        for rule in ["#sidebar-header .sidebar-fold", "#sidebar-expand-btn",
                     "body.sidebar-collapsed #sidebar-expand-btn"]:
            assert rule in seg, f"{rule} 应位于 DESK-P2 锚点段"

    def test_no_new_colors(self):
        """金标准 13：色板零新增 —— DESK-P2 段不出现新色值。"""
        html = INDEX.read_text(encoding="utf-8")
        idx_start = html.find("/* === DESK-P2 === */")
        idx_end = html.find("/* === end DESK-P2 === */")
        seg = html[idx_start:idx_end]
        # 锚点段内允许出现的色值（复用既有品牌色/语义色）
        allowed = {"var(--text)", "var(--text2)", "var(--bg)", "var(--bg2)",
                   "var(--bg3)", "var(--hover)", "var(--border)", "#e8913a"}
        found = set(re.findall(r"#[0-9a-fA-F]{3,6}\b", seg))
        new_colors = found - allowed
        assert not new_colors, f"DESK-P2 段引入新色值: {new_colors}"

    def test_new_chat_after_icon(self):
        """金标准 14：图标行之下依次 New chat → 搜索框 → session 列表。"""
        html = INDEX.read_text(encoding="utf-8")
        idx = html.find('id="sidebar-header"')
        seg = html[idx:idx + 900]
        i_collapse = seg.find('id="sidebar-collapse"')
        i_new = seg.find('id="new-chat"')
        i_search = seg.find('id="session-search"')
        assert 0 <= i_collapse < i_new < i_search, "顺序应为 折叠图标 → New chat → 搜索框"


# ═══════════════════════════════════════════════════════════════════════
# ④ 结构完整性
# ═══════════════════════════════════════════════════════════════════════

class TestStructuralIntegrity:

    def test_js_syntax_ok(self):
        """金标准 15：<script> 块可被 new Function 解析（语法健康）。"""
        import subprocess
        r = subprocess.run(
            ["node", "-e",
             "const fs=require('fs');const s=fs.readFileSync(process.argv[1],'utf8');"
             "[...s.matchAll(/<script>([\\s\\S]*?)<\\/script>/g)].forEach((m,i)=>{"
             "try{new Function(m[1]);}catch(e){console.log('ERR',i,e.message);process.exit(1);}});"
             "console.log('OK');",
             str(INDEX)],
            capture_output=True, text=True, timeout=30,
        )
        assert r.returncode == 0, f"index.html JS 语法错误: {r.stdout}{r.stderr}"

    def test_widget_js_syntax_ok(self):
        """金标准 16：widget.html <script> 块语法健康。"""
        import subprocess
        r = subprocess.run(
            ["node", "-e",
             "const fs=require('fs');const s=fs.readFileSync(process.argv[1],'utf8');"
             "[...s.matchAll(/<script>([\\s\\S]*?)<\\/script>/g)].forEach((m,i)=>{"
             "try{new Function(m[1]);}catch(e){console.log('ERR',i,e.message);process.exit(1);}});"
             "console.log('OK');",
             str(WIDGET)],
            capture_output=True, text=True, timeout=30,
        )
        assert r.returncode == 0, f"widget.html JS 语法错误: {r.stdout}{r.stderr}"
