"""票 LN-2 + LN-2R：主题笔记验收测试。

覆盖 9 项金标准（全部 tmpdir 物理检查）：
  1. 新主题建骨架笔记：frontmatter 齐全 + 五章节骨架 + version 1
  2. 同主题重写：match 命中 → 旧版进 .history、version+1、时间线追加
  3. 零价值不建：takeaways 为空 → library 无新文件、零 LLM 调用
  4. 命名违规矫正：日期主题名 → 文件名净化，不含 / : 等字符
  5. 误判保守：match=null → 建新笔记，不动任何已有笔记
  6. index 正确：两次落盘后 index.md 含两个主题条目，按领域分组
  7. 开关：BOBO_LIVING_NOTES=off 全流程零动作
  8. 降级：library 只读 → 收工正常完成（返回 written=False + error）
  9. 全量 pytest 通过（由 run_tests 单独验证零回归）
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tools.living_notes as ln


def _fake_llm(result: dict):
    """构造一个返回固定 JSON 的假 LLM 调用器。"""
    def _call(prompt, use_tools=False):
        return {"choices": [{"message": {"content": json.dumps(result, ensure_ascii=False)}}]}
    return _call


@pytest.fixture
def ln_env(tmp_path, monkeypatch):
    """隔离的 library 环境（monkeypatch 掉真实库址）。"""
    library = tmp_path / "library"
    monkeypatch.setattr(ln, "LIBRARY_DIR", library)
    monkeypatch.setattr(ln, "INDEX_PATH", library / "index.md")
    return library


# ── 验收 1：新主题建骨架笔记 ────────────────────────

def test_new_topic_creates_note(ln_env):
    llm = _fake_llm({
        "topic": "收工闸", "domain": "agent开发",
        "section": "- 收工闸在 RESPONDING 前检查待办\n- 回注最多两次",
        "match": None,
    })
    result = ln.write_living_notes(
        ["收工闸会拦截未完成的承诺"], "收工闸怎么实现的", "sid-1", llm
    )
    assert result["written"] is True
    assert result["is_new"] is True
    path = ln_env / "agent开发" / "收工闸.md"
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    # frontmatter 齐全
    assert text.startswith("---")
    assert "topic: 收工闸" in text
    assert "domain: agent开发" in text
    assert "created:" in text
    assert "last_touched:" in text
    assert "version: 1" in text
    assert "source_sessions: [sid-1]" in text
    # 五章节骨架
    for sec in ["概述", "关键结论", "决策与原因", "待办与未决", "时间线"]:
        assert f"## {sec}" in text
    # 概述含出处 sid
    assert "（源自会话 sid-1）" in text


# ── 验收 2：同主题重写（旧版进 .history、version+1）──

def test_same_topic_rewrites(ln_env):
    llm1 = _fake_llm({
        "topic": "收工闸", "domain": "agent开发",
        "section": "- 第一条要点", "match": None,
    })
    ln.write_living_notes(["第一次记录"], "用户消息1", "sid-1", llm1)
    path = ln_env / "agent开发" / "收工闸.md"
    first = path.read_text(encoding="utf-8")
    assert "version: 1" in first

    # 第二次：match 命中 → 骨架重写（判定 + 重写两次 LLM 调用）
    def seq_llm(prompt, use_tools=False):
        if "旧笔记全文" in str(prompt):
            # 重写输出：动态保留旧笔记时间线行
            old = path.read_text(encoding="utf-8")
            tl = old.split("## 时间线")[1].strip()
            new = (
                "---\ntopic: 收工闸\ndomain: agent开发\ncreated: 2026-07-31\n---\n\n"
                "## 概述\n\n- 第一条要点（源自会话 sid-1）\n- 第二条要点（源自会话 sid-2）\n\n"
                "## 关键结论\n\n- 结论更新（源自会话 sid-2）\n\n"
                "## 时间线\n\n" + tl + "\n- 10:30 第二条要点（源自会话 sid-2）\n"
            )
            return {"choices": [{"message": {"content": new}}]}
        return {"choices": [{"message": {"content": json.dumps({
            "topic": "收工闸", "domain": "agent开发",
            "section": "- 第二条要点", "match": "收工闸"})}}]}

    ln.write_living_notes(["第二次记录"], "用户消息2", "sid-2", seq_llm)
    second = path.read_text(encoding="utf-8")

    # .history 有 v1 快照（逐字等于旧版）
    hist = ln_env / ".history" / "agent开发" / "收工闸" / "v1.md"
    assert hist.exists()
    assert hist.read_text(encoding="utf-8") == first
    # version +1、source_sessions 追加
    assert "version: 2" in second
    assert "source_sessions: [sid-1, sid-2]" in second
    # 时间线两行（旧行保留 + 新行追加）
    tl = second.split("## 时间线")[1].strip()
    assert tl.count("- ") == 2


# ── 验收 3：零价值不建 ──────────────────────────────

def test_empty_takeaways_noop(ln_env):
    calls = []

    def spy_llm(prompt, use_tools=False):
        calls.append(prompt)
        return {"choices": [{"message": {"content": "{}"}}]}

    result = ln.write_living_notes([], "随便聊聊", "sid-0", spy_llm)
    assert result["written"] is False
    # library 目录无新文件
    if ln_env.exists():
        assert list(ln_env.rglob("*.md")) == []
    # 零 LLM 调用
    assert calls == []


# ── 验收 4：命名违规矫正 ────────────────────────────

def test_sanitize_bad_name(ln_env):
    llm = _fake_llm({
        "topic": "2026-07-31 收工闸: 实现/细节",
        "domain": "agent:开发",
        "section": "- 要点", "match": None,
    })
    ln.write_living_notes(["要点"], "消息", "sid-1", llm)
    # 文件名不含 / : 等非法字符
    files = [p.name for p in ln_env.rglob("*.md") if p.name != "index.md"]
    assert files == ["2026-07-31 收工闸 实现细节.md"]
    assert "/" not in files[0] and ":" not in files[0] and "*" not in files[0]


# ── 验收 5：误判保守 ────────────────────────────────

def test_match_null_creates_new(ln_env):
    # 先建一个已有笔记
    ln.write_living_notes(["旧主题内容"], "消息1", "sid-1", _fake_llm({
        "topic": "旧主题", "domain": "生活",
        "section": "- 旧要点", "match": None,
    }))
    old_path = ln_env / "生活" / "旧主题.md"
    before = old_path.read_text(encoding="utf-8")

    # 新内容 match=null → 建新笔记，不动旧笔记
    ln.write_living_notes(["全新主题内容"], "消息2", "sid-2", _fake_llm({
        "topic": "新主题", "domain": "生活",
        "section": "- 新要点", "match": None,
    }))
    new_path = ln_env / "生活" / "新主题.md"
    assert new_path.exists()
    # 旧笔记一字未动
    assert old_path.read_text(encoding="utf-8") == before


# ── 验收 6：index 正确 ──────────────────────────────

def test_index_rebuild(ln_env):
    ln.write_living_notes(["A 要点"], "消息1", "sid-1", _fake_llm({
        "topic": "主题甲", "domain": "agent开发",
        "section": "- A 要点", "match": None,
    }))
    ln.write_living_notes(["B 要点"], "消息2", "sid-2", _fake_llm({
        "topic": "主题乙", "domain": "生活",
        "section": "- B 要点", "match": None,
    }))
    index = (ln_env / "index.md").read_text(encoding="utf-8")
    assert "## agent开发" in index
    assert "## 生活" in index
    assert "[[主题甲]]" in index
    assert "[[主题乙]]" in index
    assert "最后更新" in index
    # 两个主题条目，按领域分组
    assert index.count("[[") == 2


# ── 验收 7：总开关 ──────────────────────────────────

def test_env_off_noop(ln_env, monkeypatch):
    monkeypatch.setenv("BOBO_LIVING_NOTES", "off")
    calls = []

    def spy_llm(prompt, use_tools=False):
        calls.append(prompt)
        return {"choices": [{"message": {"content": "{}"}}]}

    result = ln.write_living_notes(["有要点"], "消息", "sid-1", spy_llm)
    assert result["written"] is False
    assert result["error"] == "disabled"
    if ln_env.exists():
        assert list(ln_env.rglob("*.md")) == []
    assert calls == []


# ── 验收 8：library 只读 → 静默降级 ─────────────────

def test_readonly_library_degrade(ln_env):
    ln_env.mkdir(parents=True, exist_ok=True)
    os.chmod(ln_env, 0o555)
    try:
        result = ln.write_living_notes(["有要点"], "消息", "sid-1", _fake_llm({
            "topic": "主题丙", "domain": "general",
            "section": "- 要点", "match": None,
        }))
        # 收工正常完成：不抛异常，返回降级标记
        assert result["written"] is False
        assert result["error"] is not None
    finally:
        os.chmod(ln_env, 0o755)


# ── 补充：LLM 返回乱格式 → 保守降级不落盘 ───────────

def test_unparseable_judge_noop(ln_env):
    def bad_llm(prompt, use_tools=False):
        return {"choices": [{"message": {"content": "这不是JSON"}}]}

    result = ln.write_living_notes(["要点"], "消息", "sid-1", bad_llm)
    assert result["written"] is False
    assert result["error"] is not None
    # 没有建任何笔记（index 除外）
    notes = [p for p in ln_env.rglob("*.md") if p.name != "index.md"]
    assert notes == []
