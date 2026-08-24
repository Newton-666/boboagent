"""C1 观察总线单元测试——信号分类/累积/触发（确定性，护栏：信号可测）。"""
import json
import os
import tempfile
from pathlib import Path

from core.observer import (
    parse_events, accumulate, find_triggers, observe,
    _classify_error, THRESHOLD,
)


def _write_events(events: list, path: Path):
    with open(path, "w", encoding="utf-8") as f:
        for ev in events:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")


def test_classify_error():
    assert _classify_error("invalid regex pattern") == "regex"
    assert _classify_error("FileNotFoundError: no such file") == "path"
    assert _classify_error("PermissionError: denied") == "permission"
    assert _classify_error("connection timed out") == "network"
    assert _classify_error("奇怪的错误") == "other"


def test_parse_tool_signals():
    tmp = Path(tempfile.mkdtemp())
    ev_path = tmp / "events.jsonl"
    _write_events([
        {"type": "tool.exec", "tool": "edit_file", "status": "error",
         "error_detail": "invalid regex pattern"},
        {"type": "tool.exec", "tool": "edit_file", "status": "ok"},
        {"type": "state.change", "from": "THINKING", "to": "EXECUTING"},
        {"type": "tool.exec", "tool": "run_tests", "status": "ok"},
    ], ev_path)
    sigs = parse_events(str(ev_path))
    assert len(sigs) == 3
    fails = [s for s in sigs if s.result == "fail"]
    assert len(fails) == 1 and fails[0].error_type == "regex"


def test_accumulate_threshold():
    # 同 (tool_exec, edit_file, fail, regex) 3 次 → 过阈值
    tmp = Path(tempfile.mkdtemp())
    ev_path = tmp / "events.jsonl"
    _write_events([
        {"type": "tool.exec", "tool": "edit_file", "status": "error",
         "error_detail": "invalid regex"},
        {"type": "tool.exec", "tool": "edit_file", "status": "error",
         "error_detail": "regex error"},
        {"type": "tool.exec", "tool": "edit_file", "status": "error",
         "error_detail": "bad regex"},
        {"type": "tool.exec", "tool": "edit_file", "status": "ok"},
    ], ev_path)
    triggers = observe(str(ev_path))
    assert len(triggers) == 1, f"应 1 个触发，实际 {triggers}"
    (key, count) = triggers[0]
    assert key[0] == "tool_exec" and key[1] == "edit_file" and key[2] == "fail"
    assert count >= THRESHOLD


def test_below_threshold_no_trigger():
    tmp = Path(tempfile.mkdtemp())
    ev_path = tmp / "events.jsonl"
    _write_events([
        {"type": "tool.exec", "tool": "edit_file", "status": "error", "error_detail": "x"},
        {"type": "tool.exec", "tool": "edit_file", "status": "error", "error_detail": "x"},
    ], ev_path)
    assert observe(str(ev_path)) == []


def test_accumulate_counts():
    tmp = Path(tempfile.mkdtemp())
    ev_path = tmp / "events.jsonl"
    _write_events([
        {"type": "tool.exec", "tool": "a", "status": "ok"},
        {"type": "tool.exec", "tool": "b", "status": "ok"},
        {"type": "tool.exec", "tool": "a", "status": "ok"},
    ], ev_path)
    sigs = parse_events(str(ev_path))
    counts = accumulate(sigs)
    assert counts[("tool_exec", "a", "ok", "")] == 2
    assert counts[("tool_exec", "b", "ok", "")] == 1
