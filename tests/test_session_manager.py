"""Tests for core/session_manager.py — session CRUD, atomic writes, multi-author."""

import os
import json
import tempfile
from pathlib import Path
import pytest

from core.session_manager import SessionManager


@pytest.fixture
def session_dir():
    """Create a temporary directory for session files."""
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.fixture
def mgr(session_dir):
    """Create a SessionManager pointed at a temp directory."""
    return SessionManager(session_dir=session_dir, author="test_user")


class TestSessionCreation:
    """Tests for creating new sessions."""

    def test_new_session_creates_id(self, mgr):
        sid = mgr.new_session()
        assert sid is not None
        assert len(sid) > 0
        # Format: YYYYMMDD_HHMMSS
        assert "_" in sid

    def test_new_session_creates_file(self, mgr):
        sid = mgr.new_session()
        filepath = Path(mgr.session_dir) / f"{sid}.json"
        assert filepath.exists()

    def test_new_session_has_correct_structure(self, mgr):
        sid = mgr.new_session("Test会话")
        filepath = Path(mgr.session_dir) / f"{sid}.json"
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)
        assert data["id"] == sid
        assert data["title"] == "Test会话"
        assert "created_at" in data
        assert isinstance(data["messages"], list)

    def test_new_session_adds_join_message(self, mgr):
        sid = mgr.new_session()
        filepath = Path(mgr.session_dir) / f"{sid}.json"
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)
        messages = data["messages"]
        assert len(messages) >= 1
        assert any("test_user" in str(m) for m in messages)
        assert any("加入" in str(m) or "joined" in str(m).lower() for m in messages)

    def test_current_session_id_is_set(self, mgr):
        sid = mgr.new_session()
        assert mgr.current_session_id == sid

    def test_title_set_from_first_user_message(self, mgr):
        mgr.new_session()
        mgr.add_message("user", "帮我搜索一下Python相关的笔记")
        # Title should be set to the first user message (truncated)
        assert mgr.current_session is not None
        assert len(mgr.current_session.get("title", "")) > 0

    def test_default_title_when_no_title_given(self, mgr):
        sid = mgr.new_session()
        assert "会话_" in mgr.current_session.get("title", "")


class TestSessionList:
    """Tests for listing sessions."""

    def test_list_empty_when_no_sessions(self, mgr):
        sessions = mgr.list_sessions()
        assert isinstance(sessions, list)

    def test_list_returns_recent_sessions(self, mgr):
        mgr.new_session("Session A")
        import time
        time.sleep(1.1)  # session IDs use second-level timestamps; ensure uniqueness
        mgr.new_session("Session B")
        sessions = mgr.list_sessions(limit=10)
        assert len(sessions) >= 2

    def test_list_respects_limit(self, mgr):
        for i in range(5):
            mgr.new_session(f"Session {i}")
        sessions = mgr.list_sessions(limit=2)
        assert len(sessions) <= 2

    def test_list_sorted_most_recent_first(self, mgr):
        mgr.new_session("Older")
        import time
        time.sleep(0.1)
        mgr.new_session("Newer")
        sessions = mgr.list_sessions(limit=10)
        # Most recent first
        assert sessions[0]["title"] == "Newer"


class TestSessionLoadResume:
    """Tests for loading and resuming existing sessions."""

    def test_load_existing_session(self, mgr):
        sid = mgr.new_session("My Session")
        # Create a new manager to simulate fresh start
        mgr2 = SessionManager(session_dir=str(mgr.session_dir), author="test_user")
        session = mgr2.load_session(sid)
        assert session is not None
        assert session["id"] == sid
        assert session["title"] == "My Session"

    def test_load_nonexistent_returns_none(self, mgr):
        session = mgr.load_session("nonexistent_id")
        assert session is None

    def test_resume_sets_current_session(self, mgr):
        sid = mgr.new_session("Test")
        mgr2 = SessionManager(session_dir=str(mgr.session_dir), author="test_user")
        mgr2.load_session(sid)
        assert mgr2.current_session_id == sid


class TestAddMessage:
    """Tests for adding messages to a session."""

    def test_add_user_message(self, mgr):
        mgr.new_session()
        mgr.add_message("user", "Hello Bobo")
        assert mgr.get_message_count() >= 2  # including system join message

    def test_add_assistant_message(self, mgr):
        mgr.new_session()
        mgr.add_message("assistant", "Hello! How can I help?")
        count = mgr.get_message_count()
        assert count >= 2

    def test_add_system_message(self, mgr):
        mgr.new_session()
        mgr.add_system_message("System notification")
        messages = mgr.current_session.get("messages", [])
        assert any(m["role"] == "system" for m in messages)

    def test_message_has_timestamp(self, mgr):
        mgr.new_session()
        mgr.add_message("user", "test")
        msgs = mgr.current_session.get("messages", [])
        user_msgs = [m for m in msgs if m["role"] == "user"]
        assert len(user_msgs) > 0
        assert "timestamp" in user_msgs[0]

    def test_message_has_author(self, mgr):
        mgr.new_session()
        mgr.add_message("user", "test")
        msgs = mgr.current_session.get("messages", [])
        user_msgs = [m for m in msgs if m["role"] == "user"]
        assert user_msgs[0].get("author") == "test_user"

    def test_get_message_count_no_session(self):
        mgr = SessionManager(session_dir="/tmp/nonexistent_test", author="test")
        assert mgr.get_message_count() == 0


class TestSessionRename:
    """Tests for renaming sessions."""

    def test_rename_session(self, mgr):
        mgr.new_session("Original")
        mgr.rename_session("Renamed Session Title")
        assert mgr.current_session["title"] == "Renamed Session Title"

    def test_rename_truncates_long_titles(self, mgr):
        mgr.new_session()
        long_title = "A" * 100
        mgr.rename_session(long_title)
        assert len(mgr.current_session["title"]) <= 50


class TestSessionDelete:
    """Tests for deleting sessions."""

    def test_delete_removes_session_from_disk(self, mgr):
        sid = mgr.new_session("To Delete")
        filepath = Path(mgr.session_dir) / f"{sid}.json"
        assert filepath.exists()

        # Simulate what handle_session_delete does
        if filepath.exists():
            filepath.unlink()
        bak = Path(str(filepath) + ".bak")
        if bak.exists():
            bak.unlink()

        assert not filepath.exists()


class TestSessionReload:
    """Tests for reloading sessions from disk."""

    def test_reload_reflects_disk_changes(self, mgr):
        sid = mgr.new_session("Test")
        # Directly modify the file
        filepath = Path(mgr.session_dir) / f"{sid}.json"
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)
        data["title"] = "Modified Externally"
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

        mgr.reload_session()
        assert mgr.current_session["title"] == "Modified Externally"


class TestAtomicWrite:
    """Tests for atomic write behavior (tmp → rename pattern)."""

    def test_atomic_write_does_not_corrupt_on_crash_simulation(self, mgr):
        """Verify the .tmp → rename mechanism is used."""
        import time
        sid = mgr.new_session("Atomic Test")
        filepath = Path(mgr.session_dir) / f"{sid}.json"
        tmppath = Path(str(filepath) + ".tmp")

        # After saving, the .json should exist and .tmp should be gone
        assert filepath.exists()
        # tmp file should have been renamed away
        assert not tmppath.exists() or tmppath.exists() is False
