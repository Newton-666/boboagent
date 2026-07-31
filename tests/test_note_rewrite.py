"""票 LN-2R：活体笔记重写机制验收测试（追加式 → 进化式）。

覆盖 10 项金标准（全部 tmpdir 物理检查，禁止 mock 蒙混）：
  1. 首轮新主题 → 建骨架笔记（frontmatter + 五章节 + version 1）
  2. 第二轮重写 → 旧版进 .history、version+1、last_touched 更新
  3. 冲突覆盖：旧"方案选 A" → 新"改选 B" → 重写后 A 消失、B 在
  4. 缺失追加：新要点属"待办" → 出现在 ## 待办与未决 章节内，不是文末
  5. 结构校验三拒各一条（缺 frontmatter / 空 / <30%）
  6. 人手段落保护：`· 人手` 行 + `> 用户修订` 引用块逐字保留
  7. 时间线小节：两轮后两行，旧行不被重构
  8. BOBO_LIVING_NOTES=off → 零动作
  9. library 只读 → 收工不炸、有 notes.error 事件
  10. 全量测试零回归（由 run_tests 单独验证）
"""

import json
import os
import sys
from datetime import datetime

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tools.living_notes as ln


@pytest.fixture
def ln_env(tmp_path, monkeypatch):
    """隔离的 library 环境。"""
    library = tmp_path / "library"
    monkeypatch.setattr(ln, "LIBRARY_DIR", library)
    monkeypatch.setattr(ln, "INDEX_PATH", library / "index.md")
    return library


@pytest.fixture
def event_capture(monkeypatch):
    """捕获事件总线写入。"""
    import core.event_bus as eb
    fired = []

    class _Bus:
        def write(self, t, d):
            fired.append((t, d))

    monkeypatch.setattr(eb, "event_bus", _Bus())
    return fired


def _old_note(ln_env, topic="收工闸", domain="agent开发", *,
              last_touched="2026-01-01", tl="- 10:00 旧时间线（源自会话 sid-1）",
              extra_body="") -> object:
    """手工构造一份 v1 旧笔记（固定时间线，避免 wall clock 依赖）。"""
    fm = (
        "---\n"
        f"topic: {topic}\ndomain: {domain}\ncreated: 2026-01-01\n"
        f"last_touched: {last_touched}\nversion: 1\nsource_sessions: [sid-1]\n"
        "---\n\n"
    )
    body = (
        f"## 概述\n\n- 旧概述（源自会话 sid-1）\n\n"
        f"## 关键结论\n\n- 方案选 A（源自会话 sid-1）\n\n"
        "## 决策与原因\n\n- 旧决策（源自会话 sid-1）\n\n"
        "## 待办与未决\n\n- 旧待办（源自会话 sid-1）\n\n"
        f"## 时间线\n\n{tl}\n"
        f"{extra_body}"
    )
    d = ln_env / domain
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{topic}.md"
    p.write_text(fm + body, encoding="utf-8")
    return p


def _default_builder(old: str, *, drop_human=False) -> str:
    """标准重写输出：保留时间线旧行 + 本轮追加一行；可丢弃人手行（模拟 LLM 违规）。"""
    tl = old.split("## 时间线")[1].strip()
    return (
        "---\ntopic: 收工闸\ndomain: agent开发\ncreated: 2026-01-01\n---\n\n"
        "## 概述\n\n- 新概述（源自会话 sid-2）\n\n"
        "## 关键结论\n\n- 方案改选 B（源自会话 sid-2）\n\n"
        "## 决策与原因\n\n- 旧决策（源自会话 sid-1）\n\n"
        "## 待办与未决\n\n- 新待办项（源自会话 sid-2）\n\n"
        "## 时间线\n\n" + tl + "\n- 10:30 本轮要点（源自会话 sid-2）\n"
    )


def _rewrite_llm(path, builder, match_topic="收工闸"):
    """判定返回 match 命中 + 重写输出由 builder(旧笔记全文) 构造（无 mock）。"""
    def seq(prompt, use_tools=False):
        if "旧笔记全文" in str(prompt):
            content = builder(path.read_text(encoding="utf-8"))
            return {"choices": [{"message": {"content": content}}]}
        return {"choices": [{"message": {"content": json.dumps({
            "topic": match_topic, "domain": "agent开发",
            "section": "- 本轮要点", "match": match_topic})}}]}
    return seq


