"""TICKET-OBSIDIAN-SEARCH-C 专项测试 — search_obsidian 三路匹配 + 语义兜底。

覆盖（票验收）：
- 三路：内容 grep / 文件名子串 / 路径子串，合并去重，排序 文件名>路径>内容
- 语义 L1：映射表（data/obsidian_alias_map.json）命中 → 用映射英文名再搜
- 语义 L2：LLM 辅助（thinking_disabled 冷调用）+ 自学习写回映射表（持久化）
- 两层都无 → "未找到"（保持现状语义）；LLM 失败 → 静默降级
- 返回带类型标记 [内容]/[文件名]/[路径]/[语义]

隔离：vault 与映射表全走 tmp_path（不碰真实库）。
"""

import json

import pytest

from tools import obsidian_tools as ot


@pytest.fixture(autouse=True)
def _vault(tmp_path, monkeypatch):
    """临时 vault：Applied spectroscopy/（英文文件夹，光谱场景）+ 中文内容笔记。

    注意：vault 内不得出现"光谱"字面（文件名/内容）——"光谱"语义测试需要
    三路全空才能走到语义兜底；中文内容用"拉曼"（raman_notes.md）承载。
    """
    vault = tmp_path / "vault"
    (vault / "Applied spectroscopy").mkdir(parents=True)
    (vault / "AI music lab").mkdir(parents=True)
    (vault / "Private").mkdir(parents=True)
    (vault / "Applied spectroscopy" / "spectroscopy_overview.md").write_text(
        "# Spectroscopy Overview\nRaman techniques\n", encoding="utf-8")
    (vault / "Applied spectroscopy" / "raman_notes.md").write_text(
        "# Raman\n拉曼散射\n", encoding="utf-8")
    (vault / "AI music lab" / "music_notes.md").write_text(
        "# Music\nAI 生成音乐\n", encoding="utf-8")
    (vault / "Private" / "secret.md").write_text("私密内容\n", encoding="utf-8")

    monkeypatch.setattr(ot, "OBSIDIAN_VAULT", str(vault))
    monkeypatch.setattr(ot, "BLOCKED_FOLDERS", [])
    monkeypatch.setattr(ot, "_ALIAS_MAP_FILE", tmp_path / "obsidian_alias_map.json")
    return vault


def _llm(folders):
    """构造 mock llm_caller：返回指定候选文件夹。"""
    def fake(msgs, **kw):
        return {"choices": [{"message": {"content": json.dumps({"folders": folders})}}]}
    return fake


# ── 三路匹配：确定性 ─────────────────────────────────────────────────

def test_name_match_hits_filename():
    """搜 "spectroscopy_overview" → 文件名子串命中（唯一，路径/内容不沾边）。"""
    out = ot.search_obsidian_notes("spectroscopy_overview")
    assert "[文件名] Applied spectroscopy/spectroscopy_overview.md" in out, out
    assert "找到 1 条" in out, out


def test_path_match_hits_directory():
    """搜 "Applied" → 路径子串命中该目录下所有笔记。"""
    out = ot.search_obsidian_notes("Applied")
    assert "[路径] Applied spectroscopy/spectroscopy_overview.md" in out, out
    assert "[路径] Applied spectroscopy/raman_notes.md" in out, out


def test_content_match_hits_body():
    """搜 "拉曼" → 内容命中（无文件名/路径命中时）。"""
    out = ot.search_obsidian_notes("拉曼")
    assert "[内容] Applied spectroscopy/raman_notes.md" in out, out


def test_priority_name_over_path():
    """优先级：同一文件文件名命中 > 路径命中（合并去重取高优先级）。"""
    # "spectroscopy" 同时命中文件名（spectroscopy_overview.md）与路径（Applied spectroscopy/）
    out = ot.search_obsidian_notes("spectroscopy")
    # raman_notes.md 只路径命中；overview 文件名命中
    assert "[文件名] Applied spectroscopy/spectroscopy_overview.md" in out
    assert "[路径] Applied spectroscopy/raman_notes.md" in out
    # 文件名命中排前面
    assert out.index("[文件名]") < out.index("[路径]"), "文件名命中应排序在前"


def test_blocked_folder_excluded():
    """屏蔽目录不参与三路匹配。"""
    import importlib
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(ot, "BLOCKED_FOLDERS", ["Private"])
    try:
        out = ot.search_obsidian_notes("私密")
        assert "secret.md" not in out, "屏蔽目录不得命中"
    finally:
        monkeypatch.undo()


# ── 语义兜底 L1：映射表 ─────────────────────────────────────────────

