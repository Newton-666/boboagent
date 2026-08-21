"""TICKET-SKILL-LLM-MATCH 专项测试 — skill 匹配改 LLM 语义确认 + 摘要注入。

覆盖（票验收）：
- SkillLoader：有 llm_caller + trigger 候选 → LLM 语义确认命中（消除触发词重叠误触发）
- SkillLoader：无 llm_caller / LLM 异常 / LLM 空输出 → trigger 候选兜底
- SkillLoader：LLM 明确无匹配（NONE）→ 不注入（语义判断优先于硬编码）
- SkillLoader：enabled 治理（关掉的 skill 即使 LLM 命中也不注入）
- SkillLoader：普通消息无 trigger 候选 → 不调 LLM（零成本，COST-2）
- injector._build_skill_summary_block：摘要（name+keywords+前500字符）+ 路径指针
  + 读全文指引，不含全文（省 token，COST-2 目标）
"""

import pytest

from core.skill_loader import SkillLoader
from core import injector as injector_mod
from core import skill_loader as _skill_loader_mod


def _fake_llm(content="research"):
    """构造固定返回 content 的假 llm_caller（签名对齐 create_llm_caller）。"""
    def _call(prompt, use_tools=False, thinking_disabled=True, max_tokens=200):
        return {"choices": [{"message": {"content": content}}]}
    return _call


def _loader(history, llm=None):
    return SkillLoader(get_history=lambda: history, llm_caller=llm)


@pytest.fixture(autouse=True)
def force_enabled(monkeypatch):
    """固定 _load_enabled（防其他测试污染 enabled.json 影响本票断言）。

    research/note-taking 开（供候选确认测试），web-design 关（供治理测试）。
    全量测试中某些测试会改写 data/skills/enabled.json 且不恢复，导致本票的
    research 候选被关掉而失败；用 monkeypatch 隔离文件状态，保证测试稳定。
    """
    monkeypatch.setattr(
        _skill_loader_mod, "_load_enabled",
        lambda: {"research": True, "note-taking": True, "web-design": False})


# ── 单元：_parse_hits（候选确认）───────────────────────────────────

def test_parse_hits_none_on_empty():
    """LLM 输出空/空白 → 返回 None（判断失败 → 调用方走候选兜底）。"""
    candidates = ["research", "code-fix"]
    entries = {"research": {}, "code-fix": {}}
    loader = _loader([])
    assert loader._parse_hits("", candidates, entries, {}) is None
    assert loader._parse_hits("   ", candidates, entries, {}) is None


def test_parse_hits_empty_on_none():
    """LLM 输出 NONE/无技能名 → 返回 []（明确无匹配，不注入）。"""
    candidates = ["research", "code-fix"]
    entries = {"research": {}, "code-fix": {}}
    loader = _loader([])
    assert loader._parse_hits("NONE", candidates, entries, {}) == []
    assert loader._parse_hits("没有匹配的技能", candidates, entries, {}) == []


def test_parse_hits_matches_candidate_names():
    """LLM 输出候选技能名 → 返回命中列表（大小写不敏感）。"""
    candidates = ["research", "code-fix"]
    entries = {"research": {}, "code-fix": {}}
    loader = _loader([])
    assert loader._parse_hits("Research", candidates, entries, {}) == ["research"]
    assert loader._parse_hits("code-fix", candidates, entries, {}) == ["code-fix"]


def test_parse_hits_respects_enabled():
    """enabled 关掉的候选即使 LLM 命中也不返回。"""
    candidates = ["web-design", "research"]
    entries = {"web-design": {}, "research": {}}
    enabled = {"web-design": False}
    loader = _loader([])
    hits = loader._parse_hits("web-design research", candidates, entries, enabled)
    assert "web-design" not in hits and "research" in hits


def test_parse_hits_only_from_candidates():
    """LLM 返回候选之外的技能名 → 不返回（候选确认不扩展候选集）。"""
    candidates = ["research"]
    entries = {"research": {}, "code-fix": {}}
    loader = _loader([])
    assert loader._parse_hits("code-fix", candidates, entries, {}) == []


# ── 单元：_judge_by_llm ────────────────────────────────────────────

def test_judge_by_llm_none_without_caller():
    """无 llm_caller → 返回 None（走候选兜底）。"""
    loader = _loader([{"role": "user", "content": "帮我查一下"}])
    assert loader._judge_by_llm(
        "帮我查一下", ["research"], {"research": {}}, {}) is None


def test_judge_by_llm_none_without_candidates():
    """无候选 → 返回 None（不调 LLM，零成本）。"""
    loader = _loader([{"role": "user", "content": "say hi"}], llm=_fake_llm("research"))
    assert loader._judge_by_llm(
        "say hi", [], {"research": {}}, {}) is None


# ── 集成：load_standards（真实 skill 目录，全链路）────────────────

def test_llm_judge_confirms_research():
    """LLM 语义确认命中 research → 注入 research 全文（替代硬编码评分）。"""
    history = [{"role": "user", "content": "帮我查一下上海和北京的房价对比"}]
    loader = _loader(history, llm=_fake_llm("research"))
    injected = loader.load_standards()
    assert any("多源交叉验证" in s for s in injected), "LLM 命中 research 应注入"