# ── 验收 1：首轮新主题 → 骨架笔记 ───────────────────

def test_new_topic_skeleton(ln_env):
    def llm(prompt, use_tools=False):
        user = prompt[-1]["content"] if isinstance(prompt, list) else str(prompt)
        if "本轮完整回复" in user:  # 成文调用
            return {"choices": [{"message": {"content": (
                "---\ntopic: 新主题\ndomain: agent开发\ncreated: 2026-07-31\n---\n\n"
                "## 概述\n\n- 要点一（源自会话 sid-1）\n- 要点二（源自会话 sid-1）\n\n"
                "## 关键结论\n\n- 结论（源自会话 sid-1）\n\n"
                "## 时间线\n\n- 10:30 本轮要点（源自会话 sid-1）\n"
            )}}]}
        return {"choices": [{"message": {"content": json.dumps({
            "topic": "新主题", "domain": "agent开发",
            "section": "- 要点一\n- 要点二", "match": None})}}]}
    result = ln.write_living_notes(["要点一"], "消息", "sid-1", llm)
    assert result["written"] is True and result["is_new"] is True
    path = ln_env / "agent开发" / "新主题.md"
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---")
    for field in ["topic: 新主题", "domain: agent开发", "created:",
                  "last_touched:", "version: 1", "source_sessions: [sid-1]"]:
        assert field in text
    for sec in ["概述", "关键结论", "时间线"]:
        assert f"## {sec}" in text
    assert "（源自会话 sid-1）" in text


# ── 验收 2：第二轮重写 → .history + version+1 ────────

def test_rewrite_snapshot_and_version(ln_env):
    path = _old_note(ln_env)
    before = path.read_text(encoding="utf-8")
    result = ln.write_living_notes(["本轮要点"], "消息", "sid-2",
                                   _rewrite_llm(path, _default_builder))
    assert result["written"] is True and result["is_new"] is False
    # 旧版整篇快照进 .history
    hist = ln_env / ".history" / "agent开发" / "收工闸" / "v1.md"
    assert hist.exists()
    assert hist.read_text(encoding="utf-8") == before
    # version+1、last_touched 更新为今天、source_sessions 追加
    after = path.read_text(encoding="utf-8")
    assert "version: 2" in after
    assert f"last_touched: {datetime.now().strftime('%Y-%m-%d')}" in after
    assert "source_sessions: [sid-1, sid-2]" in after


# ── 验收 3：冲突覆盖 ────────────────────────────────

def test_conflict_override(ln_env):
    path = _old_note(ln_env)  # 关键结论含"方案选 A"
    ln.write_living_notes(["改选 B"], "方案冲突", "sid-2",
                          _rewrite_llm(path, _default_builder))
    after = path.read_text(encoding="utf-8")
    # 旧结论 A 被替换：A 句消失、B 在
    assert "方案选 A" not in after
    assert "改选 B" in after


# ── 验收 4：缺失追加进对应章节（不是文末）───────────

def test_append_into_section(ln_env):
    path = _old_note(ln_env)
    ln.write_living_notes(["新待办项"], "消息", "sid-2",
                          _rewrite_llm(path, _default_builder))
    after = path.read_text(encoding="utf-8")
    # "新待办项" 出现在 ## 待办与未决 章节内
    todo_sec = after.split("## 待办与未决")[1].split("## ")[0]
    assert "新待办项" in todo_sec
    # 不在文末（时间线之后没有）
    tl_sec = after.split("## 时间线")[1]
    assert "新待办项" not in tl_sec


# ── 验收 5：结构校验三拒 ────────────────────────────

def test_reject_missing_frontmatter(ln_env):
    path = _old_note(ln_env)
    before = path.read_text(encoding="utf-8")
    bad = lambda old: "## 概述\n\n- 没有 frontmatter\n"
    result = ln.write_living_notes(["要点"], "消息", "sid-2",
                                   _rewrite_llm(path, bad))
    assert result["written"] is False
    assert "structure check" in result["error"]
    # 旧版保留
    assert path.read_text(encoding="utf-8") == before


