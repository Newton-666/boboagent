"""TICKET-SKILL-ACTIVE-2 专项测试 — skill 激活工具卡。

覆盖（票验收）：
- A1 静态：index.html 的 TOOL_ICONS/TOOL_FRIENDLY 含 skill_activate、
  on('skill.activate') 监听存在、.skill-activate-card CSS 纯新增
- A2 后端：injector 注入命中时 emit skill.activate（event_bus），
  payload {skill_name}= 标准首行标题去 # 号；每轮只 emit 一次（防刷屏）
- A3 后端：无标准命中 → 不 emit（零残留）
- A4 前端 node 桩：skill.activate 事件 → 渲染轻量卡（图标 + Skill 标题 + 名称）
"""

import re
from pathlib import Path

import pytest

from gui_harness import (
    GUI_FILE,
    extract_func,
    extract_main_js,
    make_el,
    run_node,
)

ROOT = Path(__file__).resolve().parent.parent
INJECTOR_PY = ROOT / "core" / "injector.py"


# ── 后端桩（复用 COST-2 测试的 MockEngine 模式）──────────────────────

class MockTracker:
    _change_log: list = []
    _read_files: dict = {}


class MockProactive:
    def inject_context(self, messages):
        return messages


class _Loader:
    def __init__(self, standards):
        self._standards = standards

    def load_standards(self):
        return self._standards

    def list_available(self):
        return ""


class MockEngine:
    def __init__(self, standards=None):
        self.history = [
            {"role": "user", "content": "第一轮问题"},
            {"role": "assistant", "content": "第一轮回答"},
            {"role": "user", "content": "当前轮问题"},
        ]
        self.current_user_input = "当前轮问题"
        self._pending_diff = ""
        self._compressing = False
        self.tracker = MockTracker()
        self.proactive = MockProactive()
        self.skill_loader = _Loader(standards or [])


_STD_CODE_FIX = (
    "# Code Fix Standard v1\n\n"
    "> keywords: bug, 修复, 报错, error, fix, debug\n"
    "Bobo 在做任何代码修复时必须遵守本文档。\n"
)

_STD_GIT = (
    "# Git Workflow Standard v1\n\n"
    "> keywords: git, commit, 提交\n"
    "提交前先 git diff --stat 自审。\n"
)


@pytest.fixture
def events():
    """event_bus 桩：收集写入的事件（隔离真实 events.jsonl）。"""
    import core.event_bus as eb
    fired = []

    class _Bus:
        def write(self, t, d):
            fired.append((t, d))

    original = eb.event_bus
    eb.event_bus = _Bus()
    yield fired
    eb.event_bus = original


def _build(engine):
    from core.injector import PromptInjector
    inj = PromptInjector(engine)
    return inj.build_messages(
        system_prompt="You are Bobo.",
        user_input="当前轮问题",
        tools_schema=[],
        extra_categories=set(),
        session_id="s1",
    )


# ── A1：静态 — 前端映射与监听 ───────────────────────────────────────

def test_a1_static_frontend_mappings():
    src = GUI_FILE.read_text(encoding="utf-8")
    # TOOL_ICONS 含 skill_activate（SVG 14×14 / stroke-width 1.25 同款）
    icons_m = re.search(r"var TOOL_ICONS = \{(.*?)\n\};", src, re.S)
    assert icons_m, "TOOL_ICONS 未找到"
    icons = icons_m.group(1)
    assert "'skill_activate'" in icons, "TOOL_ICONS 缺 skill_activate"
    svg_m = re.search(r"'skill_activate': '(<svg[^']+)'", icons)
    assert svg_m, "skill_activate 缺 SVG"
    svg = svg_m.group(1)
    assert 'stroke-width="1.25"' in svg, "SVG 描边应为 1.25（同款细线）"
    assert 'viewBox="0 0 14 14"' in svg, "SVG 应为 14×14 viewBox"

    # TOOL_FRIENDLY 含 skill_activate
    assert "'skill_activate': 'Skill'" in src, "TOOL_FRIENDLY 缺 skill_activate"

    # 监听存在（on('skill.activate')）
    assert re.search(r"on\('skill\.activate'", src), "缺 skill.activate 事件监听"

    # CSS 纯新增 class
    assert ".skill-activate-card {" in src, "缺 .skill-activate-card CSS"
    assert ".skill-activate-title {" in src, "缺 .skill-activate-title CSS"
    assert ".skill-activate-summary {" in src, "缺 .skill-activate-summary CSS"
    # 票标记
    assert "TICKET-SKILL-ACTIVE-2" in src, "前端改动应带票标记"


# ── A2：后端 — 命中注入 → emit 一次（payload 含 skill_name）──────────

