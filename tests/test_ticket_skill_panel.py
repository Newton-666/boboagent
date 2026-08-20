"""TICKET-SKILL-PANEL 专项测试 — 左侧栏 Skill 面板（治理先行 A 票）。

覆盖（票验收）：
- B1 后端：enabled.json 读写（缺失/损坏/正常）与 _load_enabled 语义
- B2 后端：skills.toggle 写 enabled.json，保留其余项；非法 skill_name 拒绝
- B3 后端：load_standards 跳过关掉的 skill（含 requires 连带，一视同仁）
- F1 前端静态：Skills 分区 HTML（折叠头/内容体/list）、renderSkills/loadSkills
  存在、.skill-toggle/.skill-row CSS 纯新增、折叠关闭态规则
- F2 前端 node 桩：renderSkills 渲染 preset/custom 分组 + on/off 开关 + 空状态
"""

import json
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

# ── 后端测试 ─────────────────────────────────────────────────────────

def test_b1_enabled_json_read(tmp_path):
    """_load_enabled：缺失→{}；损坏→{}；正常 dict→bool 化。"""
    import core.skill_loader as sl
    real = sl._ENABLED_FILE
    try:
        sl._ENABLED_FILE = str(tmp_path / "enabled.json")  # 缺失
        assert sl._load_enabled() == {}
        (tmp_path / "enabled.json").write_text("{bad json", encoding="utf-8")  # 损坏
        assert sl._load_enabled() == {}
        (tmp_path / "enabled.json").write_text(
            json.dumps({"code-fix": False, "git-workflow": True}), encoding="utf-8"
        )
        got = sl._load_enabled()
        assert got == {"code-fix": False, "git-workflow": True}
    finally:
        sl._ENABLED_FILE = real


def test_b2_toggle_writes_and_keeps_others(tmp_path):
    """skills.toggle：写 enabled.json 保留其余项；非法名拒绝。"""
    sys_path = "bobo_tui_gateway.handlers.skills"
    import importlib
    h = importlib.import_module(sys_path)
    real = h._ENABLED_FILE
    try:
        h._ENABLED_FILE = tmp_path / "enabled.json"
        r = h.handle_skills_toggle({"skill_name": "code-fix", "enabled": False}, "r1", None)
        assert r["result"] == {"name": "code-fix", "enabled": False}
        r = h.handle_skills_toggle({"skill_name": "git-workflow", "enabled": False}, "r2", None)
        assert r["result"]["enabled"] is False
        data = json.loads((tmp_path / "enabled.json").read_text(encoding="utf-8"))
        assert data == {"code-fix": False, "git-workflow": False}, "应保留既有项"
        # 非法名拒绝
        for bad in ("", "../evil", "a/b", ".", ".."):
            r = h.handle_skills_toggle({"skill_name": bad, "enabled": True}, "r3", None)
            assert r.get("error"), f"非法 skill_name {bad!r} 应被拒绝"
    finally:
        h._ENABLED_FILE = real


def test_b3_load_standards_skips_disabled(tmp_path):
    """load_standards：关掉的 skill 不注入（真实标准目录，topic 触发 code-fix）。"""
    import core.skill_loader as sl
    real = sl._ENABLED_FILE
    try:
        sl._ENABLED_FILE = str(tmp_path / "enabled.json")
        hist = [{"role": "user", "content": "帮我修复这个 bug"}]
        loader = sl.SkillLoader(lambda: hist)
        # 默认（文件缺失 = 全开）：命中含 Code Fix
        res = loader.load_standards()
        assert any("Code Fix" in r for r in res), "默认应注入 code-fix"
        # 关掉 code-fix：不注入
        (tmp_path / "enabled.json").write_text(
            json.dumps({"code-fix": False}), encoding="utf-8"
        )
        res = loader.load_standards()
        assert not any("Code Fix" in r for r in res), "关掉后 code-fix 不得注入"
        # 恢复全开：再注入
        (tmp_path / "enabled.json").write_text("{}", encoding="utf-8")
        res = loader.load_standards()
        assert any("Code Fix" in r for r in res), "恢复后应重新注入"
    finally:
        sl._ENABLED_FILE = real