def test_llm_exception_fallback_candidates():
    """LLM 调用抛异常 → 回退 trigger 候选兜底（research 仍注入，降级不丢纪律）。"""
    def _boom(prompt, **kw):
        raise RuntimeError("llm down")
    history = [{"role": "user", "content": "帮我查一下上海和北京的房价对比"}]
    loader = _loader(history, llm=_boom)
    injected = loader.load_standards()
    assert any("多源交叉验证" in s for s in injected), "LLM 异常应回退候选"


def test_llm_empty_output_fallback_candidates():
    """LLM 返回空输出（调用失败但未抛异常）→ 回退 trigger 候选兜底。"""
    history = [{"role": "user", "content": "帮我查一下上海和北京的房价对比"}]
    loader = _loader(history, llm=_fake_llm(""))
    injected = loader.load_standards()
    assert any("多源交叉验证" in s for s in injected), "LLM 空输出应回退候选"


def test_llm_explicit_none_no_inject():
    """LLM 明确输出 NONE（真不匹配）→ 不注入任何 skill（语义判断优先于硬编码）。"""
    history = [{"role": "user", "content": "帮我查一下上海和北京的房价对比"}]
    loader = _loader(history, llm=_fake_llm("NONE"))
    injected = loader.load_standards()
    assert injected == [], "LLM 明确无匹配时不注入（即使 trigger 命中）"


def test_enabled_disabled_skill_not_injected():
    """enabled 关掉的 skill（web-design）即使 LLM 命中也不注入。"""
    history = [{"role": "user", "content": "帮我设计一个落地页"}]
    loader = _loader(history, llm=_fake_llm("web-design"))
    injected = loader.load_standards()
    assert not any("视觉方向探索" in s for s in injected), \
        "web-design 被关掉（enabled=false）不得注入"


def test_no_candidate_no_llm_call():
    """普通消息无 trigger 候选 → 不调 LLM（零成本，COST-2 关键）。"""
    called = []

    def _spy(prompt, **kw):
        called.append(prompt)
        return {"choices": [{"message": {"content": "research"}}]}

    history = [{"role": "user", "content": "say hi"}]
    loader = _loader(history, llm=_spy)
    injected = loader.load_standards()
    assert injected == [], "say hi 无候选 → 不注入"
    assert called == [], "无候选时不得调 LLM（零成本）"


def test_judge_by_llm_passes_topic_and_catalog():
    """llm_caller 收到含任务描述 + 候选技能清单的 prompt。"""
    captured = {}

    def _spy(prompt, **kw):
        captured["prompt"] = prompt
        return {"choices": [{"message": {"content": "NONE"}}]}

    history = [{"role": "user", "content": "帮我查一下上海和北京房价"}]
    loader = _loader(history, llm=_spy)
    injected = loader.load_standards()
    assert injected == []  # NONE → 不注入
    sys_text = captured["prompt"][0]["content"]
    user_text = captured["prompt"][1]["content"]
    assert "帮我查一下上海和北京房价" in user_text, "任务描述应传给 LLM"
    assert "research" in sys_text, "候选清单应含命中的 skill"


# ── 单元：injector._build_skill_summary_block（摘要注入）──────────

def test_summary_block_builds_path_pointer():
    """摘要块含标题 + 触发词 + 摘要 + 读全文指引 + 路径指针，不含全文。"""
    content = ("# Research Standard v1\n"
               "> keywords: 查一下, 调研\n"
               "> 价值: 查资料时命中\n\n"
               "多源交叉验证是核心纪律。")
    block = injector_mod._build_skill_summary_block(content)
    assert "### Research Standard v1" in block
    assert "触发词:" in block
    assert "摘要:" in block
    assert "read_local_file data/skill-standards/research/standard.md" in block


def test_summary_block_no_full_content():
    """摘要块截断（前500字符），不含完整正文（省 token，COST-2 目标）。"""
    content = "# 长标准 v1\n" + "A" * 2000
    block = injector_mod._build_skill_summary_block(content)
    assert "A" * 501 not in block, "摘要不得含完整 2000 字符正文"
    assert len(block) < 700, "摘要应远小于全文"


def test_summary_block_path_fallback_title():
    """无真实目录映射时路径指针退化为 title 派生（测试 mock / 新 skill 场景）。"""
    content = "# 幽灵标准 v9\n> keywords: x\n\n摘要内容"
    block = injector_mod._build_skill_summary_block(content)
    assert "read_local_file data/skill-standards/幽灵标准 v9/standard.md" in block


def test_summary_block_handles_no_keywords():
    """标准无 keywords 元数据行时，摘要块省略触发词行（不崩）。"""
    content = "# 无关键词标准\n\n只有正文没有触发词声明。"
    block = injector_mod._build_skill_summary_block(content)
    assert "### 无关键词标准" in block
    assert "触发词:" not in block
    assert "read_local_file data/skill-standards/" in block
