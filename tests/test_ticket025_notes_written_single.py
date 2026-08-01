"""TICKET-025: notes.written 重复发射修复 — 一次写入只发一条带 sid 的事件"""

import json
from pathlib import Path

import pytest

from tools.living_notes import write_living_notes


class FakeLLM:
    """模拟 LLM 调用，返回 topic=新主题、match=null 的 judge 响应 + 新笔记正文。"""

    def __init__(self, topic="测试主题", domain="agent开发"):
        self.calls = []
        self._topic = topic
        self._domain = domain

    def __call__(self, prompt, use_tools=False):
        self.calls.append(prompt)
        call_idx = len(self.calls)
        if call_idx == 1:
            # judge 调用：返回 OpenAI API 格式，section 必填
            return {
                "choices": [{
                    "message": {
                        "content": json.dumps({
                            "topic": self._topic,
                            "domain": self._domain,
                            "section": "- 测试要点1\n- 测试要点2",
                            "match": None,
                        }, ensure_ascii=False),
                    }
                }]
            }
        elif call_idx == 2:
            # 新笔记 LLM 成文调用：必须有 frontmatter
            return {
                "choices": [{
                    "message": {
                        "content": "---\n"
                                   "topic: 测试主题\n"
                                   "domain: agent开发\n"
                                   "created: 2026-08-01\n"
                                   "---\n\n"
                                   "## 概述\n\n测试笔记正文。\n\n"
                                   "## 关键结论\n\n结论内容。\n\n"
                                   "## 决策与原因\n\n决策内容。\n\n"
                                   "## 待办与未决\n\n待办内容。\n\n"
                                   "## 时间线\n\n- 20:00 要点\n",
                    }
                }]
            }
        return {"choices": [{"message": {"content": "{}"}}]}


class TestNotesWrittenSingleEmit:
    """TICKET-025：一次写入只发射一条 notes.written 事件，且带 sid。"""

    def test_new_note_emits_single_written_with_sid(self, tmp_path, monkeypatch):
        """新建笔记 → _write_new_note 发射 notes.written（带 sid），主函数不再重复发射。"""
        events = []

        def fake_emit(event_type, data):
            events.append((event_type, data))

        monkeypatch.setattr("tools.living_notes._emit", fake_emit)
        monkeypatch.setattr("tools.living_notes.LIBRARY_DIR",
                            tmp_path / "library")
        (tmp_path / "library").mkdir(parents=True, exist_ok=True)

        llm = FakeLLM()
        result = write_living_notes(
            takeaways=["测试要点1", "测试要点2"],
            user_msg="写一篇笔记",
            sid="test-sid-001",
            llm_call=llm,
            full_reply="本轮完整回复正文",
        )

        assert result["written"] is True
        assert result["is_new"] is True
        assert result.get("error") is None

        written_events = [e for e in events if e[0] == "notes.written"]
        assert len(written_events) == 1, (
            f"预期 1 次 notes.written，实际 {len(written_events)} 次: {written_events}"
        )

        event_type, data = written_events[0]
        assert data.get("sid") == "test-sid-001", (
            f"notes.written 缺少 sid: {data}"
        )

    def test_rewrite_note_emits_updated_not_written(self, tmp_path, monkeypatch):
        """已有笔记重写 → _rewrite_note 发射 notes.updated（带 sid），不发射 notes.written。"""
        events = []

        def fake_emit(event_type, data):
            events.append((event_type, data))

        monkeypatch.setattr("tools.living_notes._emit", fake_emit)
        monkeypatch.setattr("tools.living_notes.LIBRARY_DIR",
                            tmp_path / "library")
        lib_dir = tmp_path / "library" / "agent开发"
        lib_dir.mkdir(parents=True, exist_ok=True)

        existing_path = lib_dir / "已有主题.md"
        existing_path.write_text("""---
topic: 已有主题
domain: agent开发
created: 2026-07-31
last_touched: 2026-07-31
version: 1
source_sessions: [old-sid]
---

## 概述

旧笔记内容。

## 时间线

- 19:00 旧要点
""")

        class MatchLLM(FakeLLM):
            def __call__(self, prompt, use_tools=False):
                self.calls.append(prompt)
                call_idx = len(self.calls)
                if call_idx == 1:
                    return {
                        "choices": [{
                            "message": {
                                "content": json.dumps({
                                    "topic": "已有主题",
                                    "domain": "agent开发",
                                    "section": "- 更新要点",
                                    "match": "已有主题",
                                }, ensure_ascii=False),
                            }
                        }]
                    }
                elif call_idx == 2:
                    return {
                        "choices": [{
                            "message": {
                                "content": "---\n"
                                           "topic: 已有主题\n"
                                           "domain: agent开发\n"
                                           "created: 2026-07-31\n"
                                           "---\n\n"
                                           "## 概述\n\n更新后的概述。\n\n"
                                           "## 时间线\n\n"
                                           "- 19:00 旧要点\n"
                                           "- 20:00 新要点\n",
                            }
                        }]
                    }
                return {"choices": [{"message": {"content": "{}"}}]}

        llm = MatchLLM()
        result = write_living_notes(
            takeaways=["更新要点"],
            user_msg="更新已有主题",
            sid="test-sid-002",
            llm_call=llm,
            full_reply="本轮完整回复正文",
        )

        assert result["written"] is True
        assert result["is_new"] is False

        written_events = [e for e in events if e[0] == "notes.written"]
        assert len(written_events) == 0, (
            f"重写不应发射 notes.written，但发射了 {len(written_events)} 次: {written_events}"
        )

        updated_events = [e for e in events if e[0] == "notes.updated"]
        assert len(updated_events) == 1, (
            f"预期 1 次 notes.updated，实际 {len(updated_events)} 次"
        )
        assert updated_events[0][1].get("sid") == "test-sid-002"
