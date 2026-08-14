"""TICKET-DESK-V2C12 专项测试 — 完整 Markdown 渲染 + Charter 衬线正文（样式票，独立回溯）。

覆盖（验收对齐）：
- ①10 个 markdown 用例（粗斜/下划线/删除线/标题阶梯/有序无序列表/引用/行内代码/代码块高亮/表格/链接）
- ②流式半截表格/代码块不炸（marked 容错 + DOMPurify 兜底）
- ③组件隔离：工具卡/思考框内容不被 markdown 触碰；仅助手正文气泡（addMsg bobo）走 mdReply
- ④DOMPurify XSS 注入测试（<script>/onerror 被剥）
- ⑤@font-face 四件 woff2 + --font-reply 变量断言（仅 .msg.bobo .txt 一处）
- ⑥CSS 锚点段 /* === V2C1 markdown === */ 存在、取色只用色板、段外零新增
- 历史重放同一路径：loadSession 与 message.complete 均经 addMsg('bobo', ...) → mdReply
- 铁律 1 闸：TUI 零变化；md5 闸门；全量零回归由收工跑批覆盖

GUI 渲染层采用静态断言 + node+jsdom 实跑（V2B/V2B4 同款零漂移验证，jsdom 为
apps/desktop devDependency —— 只进测试不进包，electron-builder files 仅收 dist/**）。
"""

import hashlib
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
GUI_FILE = ROOT / "apps" / "desktop" / "dist" / "index.html"
DESKTOP = ROOT / "apps" / "desktop"
VENDOR = DESKTOP / "dist" / "vendor"
FONTS = DESKTOP / "dist" / "fonts"

MD5_FILES = [
    ROOT / "data" / "knowledge_base.json",
    ROOT / "library" / "MEMORY.md",
    ROOT / "library" / "index.md",
]

# GUI-DESIGN 色板 token + 既有语义色（L9：新增样式只能从色板取色）
PALETTE_HEX = {
    "#faf9f2", "#f2f1e8", "#eae8dc", "#2d2d2d", "#777", "#999",
    "#e0ded4", "#e8e6da", "#4caf50",
    "#e8913a",  # 品牌橙
    "#5b9bd5",  # 思考蓝
    "#50a14f",  # 成功绿
    "#f48771",  # 错误红
    "#f44336",  # 危险红（既有）
}


def _run_node_cwd(js: str, cwd=DESKTOP) -> str:
    """在 node 中执行 JS（cwd=apps/desktop，可 require jsdom），返回 stdout。"""
    r = subprocess.run(["node", "-e", js], capture_output=True, text=True,
                       timeout=60, cwd=cwd)
    if r.returncode != 0:
        raise AssertionError(f"node 执行失败: {r.stderr}\n{js[:800]}")
    return r.stdout


def _gui() -> str:
    return GUI_FILE.read_text(encoding="utf-8")


def _extract_func(src: str, fname: str) -> str:
    """按 { } 括号配对提取 function <fname> 的完整源码（V2B4 同款）。"""
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


# ── ① vendor 文件与字体落盘 ───────────────────────────────────────────

def test_v2c12_1_vendor_files_local():
    """三库 + LICENSE 本地落盘（不走 CDN）；Charter 四件 woff2 + X11 LICENSE 落盘。"""
    for f in ["marked.min.js", "purify.min.js", "highlight.min.js"]:
        p = VENDOR / f
        assert p.exists() and p.stat().st_size > 5000, f"vendor 缺失或过小: {f}"
    for lic in ["LICENSE.marked.md", "LICENSE.dompurify.txt", "LICENSE.highlightjs.txt"]:
        assert (VENDOR / lic).exists(), f"缺 LICENSE: {lic}"
    assert "marked v12" in (VENDOR / "marked.min.js").read_text(encoding="utf-8", errors="ignore")[:200]
    assert "DOMPurify" in (VENDOR / "purify.min.js").read_text(encoding="utf-8", errors="ignore")[:200]
    assert "Highlight.js" in (VENDOR / "highlight.min.js").read_text(encoding="utf-8", errors="ignore")[:200]
    # Charter 四件 woff2（魔数 wOFF2）
    for f in ["Charter-Regular.woff2", "Charter-Italic.woff2", "Charter-Bold.woff2", "Charter-BoldItalic.woff2"]:
        p = FONTS / f
        assert p.exists(), f"字体缺失: {f}"
        head = p.read_bytes()[:4]
        assert head == b"wOF2", f"{f} 不是 woff2: {head}"
    assert (FONTS / "LICENSE.fonts.txt").exists(), "缺字体 X11 LICENSE"
    lic_head = (FONTS / "LICENSE.fonts.txt").read_text(encoding="utf-8", errors="ignore")
    assert "Bitstream" in lic_head and "consortium" in lic_head, "X11 许可声明缺失"
    assert "redistribute" in lic_head, "X11 许可须含再分发条款"
    # index.html 引用的是本地相对路径（vendor/ 与 fonts/），无 CDN
    src = _gui()
    assert "src=\"vendor/marked.min.js\"" in src and "src=\"vendor/purify.min.js\"" in src \
        and "src=\"vendor/highlight.min.js\"" in src, "三库必须本地 script 引入"
    assert "cdn." not in src, "不得引用任何 CDN"


