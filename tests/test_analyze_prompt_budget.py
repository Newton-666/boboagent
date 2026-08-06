"""tests/test_analyze_prompt_budget.py — prompt.budget 数据分析脚本测试。"""

import json
from pathlib import Path

import pytest

from docs.战役工具.analyze_prompt_budget import analyze, iter_events


@pytest.fixture
def sample_events(tmp_path: Path):
    """构造一个临时 events.jsonl，包含 3 条 prompt.budget 和 1 条 decision。"""
    path = tmp_path / "events.jsonl"
    lines = [
        json.dumps({"ts": 1700000000.0, "type": "llm.call", "data": {}}),
        json.dumps({
            "ts": 1700000001.0,
            "type": "prompt.budget",
            "sid": "s1",
            "total_chars": 5000,
            "sections": {
                "identity": 1000,
                "memory": {"chars": 2000, "entries": 5, "total_entries": 10, "evicted": 1},
                "skills": {"chars": 1500, "truncated": True},
                "note_pointers": {"chars": 300, "count": 2, "topics": ["A", "B"]},
            },
        }),
        json.dumps({
            "ts": 1700000002.0,
            "type": "prompt.budget",
            "sid": "s2",
            "total_chars": 4000,
            "sections": {
                "identity": 1000,
                "memory": {"chars": 1500, "entries": 4, "total_entries": 8, "evicted": 0},
                "skills": {"chars": 1000, "truncated": False},
                "note_pointers": {"chars": 0, "count": 0, "topics": []},
            },
        }),
        json.dumps({
            "ts": 1700000003.0,
            "type": "prompt.budget.decision",
            "sid": "s1",
            "total_pool": 5000,
            "total_chars": 5000,
            "allocated": {"identity": 1000, "memory": 2500, "skills": 1000, "note_pointers": 500},
            "used": {"identity": 1000, "memory": 2000, "skills": 1500, "note_pointers": 300},
            "evicted": {"memory": 1, "skills": 0, "note_pointers": 0},
        }),
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def test_iter_events_filters(sample_events):
    events = list(iter_events(sample_events))
    assert len(events) == 3
    assert all(e["type"].startswith("prompt.budget") for e in events)


def test_analyze_report(sample_events):
    events = list(iter_events(sample_events))
    report = analyze(events)

    assert report["summary"]["total_events"] == 3
    assert report["summary"]["budget_events"] == 2
    assert report["summary"]["decision_events"] == 1

    total = report["total_chars"]
    assert total["count"] == 2
    assert total["mean"] == 4500.0
    assert total["min"] == 4000
    assert total["max"] == 5000

    identity = report["sections"]["identity"]
    assert identity["chars"]["mean"] == 1000

    memory = report["sections"]["memory"]
    assert memory["chars"]["mean"] == 1750.0
    assert memory["evicted"]["count"] == 1
    assert memory["evicted"]["total"] == 1

    skills = report["sections"]["skills"]
    assert skills["chars"]["mean"] == 1250.0
    assert report["truncation_events"] == 1

    topics = report["top_note_topics"]
    assert topics == [("A", 1), ("B", 1)]


def test_analyze_empty(tmp_path: Path):
    path = tmp_path / "empty.jsonl"
    path.write_text("", encoding="utf-8")
    events = list(iter_events(path))
    report = analyze(events)
    assert "error" in report
