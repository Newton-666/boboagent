"""票 TICKET-022：会话笔记台账验收测试。

验证 injector._build_session_notes_ledger：
1. 仅列出本会话产出，他 sid 笔记不出现
2. 零事件 / 文件缺失 → 静默省略
3. 预算超限 → 中间省略 + 首尾保留
4. notes.updated 覆盖 notes.written
5. prompt.budget 事件带 session_notes 字段
"""

import json
import os
import tempfile
import time
from unittest.mock import patch

import pytest

from core.event_bus import EventBus
from core.injector import PromptInjector


class DummyEngine:
    """最小 engine stub，只暴露 injector 需要访问的属性。"""
    def __init__(self):
        self._pending_diff = ""
        self.current_user_input = ""
        self.history = []
        self._compressing = False
        self._just_compressed = False
        self.tracker = _DummyTracker()
        self.proactive = _DummyProactive()
        self.skill_loader = _DummySkillLoader()
        self._phase_pending_cleanup = False
        self._worker_reminded = True
        self._step_count = 0
        self.MAX_HISTORY_MESSAGES = 200
        self.STATE_EXECUTING = "executing"
        self.state = "idle"
        self._compressed_this_turn = False
        self._session_written_files = set()


class _DummyTracker:
    _change_log = []
    _read_files = {}
    def log_change(self, desc, path=""):
        self._change_log.append({"desc": desc, "path": path})
    @property
    def recent_changes(self):
        return self._change_log[-5:]
    @property
    def recent_reads(self):
        return list(self._read_files.items())[-3:]


class _DummyProactive:
    def inject_context(self, messages):
        return messages


class _DummySkillLoader:
    def load_standards(self):
        return []
    def list_available(self):
        return ""


# ── helpers ──

def _make_event(event_type: str, sid: str, path: str, topic: str,
                version: int = 1, ts: float = None) -> dict:
    return {
        "ts": ts or time.time(),
        "type": event_type,
        "sid": sid,
        "path": path,
        "topic": topic,
        "version": version,
    }


def _write_events(log_dir: str, events: list[dict]):
    """写入事件到临时 events.jsonl。"""
    from core.event_bus import EventBus
    bus = EventBus.reset(log_dir=log_dir)
    for e in events:
        bus.write(e["type"], {k: v for k, v in e.items() if k not in ("ts", "type")})


# ── 测试 ──