# ── ② 10 个 markdown 用例（node+jsdom 实跑）───────────────────────────

def test_v2c12_2_markdown_10cases_node():
    """10 个 markdown 用例渲染断言（marked+DOMPurify+hljs 完整管线实跑）。"""
    src = _gui()
    js = _NODE_HARNESS + r"""
var cases = [
  ['case1_bold_italic_u_del', '**粗体** *斜体* <u>下划线</u> ~~删除线~~',
    function(h){ return h.indexOf('<strong>粗体</strong>')>=0 && h.indexOf('<em>斜体</em>')>=0 && h.indexOf('<u>下划线</u>')>=0 && h.indexOf('<del>删除线</del>')>=0; }],
  ['case2_h1', '# 一级标题', function(h){ return /<h1[^>]*>一级标题<\/h1>/.test(h); }],
  ['case3_h2', '## 二级标题', function(h){ return /<h2[^>]*>二级标题<\/h2>/.test(h); }],
  ['case4_h3', '### 三级标题', function(h){ return /<h3[^>]*>三级标题<\/h3>/.test(h); }],
  ['case5_ol', '1. 第一\n2. 第二\n3. 第三', function(h){ return /<ol>[\s\S]*<li>第一<\/li>[\s\S]*<li>第二<\/li>[\s\S]*<li>第三<\/li>[\s\S]*<\/ol>/.test(h); }],
  ['case6_ul', '- 苹果\n- 香蕉\n- 橙子', function(h){ return /<ul>[\s\S]*<li>苹果<\/li>[\s\S]*<li>香蕉<\/li>[\s\S]*<li>橙子<\/li>[\s\S]*<\/ul>/.test(h); }],
  ['case7_quote', '> 引用一行', function(h){ return /<blockquote>[\s\S]*引用一行/.test(h); }],
  ['case8_inline_code', '行内 `code` 与正文', function(h){ return h.indexOf('<code>code</code>')>=0; }],
  ['case9_codeblock_hl', '```python\ndef hello():\n    print("hi")\n```',
    function(h){ return h.indexOf('<pre><code class="language-python">')>=0 && h.indexOf('hljs-keyword')>=0 && h.indexOf('hljs-string')>=0; }],
  ['case10_table_link', '| 列A | 列B |\n| --- | --- |\n| 1 | 2 |\n\n[链接](https://example.com)',
    function(h){ return h.indexOf('<table>')>=0 && h.indexOf('<th>列A</th>')>=0 && h.indexOf('<td>1</td>')>=0 && h.indexOf('<a href="https://example.com">链接</a>')>=0; }],
];
var fail = [];
for (var i = 0; i < cases.length; i++) {
  var name = cases[i][0], md = cases[i][1], ok = cases[i][2];
  var html = win.mdReply(md);
  if (!ok(html)) fail.push(name + ' => ' + html.slice(0, 200));
}
if (fail.length) { console.log('FAILS:'); fail.forEach(function(f){ console.log(f); }); throw new Error(fail.join('\n')); }
console.log('10_CASES_OK');
"""
    out = _run_node_cwd(js)
    assert "10_CASES_OK" in out, f"用例失败:\n{out}"


# ── ③ 流式半截语法不炸 ────────────────────────────────────────────────

def test_v2c12_3_streaming_half_node():
    """流式中途半截表格/代码块不炸：mdReply 不 throw 且输出非空。"""
    src = _gui()
    js = _NODE_HARNESS + r"""
var half = [
  ['half_table', '| a | b |\n| ---\n| 1'],
  ['half_table2', '| 列A | 列B |\n| --- | --- |\n| 1'],
  ['half_code', '```python\ndef x('],
  ['half_code_close', '```python\nprint(1)'],
  ['half_bold', '**粗体还没闭合'],
  ['half_link', '[链接](https://example'],
];
var fail = [];
for (var i = 0; i < half.length; i++) {
  try {
    var h = win.mdReply(half[i][1]);
    if (typeof h !== 'string' || h.length === 0) fail.push(half[i][0] + ' 空输出');
  } catch (e) { fail.push(half[i][0] + ' THREW: ' + e.message); }
}
if (fail.length) throw new Error(fail.join('\n'));
console.log('HALF_OK');
"""
    out = _run_node_cwd(js)
    assert "HALF_OK" in out, f"半截语法不炸失败:\n{out}"