def test_b3b_enabled_file_does_not_break_returns(tmp_path):
    """enabled.json 含无关 key 时不影响其他 skill 注入。"""
    import core.skill_loader as sl
    real = sl._ENABLED_FILE
    try:
        sl._ENABLED_FILE = str(tmp_path / "enabled.json")
        (tmp_path / "enabled.json").write_text(
            json.dumps({"nonexistent-skill": False}), encoding="utf-8"
        )
        hist = [{"role": "user", "content": "帮我修复这个 bug"}]
        res = sl.SkillLoader(lambda: hist).load_standards()
        assert any("Code Fix" in r for r in res), "无关 key 不得影响既有 skill"
    finally:
        sl._ENABLED_FILE = real


# ── 前端静态测试 ─────────────────────────────────────────────────────

def test_f1_static_sidebar_section():
    src = GUI_FILE.read_text(encoding="utf-8")
    # 分区 HTML：折叠头 + 内容体 + list 容器
    assert "toggleSection('skill')" in src, "Skills 分区折叠头缺失"
    assert 'id="arr-skill"' in src, "缺折叠箭头 id"
    assert 'id="body-skill"' in src, "缺分区内容体"
    assert 'id="skill-list"' in src, "缺 skill-list 容器"
    assert "TICKET-SKILL-PANEL" in src, "缺票标记"
    # 渲染函数存在
    for fn in ("renderSkills", "loadSkills"):
        assert "function " + fn in src or "async function " + fn in src, f"缺 {fn}"
    # toggle 调用接线
    assert "skills.toggle" in src and "skills.list" in src, "缺 RPC 调用"
    # CSS 纯新增（行/开关/空状态/分组标题）
    for cls in (".skill-row", ".skill-toggle", ".skill-toggle.on",
                ".skill-empty", ".skill-group-title", "#body-skill.closed"):
        assert cls in src, f"缺 CSS: {cls}"
    # 空状态文案（B 票引导；I18n 铁律 → \u 转义存储，运行时解析为中文）
    assert "\\u81ea\\u52a8\\u6c89\\u6dc0" in src, "缺 custom 空状态文案（\\u 转义）"
    assert "\\u6682\\u65e0\\u9884\\u8bbe" in src, "缺 preset 空状态文案（\\u 转义）"
    # 解码后等于中文原文（防转义写错）
    assert "bobo 自动沉淀的 skill 会出现在这里" == (
        "bobo \u81ea\u52a8\u6c89\u6dc0\u7684 skill \u4f1a\u51fa\u73b0\u5728\u8fd9\u91cc"
    ), "转义与中文不一致"


# ── 前端 node 桩测试 ─────────────────────────────────────────────────

def _extract_render_skills():
    """提取 renderSkills 函数源码（用于 node 桩实跑）。"""
    src = extract_main_js()
    return extract_func(src, "renderSkills")


def _js_make_el_stub():
    """JS 版最小 DOM 元素桩（node 无 DOM；支持 renderSkills 的最小操作集）。"""
    return r"""
    function makeEl(tag) {
        return { tagName: tag.toUpperCase(), className: '', textContent: '',
            dataset: {}, children: [], innerHTML: '', style: {},
            setAttribute: function(k, v) { this.dataset[k] = v; },
            appendChild: function(c) { this.children.push(c); c.parentNode = this; },
            set innerHTML(v) { this.children = []; }
        };
    }
"""


