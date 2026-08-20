"""TICKET-PROFILE-2 验收测试 — USER.md 引擎写入闸门 + 版本快照存储。

覆盖（票文验收）：
1. 行为模板匹配：偏好/禁忌/工作流 三类各 1 条通过
2. 纯事实拒绝："用户喜欢冰美式" → 不写入 + reason="not_behavioral"
3. 版本快照：写入后 profile_versions.jsonl 追加 1 行，含 ts/diff 字段
4. 重复写入：同 category 同内容不重复追加（去重）
5. profile.update 事件：写入成功时 emit（payload: category/entry/diff）
"""

import json

import pytest

import core.profile_writer as pw


@pytest.fixture(autouse=True)
def silence_event_bus(monkeypatch):
    """event_bus 不写真实 events.jsonl（测试日志隔离），同时捕获事件。"""
    import core.event_bus as eb

    fired = []

    class _Bus:
        def write(self, t, d):
            fired.append((t, d))

    monkeypatch.setattr(eb, "event_bus", _Bus())
    return fired


@pytest.fixture
def iso(tmp_path, monkeypatch):
    """隔离数据文件：knowledge_base.json 与 profile_versions.jsonl 指向 tmp。"""
    kb = tmp_path / "knowledge_base.json"
    kb.write_text(json.dumps({"entries": [], "profile": {}}), encoding="utf-8")
    versions = tmp_path / "profile_versions.jsonl"
    monkeypatch.setattr(pw, "_KB_PATH", kb)
    monkeypatch.setattr(pw, "_VERSIONS_FILE", versions)
    return kb, versions


def _read_kb(kb):
    return json.loads(kb.read_text(encoding="utf-8"))


def _read_versions(versions):
    if not versions.exists():
        return []
    return [
        json.loads(ln) for ln in versions.read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]


class TestBehavioralTemplates:
    def test_preference_template_passes(self, iso):
        """偏好模板：'偏好 X' 命中 → 写入成功。"""
        kb, versions = iso
        r = pw.write_user_profile("用户偏好直接执行工具调用，不说明、不道歉", "preference")
        assert r["ok"] is True
        assert r["reason"] is None
        kb_data = _read_kb(kb)
        assert kb_data["profile"]["preference"]["value"] == "用户偏好直接执行工具调用，不说明、不道歉"
        assert len(_read_versions(versions)) == 1

    def test_taboo_template_passes(self, iso):
        """禁忌模板：'不要 X' 命中 → 写入成功。"""
        kb, versions = iso
        r = pw.write_user_profile("不要用 sudo 执行命令", "taboo")
        assert r["ok"] is True
        assert r["reason"] is None
        assert "taboo" in _read_kb(kb)["profile"]

    def test_workflow_template_passes(self, iso):
        """工作流模板：'先 X 再 Y' 命中 → 写入成功。"""
        kb, versions = iso
        r = pw.write_user_profile("先理解数据，再写运行脚本", "workflow")
        assert r["ok"] is True
        assert r["reason"] is None
        assert "workflow" in _read_kb(kb)["profile"]


class TestFactRejection:
    def test_fact_rejected(self, iso):
        """纯事实：'用户喜欢冰美式' 不匹配任何模板 → 拒绝 + reason 正确。"""
        kb, versions = iso
        r = pw.write_user_profile("用户喜欢冰美式", "preference")
        assert r["ok"] is False
        assert r["reason"] == "not_behavioral"
        # 不写入 knowledge_base
        assert "preference" not in _read_kb(kb)["profile"]
        # 不追加版本快照
        assert _read_versions(versions) == []

    def test_empty_entry_rejected(self, iso):
        """空/非字符串 entry → 拒绝 not_behavioral。"""
        kb, versions = iso
        assert pw.write_user_profile("", "preference")["reason"] == "not_behavioral"
        assert pw.write_user_profile(None, "preference")["reason"] == "not_behavioral"
        assert _read_versions(versions) == []


class TestVersionSnapshot:
    def test_snapshot_appended_with_ts_and_diff(self, iso):
        """写入后 jsonl 追加 1 行，含 ts/diff 字段。"""
        kb, versions = iso
        r = pw.write_user_profile("用户偏好直接执行工具调用，不说明、不道歉", "preference")
        assert r["ok"] is True
        lines = _read_versions(versions)
        assert len(lines) == 1
        rec = lines[0]
        assert "ts" in rec and rec["ts"] > 0
        assert "diff" in rec and rec["diff"] == "+ 用户偏好直接执行工具调用，不说明、不道歉"
        assert rec["category"] == "preference"
        assert rec["entry"] == "用户偏好直接执行工具调用，不说明、不道歉"
        assert rec["reason"] == "behavioral"
        assert rec["signal_source"] == "user"

    def test_snapshot_diff_old_to_new(self, iso):
        """更新已有画像：diff 记 old → new。"""
        kb, versions = iso
        pw.write_user_profile("用户偏好直接执行工具调用，不说明、不道歉", "preference")
        pw.write_user_profile("用户偏好直接执行工具调用，不解释、不道歉", "preference")
        lines = _read_versions(versions)
        assert len(lines) == 2
        assert lines[1]["diff"] == "用户偏好直接执行工具调用，不说明、不道歉 → 用户偏好直接执行工具调用，不解释、不道歉"


class TestDedup:
    def test_duplicate_not_appended(self, iso):
        """同 category 同内容重复写入 → 不追加（去重）。"""
        kb, versions = iso
        r1 = pw.write_user_profile("用户偏好直接执行工具调用，不说明、不道歉", "preference")
        assert r1["ok"] is True
        r2 = pw.write_user_profile("用户偏好直接执行工具调用，不说明、不道歉", "preference")
        assert r2["ok"] is False
        assert r2["reason"] == "duplicate"
        # 版本快照仍只有 1 行
        assert len(_read_versions(versions)) == 1
        # knowledge_base 值不变
        assert _read_kb(kb)["profile"]["preference"]["value"] == "用户偏好直接执行工具调用，不说明、不道歉"


class TestEvent:
    def test_profile_update_event_emitted(self, iso, silence_event_bus):
        """写入成功 → emit profile.update 事件（category/entry/diff）。"""
        kb, versions = iso
        pw.write_user_profile("用户偏好直接执行工具调用，不说明、不道歉", "preference")
        events = [d for t, d in silence_event_bus if t == "profile.update"]
        assert events, "应 emit profile.update 事件"
        assert events[0]["category"] == "preference"
        assert events[0]["entry"] == "用户偏好直接执行工具调用，不说明、不道歉"
        assert "diff" in events[0]

    def test_no_event_on_rejection(self, iso, silence_event_bus):
        """模板拒绝 → 不 emit 事件。"""
        kb, versions = iso
        pw.write_user_profile("用户喜欢冰美式", "preference")
        events = [d for t, d in silence_event_bus if t == "profile.update"]
        assert events == []