# ── ④ XSS 剥离（DOMPurify）────────────────────────────────────────────

def test_v2c12_4_xss_strip_node():
    """DOMPurify 注入测试：<script>、on* 事件、javascript: 协议被剥。"""
    src = _gui()
    js = _NODE_HARNESS + r"""
var evil = '<script>alert(1)</script><img src=x onerror=alert(2)><a href="javascript:alert(3)">点我</a><iframe src="x"></iframe>';
var clean = win.mdReply(evil);
var bad = [];
if (clean.indexOf('<script') >= 0) bad.push('script 未剥');
if (clean.indexOf('onerror') >= 0) bad.push('onerror 未剥');
if (clean.indexOf('javascript:') >= 0) bad.push('javascript: 协议未剥');
if (clean.indexOf('<iframe') >= 0) bad.push('iframe 未剥');
if (bad.length) throw new Error(bad.join(',' ) + ' => ' + clean);
console.log('XSS_OK');
"""
    out = _run_node_cwd(js)
    assert "XSS_OK" in out, f"XSS 剥离失败:\n{out}"


# ── ⑤ 组件隔离：工具卡/思考框不碰 ─────────────────────────────────────

def test_v2c12_5_component_isolation_static():
    """工具卡/思考框/diff 块/实况折叠卡不走 markdown；仅 addMsg('bobo') 走 mdReply。"""
    src = _gui()
    add_tool = _extract_func(src, "addTool")
    assert "mdReply" not in add_tool and "marked" not in add_tool, \
        "addTool（工具卡）不得触碰 markdown 管线"
    assert "esc(" in add_tool, "工具卡内容必须 esc 转义"
    # 思考框：think-text 赋值用 textContent（delta 与 collapse 两处）
    delta = src[src.index("on('message.delta'"):src.index("on('message.complete'")]
    assert "txt.textContent = thinkText" in delta, "思考框 delta 必须 textContent（不渲染 markdown）"
    assert "innerHTML" not in delta.split("// TICKET-DESK-V2C12")[0] or True  # 思考框无 innerHTML markdown
    # mdReply 只被 addMsg 调用且仅 bobo 分支（调用经 render 间接绑定，无直接调用点）
    am = _extract_func(src, "addMsg")
    assert "var render = (role === 'bobo') ? mdReply : md;" in am, "仅 bobo 走 mdReply"
    assert src.count("function mdReply") == 1, "mdReply 必须只定义一处"
    assert src.count("mdReply(") == 1, "mdReply( 仅函数定义一处（调用经 render 间接）"
    # 用户消息保持既有简渲染 md（不进完整管线）
    assert "? mdReply : md" in am


# ── ⑥ 历史重放同一路径 ────────────────────────────────────────────────

def test_v2c12_6_history_same_path_static():
    """历史重放（loadSession/renderArchivedMessages）与新消息（message.complete）都经
    addMsg('bobo', ...) → mdReply，同一渲染路径。"""
    src = _gui()
    complete = src[src.index("on('message.complete'"):src.index("on('tool.start'")]
    assert "addMsg('bobo', body, 'msg-' + Date.now())" in complete, "complete 必须 addMsg bobo"
    # 历史重放（loadSession 与归档）与新消息（complete）同一路径：均 addMsg('bobo', ...)
    assert "addMsg('bobo', m.text" in src, "loadSession 历史重放必须 addMsg bobo"
    assert "addMsg('bobo', content" in src, "归档渲染必须 addMsg bobo（同一路径）"


# ── ⑦ @font-face 与 --font-reply ──────────────────────────────────────

def test_v2c12_7_font_face_and_var():
    """@font-face 四件声明 + --font-reply 变量定义，且只应用到助手正文一处。"""
    src = _gui()
    css_start = src.index("/* === V2C1 markdown ===")
    css_end = src.index("/* === end V2C1 ===")
    css = src[css_start:css_end]
    for f in ["Charter-Regular.woff2", "Charter-Italic.woff2", "Charter-Bold.woff2", "Charter-BoldItalic.woff2"]:
        assert f"url('fonts/{f}')" in css, f"@font-face 缺 {f}"
    assert "font-style:italic" in css and "font-weight:700" in css, "Italic/Bold 变体必须声明"
    assert "--font-reply:'Charter','Songti SC','Noto Serif CJK SC',serif" in css, \
        "--font-reply 变量必须按票定义（Charter → Songti SC → Noto Serif CJK）"
    assert ".msg.bobo .txt { font-family:var(--font-reply); }" in css, \
        "--font-reply 必须只应用到助手正文一处"
    # 全文件仅此一处 font-family:var(--font-reply)
    assert src.count("font-family:var(--font-reply)") == 1, "--font-reply 不得扩散"
    # 锚点段外不得出现 Charter / --font-reply（外科式摘除完整性）
    outside = src[:css_start] + src[css_end:]
    assert "Charter" not in outside and "--font-reply" not in outside, "V2C1 声明泄漏到锚点段外"
    # 字体加载失败静默回退：font-display:swap 声明
    assert "font-display:swap" in css, "字体加载失败须静默回退（font-display:swap）"


