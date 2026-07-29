"""票 Y：上下文实验台 — 测试套件"""

import json
import os
import tempfile
from pathlib import Path

import pandas as pd
import pytest

from scripts.context_lab import (
    _calc_amnesia_signals,
    _calc_basic_stats,
    _calc_compression_stats,
    _calc_duration_dist,
    _calc_fault_stats,
    _calc_token_curve,
    _safe_int,
    _validate_thresholds,
    analyze_all,
    analyze_session,
    load_events,
)


# ── 夹具：生成迷你 events.jsonl ──


@pytest.fixture
def sample_events_path():
    """生成包含多种事件类型的迷你 events.jsonl。"""
    events = [
        {"ts": 1000.0, "type": "state.change", "session_id": "s1", "from": "idle", "to": "thinking", "reason": "user input"},
        {"ts": 1001.0, "type": "state.change", "session_id": "s1", "from": "idle", "to": "thinking", "reason": "user input"},
        {"ts": 1002.0, "type": "llm.call", "session_id": "s1", "msg_count": 5, "has_tool_calls": False, "duration_ms": 200, "prompt_tokens": 500, "completion_tokens": 100, "total_tokens": 600},
        {"ts": 1003.0, "type": "state.change", "session_id": "s1", "from": "thinking", "to": "done", "reason": "complete"},
        {"ts": 1004.0, "type": "llm.call", "session_id": "s1", "msg_count": 8, "has_tool_calls": True, "duration_ms": 1500, "prompt_tokens": 800, "completion_tokens": 200, "total_tokens": 1000},
        {"ts": 1005.0, "type": "tool.exec", "session_id": "s1", "name": "read_file", "duration_ms": 100, "cancelled": False, "hard_blocked": False},
        {"ts": 1006.0, "type": "state.change", "session_id": "s1", "from": "thinking", "to": "done", "reason": "complete"},
        {"ts": 1007.0, "type": "engine.thread.exit", "session_id": "s1", "reason": "completed", "duration_ms": 5000},
        # 会话 s2（无压缩）
        {"ts": 2000.0, "type": "state.change", "session_id": "s2", "from": "idle", "to": "thinking", "reason": "user input"},
        {"ts": 2001.0, "type": "llm.call", "session_id": "s2", "msg_count": 3, "has_tool_calls": False, "duration_ms": 300, "prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        {"ts": 2002.0, "type": "state.change", "session_id": "s2", "from": "thinking", "to": "done", "reason": "complete"},
        # 会话 s3（有压缩事件）
        {"ts": 3000.0, "type": "state.change", "session_id": "s3", "from": "idle", "to": "thinking", "reason": "user input"},
        {"ts": 3001.0, "type": "llm.call", "session_id": "s3", "msg_count": 5, "has_tool_calls": False, "duration_ms": 400, "prompt_tokens": 300, "completion_tokens": 70, "total_tokens": 370},
        {"ts": 3002.0, "type": "context.compressed", "session_id": "s3", "pre_tokens": 300, "post_tokens": 120},
        {"ts": 3003.0, "type": "state.change", "session_id": "s3", "from": "thinking", "to": "done", "reason": "complete"},
        {"ts": 3004.0, "type": "tool.exec", "session_id": "s3", "name": "load_result", "duration_ms": 50},
        {"ts": 3005.0, "type": "llm.call", "session_id": "s3", "msg_count": 10, "has_tool_calls": False, "duration_ms": 500, "prompt_tokens": 400, "completion_tokens": 80, "total_tokens": 480},
    ]
    path = Path(tempfile.mktemp(suffix=".jsonl"))
    with open(path, "w") as f:
        for ev in events:
            f.write(json.dumps(ev) + "\n")
    yield path
    path.unlink(missing_ok=True)


# ── load_events ──


class TestLoadEvents:
    def test_loads_and_parses(self, sample_events_path):
        df = load_events(sample_events_path)
        assert len(df) == 17
        assert "ts_dt" in df.columns
        assert list(df["type"].unique()) == ["state.change", "llm.call", "tool.exec", "engine.thread.exit", "context.compressed"]

    def test_empty_file(self):
        path = Path(tempfile.mktemp(suffix=".jsonl"))
        path.write_text("")
        df = load_events(str(path))
        assert df.empty
        path.unlink()

    def test_since_filter(self, sample_events_path):
        df = load_events(sample_events_path, since="1970-01-01")
        assert len(df) == 17
        df_empty = load_events(sample_events_path, since="2030-01-01")
        assert df_empty.empty


# ── _safe_int ──


class TestSafeInt:
    def test_normal(self):
        assert _safe_int(42) == 42
        assert _safe_int(0) == 0

    def test_nan(self):
        assert _safe_int(float("nan")) == 0

    def test_float(self):
        assert _safe_int(3.14) == 3

    def test_string_like(self):
        assert _safe_int("42") == 42


# ── _calc_basic_stats ──


class TestCalcBasicStats:
    def test_s1(self, sample_events_path):
        df = load_events(sample_events_path)
        stats = _calc_basic_stats(df, "s1")
        assert stats["session_id"] == "s1"
        assert stats["llm_calls"] == 2
        assert stats["tool_calls"] == 1
        assert stats["prompt_tokens"] == 1300  # 500 + 800
        assert stats["completion_tokens"] == 300  # 100 + 200


# ── _calc_token_curve ──


class TestCalcTokenCurve:
    def test_s1_curve(self, sample_events_path):
        df = load_events(sample_events_path)
        sdf = df[df["session_id"] == "s1"]
        curve = _calc_token_curve(sdf)
        assert len(curve) == 2
        assert curve[-1]["cumsum"] == 1300  # 500 + 800


# ── _calc_compression_stats ──


class TestCompressionStats:
    def test_s3_compressed(self, sample_events_path):
        df = load_events(sample_events_path)
        sdf = df[df["session_id"] == "s3"]
        comp = _calc_compression_stats(sdf)
        assert comp["compression_count"] == 1
        assert comp["efficiency_ratios"] == [0.4]  # 120/300

    def test_s1_no_compress(self, sample_events_path):
        df = load_events(sample_events_path)
        sdf = df[df["session_id"] == "s1"]
        comp = _calc_compression_stats(sdf)
        assert comp["compression_count"] == 0


# ── analyze_session ──


class TestAnalyzeSession:
    def test_s1_full(self, sample_events_path):
        df = load_events(sample_events_path)
        res = analyze_session(df, "s1")
        assert res["llm_calls"] == 2
        assert res["rounds"] == 2  # 2 state.change → done
        assert res["fault"]["total_exits"] == 1

    def test_s2(self, sample_events_path):
        df = load_events(sample_events_path)
        res = analyze_session(df, "s2")
        assert res["llm_calls"] == 1
        assert res["rounds"] == 1

    def test_s3_compression(self, sample_events_path):
        df = load_events(sample_events_path)
        res = analyze_session(df, "s3")
        assert res["compression"]["compression_count"] == 1
        assert res["amnesia"]["load_result_after_compress"] == 1


# ── analyze_all ──


class TestAnalyzeAll:
    def test_all_sessions(self, sample_events_path):
        df = load_events(sample_events_path)
        results = analyze_all(df)
        assert set(results.keys()) == {"s1", "s2", "s3"}
        assert results["s1"]["llm_calls"] == 2
        assert results["s3"]["compression"]["compression_count"] == 1


# ── _validate_thresholds ──


class TestValidateThresholds:
    def test_results(self, sample_events_path):
        df = load_events(sample_events_path)
        results = analyze_all(df)
        validation = _validate_thresholds(results, budget=60)
        assert validation["budget"] == 60
        assert validation["avg_token_per_round"] > 0
        assert "verdict" in validation


# ── _calc_duration_dist ──


class TestDurationDist:
    def test_s1(self, sample_events_path):
        df = load_events(sample_events_path)
        sdf = df[df["session_id"] == "s1"]
        calls = sdf[sdf["type"] == "llm.call"]
        dist = _calc_duration_dist(calls)
        assert dist["count"] == 2
        assert dist["p50"] == 850.0  # median of 200, 1500