def test_alias_map_hit_uses_mapped_name(tmp_path, monkeypatch):
    """映射表 {"光谱": ["Applied spectroscopy"]} → 搜"光谱" → 映射英文名再搜命中。"""
    (tmp_path / "obsidian_alias_map.json").write_text(
        json.dumps({"光谱": ["Applied spectroscopy"]}), encoding="utf-8")
    calls = {"n": 0}

    def fake_llm(msgs, **kw):
        calls["n"] += 1
        return {"choices": [{"message": {"content": '{"folders": []}'}}]}

    out = ot.search_obsidian_notes("光谱", llm_caller=fake_llm)
    assert "[语义] Applied spectroscopy/spectroscopy_overview.md" in out, out
    assert calls["n"] == 0, "映射表命中不得调用 LLM"


def test_alias_map_miss_no_llm_caller_returns_not_found():
    """映射表未命中且无 llm_caller → 未找到（不崩）。"""
    out = ot.search_obsidian_notes("不存在的主题xyz", llm_caller=None)
    assert "没有找到" in out, out


# ── 语义兜底 L2：LLM 辅助 + 自学习 ─────────────────────────────────

def test_llm_fallback_hits_and_learns(tmp_path, monkeypatch):
    """映射表空 + LLM 返回候选 → 语义命中 + 自学习写回映射表（持久化）。"""
    out = ot.search_obsidian_notes("光谱", llm_caller=_llm(["Applied spectroscopy"]))
    assert "[语义] Applied spectroscopy/spectroscopy_overview.md" in out, out
    # 自学习：映射表已写入
    saved = json.loads((tmp_path / "obsidian_alias_map.json").read_text(encoding="utf-8"))
    assert "光谱" in saved and "Applied spectroscopy" in saved["光谱"], saved


def test_llm_learned_map_used_next_time(tmp_path):
    """自学习后：第二次搜"光谱"走映射表（不再调 LLM）。"""
    calls = {"n": 0}

    def fake_llm(msgs, **kw):
        calls["n"] += 1
        return {"choices": [{"message": {"content": '{"folders": ["Applied spectroscopy"]}'}}]}

    ot.search_obsidian_notes("光谱", llm_caller=fake_llm)  # 第一次：LLM 兜底 + 学习
    calls["n"] = 0
    out = ot.search_obsidian_notes("光谱", llm_caller=fake_llm)  # 第二次：映射表命中
    assert "[语义]" in out, out
    assert calls["n"] == 0, "自学习后第二次不得再调 LLM"


def test_llm_no_candidates_not_found(tmp_path):
    """LLM 返回空候选 → 未找到（保持现状语义）。"""
    out = ot.search_obsidian_notes("量子计算", llm_caller=_llm([]))
    assert "没有找到" in out, out
    # 未命中 → 不写映射表
    assert not (tmp_path / "obsidian_alias_map.json").exists() or \
        json.loads((tmp_path / "obsidian_alias_map.json").read_text(encoding="utf-8")) == {}


def test_llm_failure_silent():
    """LLM 抛异常 → 未找到（静默降级，不崩）。"""
    def boom(msgs, **kw):
        raise RuntimeError("llm down")

    out = ot.search_obsidian_notes("光谱", llm_caller=boom)
    assert "没有找到" in out, out


def test_cold_call_disables_thinking():
    """LLM 兜底必须 thinking_disabled=True（P5-400 同款防 400）。"""
    seen = {}

    def fake(msgs, **kw):
        seen.update(kw)
        return {"choices": [{"message": {"content": '{"folders": ["Applied spectroscopy"]}'}}]}

    ot.search_obsidian_notes("光谱", llm_caller=fake)
    assert seen.get("thinking_disabled") is True, "冷调用必须关 thinking"
    assert seen.get("use_tools") is False


def test_llm_garbage_output_silent():
    """LLM 返回非 JSON → 未找到（静默）。"""
    out = ot.search_obsidian_notes("光谱", llm_caller=lambda msgs, **kw: {
        "choices": [{"message": {"content": "完全不是 JSON"}}]})
    assert "没有找到" in out, out


# ── 返回格式 ────────────────────────────────────────────────────────

def test_result_tags_correct():
    """三种命中标记 + 语义标记都存在且格式正确。"""
    out = ot.search_obsidian_notes("music")
    assert "- [文件名] AI music lab/music_notes.md" in out or \
        "- [路径] AI music lab/music_notes.md" in out, out


def test_empty_query():
    assert "请提供搜索关键词" in ot.search_obsidian_notes("")