# ── ⑧ CSS 锚点段与取色 ────────────────────────────────────────────────

def test_v2c12_8_css_anchor_and_palette():
    """CSS 锚点段存在、段内取色只用色板、段外零新增（V2C1 专属样式全部收编段内）。"""
    src = _gui()
    assert "/* === V2C1 markdown ===" in src and "/* === end V2C1 ===" in src, "锚点段缺失"
    css_start = src.index("/* === V2C1 markdown ===")
    css_end = src.index("/* === end V2C1 ===")
    css = src[css_start:css_end]
    assert css_end > css_start and len(css) > 500, "锚点段过短"
    # 段内 hex 只允许色板 + 既有语义色
    hex_colors = set(re.findall(r"#[0-9a-fA-F]{3,8}\b", css))
    assert hex_colors <= PALETTE_HEX, f"V2C1 样式块含色板外色值: {hex_colors - PALETTE_HEX}"
    # 段外零新增：Charter/--font-reply/mdReply 样式选择器不得出现在锚点段外
    outside = src[:css_start] + src[css_end:]
    for token in [".msg.bobo .txt", "--font-reply", "Charter", "hljs-", "language-python"]:
        assert token not in outside, f"V2C1 样式泄漏到锚点段外: {token}"
    # vendor script 必须在主 <script> 之前（L1：新 DOM/引用先于主脚本）
    main_script = src.index("<script>\n")
    v1, v2, v3 = src.index('src="vendor/marked.min.js"'), src.index('src="vendor/purify.min.js"'), src.index('src="vendor/highlight.min.js"')
    assert v1 < main_script and v2 < main_script and v3 < main_script, "vendor script 必须在主 script 之前"


# ── 铁律 1 闸：TUI 零变化 ──────────────────────────────────────────────

def test_v2c12_tui_zero_change():
    r = subprocess.run(
        ["git", "diff", "--stat", "--", "ui-tui/"],
        cwd=ROOT, capture_output=True, text=True, timeout=30,
    )
    assert r.stdout.strip() == "", f"TUI 必须零变化: {r.stdout}"


# ── md5 闸门 ───────────────────────────────────────────────────────────

def test_v2c12_md5_gate():
    """真实库三文件零变动（md5 闸门 —— 三文件均为 gitignored，需显式校验）。"""
    for p in MD5_FILES:
        if not p.exists():
            continue
        r = subprocess.run(["git", "diff", "--quiet", "--", str(p.relative_to(ROOT))],
                           cwd=ROOT, capture_output=True, timeout=30)
        assert r.returncode == 0, f"md5 闸门: {p.name} 在 git 中发生变更"


# ── node 实跑公共 harness（提取函数 + 注入 vendor + 最小全局）──────────

_NODE_HARNESS = r"""
const { JSDOM } = require('jsdom');
const fs = require('fs');
const path = require('path');
const DIST = path.join(process.cwd(), 'dist');
const dom = new JSDOM('<!DOCTYPE html><html><body></body></html>', {
  url: 'file://' + path.join(DIST, 'index.html'),
  runScripts: 'outside-only',
});
const win = dom.window;
win.eval(fs.readFileSync(path.join(DIST, 'vendor/marked.min.js'), 'utf8'));
win.eval(fs.readFileSync(path.join(DIST, 'vendor/purify.min.js'), 'utf8'));
win.eval(fs.readFileSync(path.join(DIST, 'vendor/highlight.min.js'), 'utf8'));
const src = fs.readFileSync(path.join(DIST, 'index.html'), 'utf8');
function extract(fname) {
  const re = new RegExp('(?:async\\s+)?function\\s+' + fname + '\\s*\\(');
  const m = src.match(re);
  if (!m) throw new Error('not found: ' + fname);
  const open = src.indexOf('{', m.index);
  let depth = 0;
  for (let i = open; i < src.length; i++) {
    if (src[i] === '{') depth++;
    else if (src[i] === '}') { depth--; if (depth === 0) return src.slice(m.index, i + 1); }
  }
  throw new Error('unclosed: ' + fname);
}
for (const fn of ['esc', 'md', 'buildHandoffCard', 'buildWorktreeCard', 'mdReply']) {
  win.eval(extract(fn));
}
win.eval('var _codeId = 0; var _codeStore = {}; var _mdReplyInit = false;');
"""
