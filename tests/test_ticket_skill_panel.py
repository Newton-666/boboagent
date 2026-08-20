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


# ── 前端静态测试（v2：Memory 式导航项 + 主面板）────────────────────

def test_f1_static_sidebar_section():
    src = GUI_FILE.read_text(encoding="utf-8")
    # v2：左侧栏 nav-item（SVG + 名称 + hover 高亮，同 Memory 模式）
    assert 'id="nav-skills"' in src, "缺 nav-skills 导航项"
    assert "onNavSkills()" in src, "缺 onNavSkills 点击处理"
    assert 'class="nav-label">Skills</span>' in src, "缺 Skills 名称"
    # v2：主面板视图（同 Memory 的 memory-view 模式）
    assert 'id="skills-view"' in src, "缺 skills-view 主面板"
    assert 'id="skills-groups"' in src, "缺 skills-groups 容器"
    assert 'id="skills-stats"' in src, "缺 skills-stats"
    assert "TICKET-SKILL-PANEL" in src, "缺票标记"
    # 渲染函数存在（v2 版）
    for fn in ("loadSkillsPanel", "renderSkillRow", "toggleSkill", "closeSkillsView"):
        assert "function " + fn in src, f"缺 {fn}"
    # toggle 调用接线
    assert "skills.toggle" in src and "skills.list" in src, "缺 RPC 调用"
    # setNavActive 包含 nav-skills
    assert "'nav-skills'" in src, "setNavActive 应含 nav-skills"
    # CSS 纯新增（主面板行/开关/分组标签）
    for cls in (".skills-row", ".skill-toggle", ".skill-toggle.on",
                ".skills-sec-label", ".skills-list"):
        assert cls in src, f"缺 CSS: {cls}"
    # 空状态文案（Custom 引导；英文——v2 主面板用英文保持 I18n 合规）
    assert "Auto-generated skills will appear here" in src, "缺 custom 空状态文案"


# ── 前端 node 桩测试（v2：renderSkillRow + toggleSkill）────────────────

def _extract_render_skills():
    """提取 renderSkillRow 函数源码（用于 node 桩实跑）。"""
    src = extract_main_js()
    return extract_func(src, "renderSkillRow")


def test_f2_node_render_groups():
    """node 桩：renderSkillRow 渲染单行（名称 + on/off 开关 + class）。"""
    fn = _extract_render_skills()
    js = f"""
    function esc(s) {{ return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }}
    function toggleSkill() {{}}
    {fn}
    var rowOn = renderSkillRow({{ name: 'code-fix', enabled: true }});
    var rowOff = renderSkillRow({{ name: 'git-workflow', enabled: false }});
    if (rowOn.indexOf('code-fix') === -1) throw new Error('on 行缺名称');
    if (rowOn.indexOf('skill-toggle on') === -1) throw new Error('on 行缺 .on class');
    if (rowOn.indexOf('>on<') === -1) throw new Error('on 行按钮应为 on');
    if (rowOff.indexOf('git-workflow') === -1) throw new Error('off 行缺名称');
    if (rowOff.indexOf('skill-toggle') === -1) throw new Error('off 行缺 toggle class');
    if (rowOff.indexOf('skill-toggle on') !== -1) throw new Error('off 行不应有 .on');
    if (rowOff.indexOf('>off<') === -1) throw new Error('off 行按钮应为 off');
    console.log('F2-OK rowOn=' + rowOn.length + ' rowOff=' + rowOff.length);
    """
    out = run_node(js)
    assert "F2-OK" in out, f"node 桩渲染失败: {out}"


def test_f2b_node_toggle_calls_rpc():
    """node 桩：toggleSkill 点击调用 skills.toggle（enabled 取反）。"""
    src = extract_main_js()
    fn = extract_func(src, "toggleSkill")
    js = f"""
    var calls = [];
    function call(m, p) {{ calls.push({{ m: m, p: p }}); return Promise.resolve({{}}); }}
    function loadSkillsPanel() {{}}
    {fn}
    // 模拟 on 态按钮（class 含 'on'）→ toggle 应传 enabled=false
    var btnOn = {{ classList: {{ contains: function(c) {{ return c === 'on'; }} }} }};
    toggleSkill(btnOn, 'code-fix');
    // 注意 toggleSkill 的 call 是异步的（.then 里刷新），此处只验证调用参数
    if (calls.length !== 1) throw new Error('应调一次 skills.toggle');
    if (calls[0].m !== 'skills.toggle') throw new Error('method 应为 skills.toggle');
    if (calls[0].p.skill_name !== 'code-fix' || calls[0].p.enabled !== false)
        throw new Error('on 态应传 enabled=false: ' + JSON.stringify(calls[0].p));
    console.log('F2B-OK toggle=' + JSON.stringify(calls[0].p));
    """
    out = run_node(js)
    assert "F2B-OK" in out, f"node 桩 toggle 失败: {out}"
