"""TICKET-SELF-DIAGNOSE 专项测试 — 通用开发纪律 preset skill。

覆盖（票验收）：
- 静态：data/skill-standards/self-diagnose/standard.md 存在、
  含三条纪律（实弹验证/日志诊断/证据汇报）、格式对齐 code-fix（keywords 元数据）
- 行为：skill_loader 能加载它（匹配触发词注入）
- 红线：内容只约束动作，不约束表达方式（无措辞/语气要求）

边界：只读检查 + skill_loader 真实加载，不写任何文件。
"""

import re
from pathlib import Path

from core.skill_loader import SkillLoader

ROOT = Path(__file__).resolve().parent.parent
STD = ROOT / "data" / "skill-standards" / "self-diagnose" / "standard.md"
REF = ROOT / "data" / "skill-standards" / "code-fix" / "standard.md"

REQUIRED_DISCIPLINES = ("实弹验证", "日志诊断", "证据汇报")
ACTION_ONLY_GUARD = (
    # 表达约束类词——出现即违规（红线：只约束动作，不约束表达）
    "你必须这样说话", "语气", "措辞", "称呼我", "说话方式",
    "口吻", "开头必须", "结尾必须", "用XX语气", "必须礼貌",
)


# ── 静态：文件与格式 ─────────────────────────────────────────────────

def test_standard_md_exists():
    assert STD.exists(), f"standard.md 必须存在: {STD}"


def test_format_matches_code_fix():
    """格式对齐 code-fix：标题 v1 + keywords 元数据行。"""
    text = STD.read_text(encoding="utf-8")
    assert text.startswith("# Self-Diagnose Standard v1"), "标题须为 <Name> Standard v1"
    assert re.search(r"^> keywords: .+", text, re.M), "须有 keywords 元数据行"
    # 与 code-fix 同构：标题 + 元数据块 + 正文
    ref = REF.read_text(encoding="utf-8")
    assert "# Code Fix Standard v1" in ref  # 参照物有效


def test_keywords_cover_code_tasks():
    """keywords 覆盖通用开发触发词（开发/改代码/修复/bug/测试/验证）。"""
    text = STD.read_text(encoding="utf-8")
    kw_line = re.search(r"^> keywords: (.+)$", text, re.M).group(1)
    for kw in ("开发", "改代码", "修复", "bug", "测试", "验证"):
        assert kw in kw_line, f"keywords 缺通用触发词: {kw}"


# ── 静态：三条纪律内容 ───────────────────────────────────────────────

def test_contains_three_disciplines():
    text = STD.read_text(encoding="utf-8")
    for d in REQUIRED_DISCIPLINES:
        assert d in text, f"缺纪律: {d}"


def test_contains_eight_step_method():
    text = STD.read_text(encoding="utf-8")
    assert "八步调试法" in text
    for i in range(1, 9):
        assert f"{i}." in text, f"八步调试法缺第 {i} 步"


# ── 行为：skill_loader 真实加载注入 ─────────────────────────────────

def test_loader_injects_on_code_topic():
    """history 含"开发任务"→ self-diagnose 被加载（命中触发词注入）。"""
    history = [{"role": "user", "content": "这是一个开发任务，帮我看看测试"}]
    loader = SkillLoader(get_history=lambda: history)
    injected = loader.load_standards()
    assert any("实弹验证" in s for s in injected), \
        f"self-diagnose 应被注入: {[s[:30] for s in injected]}"


def test_loader_injects_on_bug_topic():
    """history 含"报错/修复"→ 同样注入（与 code-fix 可共存）。"""
    history = [{"role": "user", "content": "修一下这个报错"}]
    loader = SkillLoader(get_history=lambda: history)
    injected = loader.load_standards()
    assert any("实弹验证" in s for s in injected)


def test_loader_matches_any_trigger_word():
    """任一触发词命中即注入（"改代码"）。"""
    history = [{"role": "user", "content": "帮我改代码"}]
    loader = SkillLoader(get_history=lambda: history)
    injected = loader.load_standards()
    assert any("实弹验证" in s for s in injected)


# ── 红线：只约束动作，不约束表达 ────────────────────────────────────

def test_no_expression_constraints():
    """内容不含表达约束（措辞/语气/说话方式类），只约束动作。"""
    text = STD.read_text(encoding="utf-8")
    for banned in ACTION_ONLY_GUARD:
        assert banned not in text, f"出现表达约束类词: {banned!r}"


def test_action_disciplines_are_behavioral():
    """三条纪律都是动作（实弹调用/查日志/附证据），不是措辞要求。"""
    text = STD.read_text(encoding="utf-8")
    # 动作词必须出现（证明纪律是行为性的）
    for action in ("发起一次真实调用", "看 data/logs/bobo.log", "附原始日志路径"):
        assert action in text, f"纪律须为动作描述: {action!r}"


def test_explicit_statement_no_expression_rule():
    """文件须明示：不约束表达方式（owner 红线自我声明）。"""
    text = STD.read_text(encoding="utf-8")
    assert "不约束表达" in text, "须明示只约束动作不约束表达"
