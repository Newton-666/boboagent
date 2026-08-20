"""TICKET-SKILL-AUDIT-1 专项测试 — preset skill 价值审查。

覆盖（票验收）：
- 每个 standard.md 有价值声明行（> 价值:）——skill 自明价值
- research 触发词已收紧（无"有没有/找一下"等日常口语词）+ excludes 生效
- note-taking 已缩词（无"保存/存档/写入/append"泛写词）+ 非笔记 excludes
- web-design 无"做个/做一个"泛词 + 日常 excludes
- git-workflow 无"版本/备份"宽词 + 软件讨论 excludes
- tmux-office / code-fix excludes 补丁
- 行为：skill_loader 真实加载——调研话题注入 research，"有没有人"场景排除
"""

import os
import re
from pathlib import Path

from core.skill_loader import SkillLoader

ROOT = Path(__file__).resolve().parent.parent
STD_DIR = ROOT / "data" / "skill-standards"

# 本票收掉的日常口语/泛写词（出现在 keywords 即违规）
BANNED_KW = {
    "research": ("有没有", "找一下", "look up", "find", "what is", "how to", "怎么做", "怎么用", "什么意思"),
    "note-taking": ("保存", "写入", "存档", "append"),
    "web-design": ("做个", "做一个"),
    "git-workflow": ("版本", "备份"),
}
# 本票补的 excludes（缺失即违规）
REQUIRED_EX = {
    "research": ("有没有人", "有没有时间"),
    "note-taking": ("日志", "配置", "文件", "数据"),
    "web-design": ("做饭", "决定"),
    "tmux-office": ("在办公室", "去办公室"),
    "code-fix": ("文档", "文案"),
    "git-workflow": ("新版本", "发布了"),
}


def _read(name: str) -> str:
    p = STD_DIR / name / "standard.md"
    assert p.exists(), f"缺 standard.md: {p}"
    return p.read_text(encoding="utf-8")


def _meta_line(text: str, key: str) -> str:
    m = re.search(rf"^>\s*{key}:\s*(.+)$", text, re.M)
    assert m, f"缺 {key} 元数据行"
    return m.group(1)


# ── 价值声明：每个保留 skill 自明价值 ───────────────────────────────

def test_every_standard_has_value_statement():
    """每个 standard.md 必须有价值声明行（> 价值: 场景 → 约束）。"""
    missing = []
    for name in sorted(os.listdir(STD_DIR)):
        p = STD_DIR / name / "standard.md"
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8")
        if not re.search(r"^>\s*价值:", text, re.M):
            missing.append(name)
    assert missing == [], f"缺价值声明的 skill: {missing}"


def test_value_statement_format():
    """价值行格式：含场景 + 箭头 + 约束（自明价值，不空泛）。"""
    for name in sorted(os.listdir(STD_DIR)):
        p = STD_DIR / name / "standard.md"
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8")
        m = re.search(r"^>\s*价值:\s*(.+)$", text, re.M)
        assert m, f"{name} 缺价值行"
        val = m.group(1)
        assert "命中" in val, f"{name} 价值行应说明命中场景: {val[:40]}"
        assert "→" in val, f"{name} 价值行应带约束箭头: {val[:40]}"


# ── 触发词收紧（本票改动验证）───────────────────────────────────────

def test_research_no_daily_colloquial_words():
    """research 已去掉日常口语词（有没有/找一下/what is/how to 等）。"""
    kws = _meta_line(_read("research"), "keywords")
    for banned in BANNED_KW["research"]:
        assert banned not in kws, f"research 仍含口语触发词: {banned!r}"


def test_research_keeps_core_trigger_words():
    """research 保留核心触发词（帮我查/搜一下/调研/搜索/研究/对比/vs/research）。"""
    kws = _meta_line(_read("research"), "keywords")
    for keep in ("帮我查", "搜一下", "调研", "搜索", "研究", "对比", "vs", "research"):
        assert keep in kws, f"research 应保留核心词: {keep!r}"


def test_research_excludes_person_time():
    """research excludes 含"有没有人/有没有时间"（非调研场景不注入）。"""
    ex = _meta_line(_read("research"), "excludes")
    for word in REQUIRED_EX["research"]:
        assert word in ex, f"research excludes 缺: {word!r}"


def test_note_taking_no_generic_write_words():
    """note-taking 已去掉泛写词（保存/写入/存档/append）。"""
    kws = _meta_line(_read("note-taking"), "keywords")
    for banned in BANNED_KW["note-taking"]:
        assert banned not in kws, f"note-taking 仍含泛写词: {banned!r}"


def test_note_taking_excludes_file_ops():
    """note-taking excludes 含非笔记场景（日志/配置/文件/数据）。"""
    ex = _meta_line(_read("note-taking"), "excludes")
    for word in REQUIRED_EX["note-taking"]:
        assert word in ex, f"note-taking excludes 缺: {word!r}"


def test_web_design_no_do_generic():
    """web-design 已去掉"做个/做一个"泛词。"""
    kws = _meta_line(_read("web-design"), "keywords")
    for banned in BANNED_KW["web-design"]:
        assert banned not in kws, f"web-design 仍含泛词: {banned!r}"


def test_git_workflow_no_version_backup():
    """git-workflow 已去掉宽词"版本/备份"（回退/回滚/commit 已覆盖）。"""
    kws = _meta_line(_read("git-workflow"), "keywords")
    for banned in BANNED_KW["git-workflow"]:
        assert banned not in kws, f"git-workflow 仍含宽词: {banned!r}"


def test_all_required_excludes_present():
    """本票补的 excludes 全部在册（tmux-office / code-fix / git-workflow）。"""
    for skill, words in REQUIRED_EX.items():
        ex = _meta_line(_read(skill), "excludes")
        for w in words:
            assert w in ex, f"{skill} excludes 缺: {w!r}"


# ── 行为：skill_loader 真实加载 ─────────────────────────────────────

def test_behavior_research_injected_on_query():
    """调研话题（帮我查一下 X）→ research 注入（触发词保留生效）。"""
    history = [{"role": "user", "content": "帮我查一下上海和北京的房价对比"}]
    injected = SkillLoader(get_history=lambda: history).load_standards()
    assert any("多源交叉验证" in s for s in injected), "research 应注入"


def test_behavior_research_excluded_by_person_word():
    """"帮我查一下有没有人报名" → 含 excludes 词"有没有人" → research 不注入。"""
    history = [{"role": "user", "content": "帮我查一下有没有人报名这个活动"}]
    injected = SkillLoader(get_history=lambda: history).load_standards()
    assert not any("多源交叉验证" in s for s in injected), \
        "excludes 命中（有没有人）→ research 不得注入"


def test_behavior_research_not_injected_on_casual():
    """日常口语（"有没有人知道怎么处理"）→ 无 research 触发词 → 不注入。"""
    history = [{"role": "user", "content": "有没有人知道这个文件怎么处理"}]
    injected = SkillLoader(get_history=lambda: history).load_standards()
    assert not any("多源交叉验证" in s for s in injected), "日常口语不得触发 research"


def test_behavior_web_design_excluded_on_cooking():
    """"做个饭" → excludes（做饭）→ web-design 不注入。"""
    history = [{"role": "user", "content": "帮我做个饭吧"}]
    injected = SkillLoader(get_history=lambda: history).load_standards()
    assert not any("视觉方向探索" in s for s in injected), "做饭场景不得触发 web-design"