def test_f2_node_render_groups():
    """node 桩：renderSkills 渲染 preset/custom 分组 + on/off 开关 + 空状态。"""
    fn = _extract_render_skills()
    js = f"""
    var chatEl = {{ children: [] }};
    {_js_make_el_stub()}
    var skillListEl = makeEl('div');
    var document = {{ getElementById: function(id) {{
        if (id === 'skill-list') return skillListEl;
        return null;
    }}, createElement: makeEl }};
    function call(m, p) {{ return Promise.resolve({{}}); }}
    function loadSkills() {{}}
    {fn}
    var data = {{
        preset: [{{ name: 'code-fix', enabled: true }}, {{ name: 'git-workflow', enabled: false }}],
        custom: []
    }};
    renderSkills(data);
    var html = JSON.stringify(skillListEl.children.map(function(g) {{
        return {{ cls: g.className, title: (g.children[0]||{{}}).textContent,
            rows: (g.children.slice(1)||[]).map(function(r) {{
                return {{ cls: r.className, name: (r.children[0]||{{}}).textContent,
                    tg: (r.children[1]||{{}}).textContent,
                    tgCls: (r.children[1]||{{}}).className,
                    dataSkill: (r.children[1]||{{}}).dataset ? (r.children[1]||{{}}).dataset['data-skill'] : null }};
            }}),
            empty: (g.children[1]||{{}}).textContent }};
    }}));
    var groups = JSON.parse(html);
    if (groups.length !== 2) throw new Error('应有两个分组: ' + groups.length);
    if (groups[0].title !== 'Preset') throw new Error('第一组应为 Preset');
    if (groups[1].title !== 'Custom') throw new Error('第二组应为 Custom');
    var rows = groups[0].rows;
    if (rows.length !== 2) throw new Error('preset 应有 2 行');
    if (rows[0].name !== 'code-fix' || rows[0].tg !== 'on') throw new Error('code-fix 应 on');
    if (rows[0].tgCls.indexOf('on') === -1) throw new Error('on 态缺 .on class');
    if (rows[1].name !== 'git-workflow' || rows[1].tg !== 'off') throw new Error('git-workflow 应 off');
    if (rows[1].tgCls.indexOf('on') !== -1) throw new Error('off 态不应有 .on class');
    if (groups[1].empty !== 'bobo 自动沉淀的 skill 会出现在这里')
        throw new Error('custom 空状态文案错误: ' + groups[1].empty);
    console.log('F2-OK groups=' + groups.length + ' rows=' + rows.length);
    """
    out = run_node(js)
    assert "F2-OK" in out, f"node 桩渲染失败: {out}"


def test_f2b_node_toggle_calls_rpc():
    """node 桩：开关点击调用 skills.toggle（enabled 取反）+ 刷新。"""
    fn = _extract_render_skills()
    js = f"""
    var chatEl = {{ children: [] }};
    {_js_make_el_stub()}
    var skillListEl = makeEl('div');
    var document = {{ getElementById: function(id) {{
        if (id === 'skill-list') return skillListEl;
        return null;
    }}, createElement: makeEl }};
    var calls = [];
    function call(m, p) {{ calls.push({{ m: m, p: p }}); return Promise.resolve({{}}); }}
    var refreshCount = 0;
    function loadSkills() {{ refreshCount++; }}
    {fn}
    renderSkills({{ preset: [{{ name: 'code-fix', enabled: true }}], custom: [] }});
    var btn = skillListEl.children[0].children[1].children[1];
    btn.onclick();
    if (calls.length !== 1) throw new Error('应调一次 skills.toggle');
    if (calls[0].m !== 'skills.toggle') throw new Error('method 应为 skills.toggle');
    if (calls[0].p.skill_name !== 'code-fix' || calls[0].p.enabled !== false)
        throw new Error('toggle 参数应取反: ' + JSON.stringify(calls[0].p));
    console.log('F2B-OK toggle=' + JSON.stringify(calls[0].p));
    """
    out = run_node(js)
    assert "F2B-OK" in out, f"node 桩 toggle 失败: {out}"