def test_a2_backend_emit_on_hit(events):
    engine = MockEngine(standards=[_STD_CODE_FIX, _STD_GIT])
    _build(engine)
    act = [e for e in events if e[0] == "skill.activate"]
    assert len(act) == 1, f"每轮应只 emit 一次（实际 {len(act)}）——防刷屏"
    _, payload = act[0]
    assert payload["skill_name"] == "Code Fix Standard v1", (
        f"skill_name 应为标准首行标题去 # 号: {payload}"
    )


def test_a2b_backend_emit_quoted_std(events):
    """首行带引号/前后空格的标题也能正确提取。"""
    engine = MockEngine(standards=['   "Quoted Standard"   \n正文\n'])
    _build(engine)
    act = [e for e in events if e[0] == "skill.activate"]
    assert len(act) == 1
    assert act[0][1]["skill_name"] == '"Quoted Standard"', act[0]


# ── A3：后端 — 无标准 → 不 emit ────────────────────────────────────

def test_a3_backend_no_emit_without_hit(events):
    engine = MockEngine(standards=[])
    _build(engine)
    act = [e for e in events if e[0] == "skill.activate"]
    assert act == [], "无标准命中时不得 emit skill.activate"


# ── A4：前端 node 桩 — 事件 → 卡片渲染 ─────────────────────────────

def _extract_skill_activate_handler():
    """提取 on('skill.activate') 注册块源码（与 GUI-T3 同法，含结尾 ');'）。"""
    main = extract_main_js()
    m = re.search(r"on\('skill\.activate',\s*function[^{]*\{", main)
    assert m, "skill.activate handler 未找到"
    open_i = main.index("{", m.start())
    depth = 0
    for i in range(open_i, len(main)):
        c = main[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                # 吞掉函数体闭合 '}' 后的 ')' 与 ';'（否则嵌入 js 语法错误）
                j = i + 1
                while j < len(main) and main[j] in " \t\n":
                    j += 1
                if j < len(main) and main[j] == ")":
                    j += 1
                while j < len(main) and main[j] in " \t\n":
                    j += 1
                if j < len(main) and main[j] == ";":
                    j += 1
                return main[m.start():j]
    raise AssertionError("handler 未闭合")


def test_a4_frontend_node_render():
    """桩环境触发 skill.activate → 渲染轻量卡（图标 + Skill 标题 + 名称）。"""
    handler = _extract_skill_activate_handler()

    js = f"""
    var chatEl = {{
        children: [],
        scrollTop: 0, set scrollTop(v) {{}}, get scrollHeight() {{ return 0; }},
        appendChild: function(c) {{ this.children.push(c); }},
        addEventListener: function() {{}}
    }};
    var _handlers = {{}};
    function on(evt, fn) {{ _handlers[evt] = fn; }}
    function isForeignSession(d) {{ return false; }}
    function esc(s) {{ return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;')
        .replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }}
    function toolIcon(name) {{
        var m = TOOL_ICONS[name];
        return m || TOOL_ICONS['_default'];
    }}
    var TOOL_ICONS = {_icons_js()};
    var document = {{ createElement: function(tag) {{
        return {{ className: '', dataset: {{}}, children: [], innerHTML: '',
            setAttribute: function(k, v) {{ this.dataset[k] = v; }},
            appendChild: function(c) {{ this.children.push(c); }},
            get childNodes() {{ return this.children; }} }};
    }} }};
    {handler}
    // 触发注册的 handler（真实行为路径）
    var card = null;
    var _reg = _handlers['skill.activate'];
    if (typeof _reg !== 'function') throw new Error('handler 未注册');
    card = _reg({{ skill_name: 'Code Fix Standard v1' }});
    if (!card) card = chatEl.children[chatEl.children.length - 1];
    if (!card) throw new Error('卡片未渲染');
    if (card.className !== 'skill-activate-card') throw new Error('class 错误: ' + card.className);
    if (card.dataset['data-tool'] !== 'skill_activate') throw new Error('data-tool 错误');
    if (card.innerHTML.indexOf('svg') === -1) throw new Error('缺图标');
    if (card.innerHTML.indexOf('Skill') === -1) throw new Error('缺标题');
    if (card.innerHTML.indexOf('Code Fix Standard v1') === -1) throw new Error('缺名称');
    console.log('A4-OK ' + card.innerHTML.length + ' chars');
    """

    out = run_node(js)
    assert "A4-OK" in out, f"node 桩渲染失败: {out}"


def _icons_js():
    """提取 TOOL_ICONS 对象源码（JSON 化嵌入 node 桩）。"""
    src = GUI_FILE.read_text(encoding="utf-8")
    m = re.search(r"var TOOL_ICONS = (\{.*?\n\});", src, re.S)
    assert m, "TOOL_ICONS 未找到"
    return m.group(1)