def test_reject_empty_body(ln_env):
    path = _old_note(ln_env)
    before = path.read_text(encoding="utf-8")
    bad = lambda old: "---\ntopic: 收工闸\ndomain: agent开发\ncreated: 2026-01-01\n---\n"
    result = ln.write_living_notes(["要点"], "消息", "sid-2",
                                   _rewrite_llm(path, bad))
    assert result["written"] is False
    assert "structure check" in result["error"]
    assert path.read_text(encoding="utf-8") == before


def test_reject_too_short(ln_env):
    path = _old_note(ln_env)
    before = path.read_text(encoding="utf-8")
    short = "---\ntopic: 收工闸\ndomain: agent开发\ncreated: 2026-01-01\n---\n\n## 概述\n\n- 短\n"
    assert len(short) < len(before) * 0.3
    bad = lambda old: short
    result = ln.write_living_notes(["要点"], "消息", "sid-2",
                                   _rewrite_llm(path, bad))
    assert result["written"] is False
    assert "structure check" in result["error"]
    assert path.read_text(encoding="utf-8") == before


# ── 验收 6：人手段落保护 ────────────────────────────

def test_human_lines_protected(ln_env):
    path = _old_note(ln_env, extra_body="- 生产配置项 ABC · 人手\n\n"
                                        "> 用户修订\n"
                                        "> 这个结论必须逐字保留，不许改\n")
    before = path.read_text(encoding="utf-8")
    # 正常路径：LLM 保留人手行 → 重写成功，人手行逐字仍在
    result = ln.write_living_notes(["要点"], "消息", "sid-2",
                                   _rewrite_llm(path, _default_builder))
    assert result["written"] is True
    after = path.read_text(encoding="utf-8")
    assert "- 生产配置项 ABC · 人手" in after
    assert "> 用户修订\n> 这个结论必须逐字保留，不许改" in after

    # 拒绝路径：LLM 丢掉人手行 → 拒写、旧版保留
    path2 = _old_note(ln_env, topic="主题二", extra_body="- 关键手改项 · 人手\n")
    before2 = path2.read_text(encoding="utf-8")
    def dropping_builder(old):
        # 去掉所有 · 人手 行
        kept = "\n".join(l for l in old.split("\n") if "· 人手" not in l)
        return _default_builder(kept)
    result2 = ln.write_living_notes(["要点"], "消息", "sid-3",
                                    _rewrite_llm(path2, dropping_builder, match_topic="主题二"))
    assert result2["written"] is False
    assert "structure check" in result2["error"]
    assert path2.read_text(encoding="utf-8") == before2


# ── 验收 7：时间线两轮两行、不被重构 ────────────────

def test_timeline_two_rounds(ln_env):
    path = _old_note(ln_env)  # 时间线 1 行：- 10:00 旧时间线（源自会话 sid-1）
    ln.write_living_notes(["本轮要点"], "消息", "sid-2",
                          _rewrite_llm(path, _default_builder))
    after = path.read_text(encoding="utf-8")
    tl = after.split("## 时间线")[1].strip()
    # 两行：旧行原样保留 + 新行追加
    assert tl.count("- ") == 2
    assert "- 10:00 旧时间线（源自会话 sid-1）" in tl
    assert "- 10:30 本轮要点（源自会话 sid-2）" in tl


# ── 验收 8：总开关 off → 零动作 ─────────────────────

def test_env_off_noop(ln_env, monkeypatch):
    monkeypatch.setenv("BOBO_LIVING_NOTES", "off")
    calls = []

    def spy(prompt, use_tools=False):
        calls.append(prompt)
        return {"choices": [{"message": {"content": "{}"}}]}

    result = ln.write_living_notes(["有要点"], "消息", "sid-1", spy)
    assert result["written"] is False
    assert result["error"] == "disabled"
    if ln_env.exists():
        assert list(ln_env.rglob("*.md")) == []
    assert calls == []


# ── 验收 9：library 只读 → 不炸 + notes.error ───────

def test_readonly_library_notes_error(ln_env, event_capture):
    path = _old_note(ln_env)
    os.chmod(ln_env, 0o555)
    try:
        result = ln.write_living_notes(["要点"], "消息", "sid-2",
                                       _rewrite_llm(path, _default_builder))
        # 收工不炸、降级返回
        assert result["written"] is False
        assert result["error"] is not None
        # 有 notes.error 事件
        assert any(t == "notes.error" for t, _ in event_capture)
    finally:
        os.chmod(ln_env, 0o755)