class TestSessionNotesLedger:
    """验收 1：仅列出本会话产出，他 sid 不出现。"""

    def test_only_own_session_notes(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_dir = tmp
            my_sid = "sid-abc"
            other_sid = "sid-xyz"
            t0 = time.time()

            events = [
                _make_event("notes.written", my_sid, "/tmp/a.md", "我的笔记A", 1, t0),
                _make_event("notes.written", my_sid, "/tmp/b.md", "我的笔记B", 1, t0 + 1),
                _make_event("notes.written", my_sid, "/tmp/c.md", "我的笔记C", 1, t0 + 2),
                _make_event("notes.written", other_sid, "/tmp/d.md", "他人笔记", 1, t0 + 3),
                _make_event("notes.written", other_sid, "/tmp/e.md", "他人笔记2", 1, t0 + 4),
            ]
            _write_events(log_dir, events)

            bus = EventBus.reset(log_dir=log_dir)
            inj = PromptInjector(DummyEngine())
            text, stats = inj._build_session_notes_ledger(my_sid)

            assert stats["session_notes"] == 3
            assert "我的笔记A" in text
            assert "我的笔记B" in text
            assert "我的笔记C" in text
            assert "他人笔记" not in text
            assert "他人笔记2" not in text
            assert "共 3 篇" in text or "已产出笔记 3 篇" in text

    def test_no_events_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            bus = EventBus.reset(log_dir=tmp)
            inj = PromptInjector(DummyEngine())
            text, stats = inj._build_session_notes_ledger("sid-nonexist")

            assert text == ""
            assert stats["session_notes"] == 0

    def test_missing_events_file_returns_empty(self):
        """events.jsonl 不存在 → 静默省略。"""
        inj = PromptInjector(DummyEngine())
        # 构造一个指向不存在文件的 event_bus
        with tempfile.TemporaryDirectory() as tmp:
            bus = EventBus.reset(log_dir=tmp)
            # filepath 指向不存在的文件：不先写事件，直接删除目录
            nonexistent = os.path.join(tmp, "events.jsonl")
            assert not os.path.exists(nonexistent)
            text, stats = inj._build_session_notes_ledger("sid-any")
            assert text == ""
            assert stats["session_notes"] == 0

    def test_empty_session_id_returns_empty(self):
        inj = PromptInjector(DummyEngine())
        text, stats = inj._build_session_notes_ledger("")
        assert text == ""
        assert stats["session_notes"] == 0

    def test_updated_overwrites_written(self):
        """notes.updated 覆盖 notes.written 的同路径条目。"""
        with tempfile.TemporaryDirectory() as tmp:
            my_sid = "sid-abc"
            t0 = time.time()
            events = [
                _make_event("notes.written", my_sid, "/tmp/same.md", "初始", 1, t0),
                _make_event("notes.updated", my_sid, "/tmp/same.md", "初始", 2, t0 + 1),
            ]
            _write_events(tmp, events)

            bus = EventBus.reset(log_dir=tmp)
            inj = PromptInjector(DummyEngine())
            text, stats = inj._build_session_notes_ledger(my_sid)

            assert stats["session_notes"] == 1
            assert "v2" in text
            assert "初始" in text

    def test_budget_overflow_truncates_middle(self):
        """预算超限：首尾保留中间省略。"""
        with tempfile.TemporaryDirectory() as tmp:
            my_sid = "sid-abc"
            t0 = time.time()
            events = []
            for i in range(15):
                events.append(
                    _make_event("notes.written", my_sid,
                                f"/tmp/note_{i}.md", f"笔记{i}", 1, t0 + i))
            _write_events(tmp, events)

            bus = EventBus.reset(log_dir=tmp)
            inj = PromptInjector(DummyEngine())
            text, stats = inj._build_session_notes_ledger(my_sid)

            assert stats["session_notes"] == 15
            # 首尾应出现
            assert "笔记0" in text
            assert "笔记14" in text
            assert "共 15 篇" in text or "已产出笔记 15 篇" in text
            # 翻阅纪律必须在
            assert "翻阅纪律" in text
            assert "禁止无目标批量遍历" in text


class TestPromptBudgetSessionNotes:
    """验收 5：prompt.budget 事件带 session_notes 字段。"""

    def test_session_notes_in_budget_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            my_sid = "sid-budget-test"
            t0 = time.time()
            events = [
                _make_event("notes.written", my_sid, "/tmp/x.md", "X笔记", 1, t0),
                _make_event("notes.written", my_sid, "/tmp/y.md", "Y笔记", 1, t0 + 1),
                _make_event("notes.written", my_sid, "/tmp/z.md", "Z笔记", 1, t0 + 2),
            ]
            _write_events(tmp, events)
            bus = EventBus.reset(log_dir=tmp)

            inj = PromptInjector(DummyEngine())
            messages = inj.build_messages(
                system_prompt="你是 Bobo。",
                user_input="你好",
                tools_schema=[],
                extra_categories=set(),
                session_id=my_sid,
            )

            # 检查 events.jsonl 中是否有 prompt.budget 事件带 session_notes
            with open(bus.filepath, "r") as f:
                budget_events = [
                    json.loads(l) for l in f
                    if '"type":"prompt.budget"' in l
                ]

            assert len(budget_events) >= 1
            be = budget_events[-1]
            sections = be.get("sections", {})
            note_ptrs = sections.get("note_pointers", {})
            assert note_ptrs.get("session_notes") == 3, \
                f"session_notes 应为 3，实际: {note_ptrs}"


class TestDisciplineFooter:
    """翻阅纪律尾部文案。"""

    def test_footer_present_when_notes_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            my_sid = "sid-disc"
            events = [
                _make_event("notes.written", my_sid, "/tmp/a.md", "测试", 1, time.time()),
            ]
            _write_events(tmp, events)
            bus = EventBus.reset(log_dir=tmp)

            inj = PromptInjector(DummyEngine())
            text, stats = inj._build_session_notes_ledger(my_sid)

            assert stats["session_notes"] == 1
            assert "翻阅纪律" in text
            assert "read_local_file" in text
            assert "禁止无目标批量遍历 library" in text

    def test_no_footer_when_no_notes(self):
        inj = PromptInjector(DummyEngine())
        text, stats = inj._build_session_notes_ledger("nonexist")
        assert text == ""
        assert stats["session_notes"] == 0
