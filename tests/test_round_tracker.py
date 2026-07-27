"""Unit tests for core/round_tracker.py (P1 extraction follow-up)."""

import pytest
from core.round_tracker import RoundTracker


class DummyEngine:
    """Minimal stub so RoundTracker can reference self._engine attributes."""
    current_depth = 0
    history = []
    WORKSPACE_DIR = "/tmp/bobo_test_workspace"

    def _append_to_history(self, role, content):
        pass


@pytest.fixture
def tracker():
    return RoundTracker(DummyEngine())


class TestRecordRead:
    def test_stores_content(self, tracker):
        content = "This is long enough content to pass the 40-char minimum check for read tracking"
        tracker.record_read("/tmp/a.txt", content)
        assert "/tmp/a.txt" in tracker._read_files
        assert tracker._read_files["/tmp/a.txt"] == content[:200]

    def test_truncates_long_content(self, tracker):
        long_content = "X" * 500
        tracker.record_read("/tmp/b.txt", long_content)
        assert len(tracker._read_files["/tmp/b.txt"]) == 200

    def test_evicts_oldest_when_over_10(self, tracker):
        for i in range(15):
            tracker.record_read(f"/tmp/{i}.txt", f"content {i} is long enough to meet minimum length requirement")
        assert len(tracker._read_files) == 10
        assert "/tmp/0.txt" not in tracker._read_files
        assert "/tmp/14.txt" in tracker._read_files

    def test_no_dict_wrapper_stored(self, tracker):
        """record_read stores pure content, not dict repr (P1毛刺1 fix)."""
        content = "real content here, long enough to pass the 40-char minimum threshold"
        tracker.record_read("/tmp/c.txt", content)
        stored = tracker._read_files["/tmp/c.txt"]
        assert "tool_call_id" not in stored
        assert stored == content[:200]


class TestCompressChangelog:
    def test_noop_when_under_20(self, tracker):
        for i in range(10):
            tracker.log_change(f"change {i}")
        tracker.compress_changelog()
        assert len(tracker._change_log) == 10

    def test_compresses_when_over_20(self, tracker):
        for i in range(25):
            tracker.log_change(f"change {i}")
        tracker.compress_changelog()
        assert len(tracker._change_log) < 25
        # Should contain the history summary
        assert any("[历史改动]" in c["desc"] for c in tracker._change_log)


class TestRecentReads:
    def test_returns_most_recent(self, tracker):
        for i in range(5):
            tracker.record_read(f"/tmp/{i}.txt", f"content for file {i} is long enough to meet the minimum length requirement")
        recent = tracker.recent_reads(limit=3)
        assert len(recent) == 3

    def test_respects_limit(self, tracker):
        for i in range(5):
            tracker.record_read(f"/tmp/{i}.txt", f"content for file {i} with sufficient length to pass the threshold check")
        assert len(tracker.recent_reads(limit=2)) == 2


class TestLogChange:
    def test_logs_and_retrieves(self, tracker):
        tracker.log_change("edit: x.py")
        tracker.log_change("write: y.py")
        changes = tracker.recent_changes(limit=2)
        assert len(changes) == 2
        assert "x.py" in changes[0]["desc"]
        assert "y.py" in changes[1]["desc"]
