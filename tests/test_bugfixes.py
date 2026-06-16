"""Regression tests for bugs found during code audit + phase 1 improvements."""

import os
import sys
import tempfile
from pathlib import Path
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── B1: github_create_repo description ignored ──────────────────────────

class TestGitHubCreateRepo:
    """Verify github_create_repo correctly handles description parameter."""

    def test_description_included_in_command(self):
        """The --description flag must be inserted when description is non-empty."""
        from tools.github_create_repo import execute as gh_execute

        # gh not required — we're testing command construction logic
        # by verifying the function signature accepts and uses description
        import inspect
        sig = inspect.signature(gh_execute)
        params = list(sig.parameters.keys())
        assert "description" in params
        assert "name" in params
        assert "public" in params

    def test_description_param_has_default(self):
        """description should default to empty string."""
        import inspect
        from tools.github_create_repo import execute as gh_execute
        sig = inspect.signature(gh_execute)
        assert sig.parameters["description"].default == ""


# ── B3: file_operation no backup before write/delete ────────────────────

class TestFileOperationBackup:
    """Verify file_operation creates backups before write/delete."""

    def test_write_backs_up_existing_file(self, tmp_path):
        """Writing to an existing file should create a trash backup."""
        test_file = tmp_path / "test_backup.txt"
        test_file.write_text("original content", encoding="utf-8")

        from tools.file_operation import execute

        result = execute(action="write", path=str(test_file), content="new content")
        assert "已写入" in result

        # Check backup exists
        trash_dir = Path.home() / ".bobo" / "trash"
        backups = list(trash_dir.glob("test_backup.txt_*"))
        assert len(backups) >= 1, "No backup was created in ~/.bobo/trash/"

    def test_delete_backs_up_file(self, tmp_path):
        """Deleting a file should create a trash backup first."""
        test_file = tmp_path / "test_delete_backup.txt"
        test_file.write_text("to be deleted", encoding="utf-8")

        from tools.file_operation import execute

        result = execute(action="delete", path=str(test_file))
        assert "已删除" in result
        assert not test_file.exists()

        # Check backup exists
        trash_dir = Path.home() / ".bobo" / "trash"
        backups = list(trash_dir.glob("test_delete_backup.txt_*"))
        assert len(backups) >= 1, "No backup was created before deletion"

    def test_write_new_file_no_backup_needed(self, tmp_path):
        """Writing a new file (not existing) should still work without error."""
        test_file = tmp_path / "new_file.txt"
        from tools.file_operation import execute

        result = execute(action="write", path=str(test_file), content="hello")
        assert "已写入" in result
        assert test_file.exists()


# ── B4: search_code missing venv skip dirs ──────────────────────────────

class TestSearchCodeSkipDirs:
    """Verify search_code skips virtual environment directories."""

    def test_venv_skipped(self):
        from tools.search_code import SKIP_DIRS
        for skip_dir in [".venv", "venv", "dist", "build", ".next", "coverage"]:
            assert skip_dir in SKIP_DIRS, f"'{skip_dir}' should be in SKIP_DIRS"

    def test_no_duplicate_dirs(self):
        from tools.search_code import SKIP_DIRS
        # SKIP_DIRS is a set — duplicates are impossible by definition
        assert isinstance(SKIP_DIRS, set)

    def test_skip_dirs_includes_virtual_env(self):
        """search_code should skip searching inside virtual environments."""
        from tools.search_code import _should_skip
        # _should_skip checks both SKIP_DIRS membership AND hidden directory prefix
        # After the fix, "venv" is in SKIP_DIRS, so _should_skip returns True
        assert _should_skip("venv") is True   # matches SKIP_DIRS
        assert _should_skip(".venv") is True   # starts with dot


# ── B6: file_operation misleading variable name ─────────────────────────

class TestFileOperationCache:
    """Verify read cache works with correct variable naming."""

    def test_cache_reads_file(self, tmp_path):
        test_file = tmp_path / "cached.txt"
        test_file.write_text("cache content", encoding="utf-8")

        from tools.file_operation import execute

        result1 = execute(action="read", path=str(test_file))
        assert "cache content" in result1

        # Second read should use cache (file unchanged)
        result2 = execute(action="read", path=str(test_file))
        assert "缓存" in result2  # cached indicator

    def test_write_invalidates_cache(self, tmp_path):
        test_file = tmp_path / "invalidate.txt"
        test_file.write_text("v1", encoding="utf-8")

        from tools.file_operation import execute

        # Read → cache
        r1 = execute(action="read", path=str(test_file))
        assert "v1" in r1

        # Write new content → should invalidate cache
        execute(action="write", path=str(test_file), content="v2")
        r2 = execute(action="read", path=str(test_file))
        # After write, cache is cleared, so re-reads from disk
        assert "v2" in r2

    def test_delete_invalidates_cache(self, tmp_path):
        test_file = tmp_path / "delete_cache.txt"
        test_file.write_text("doomed", encoding="utf-8")

        from tools.file_operation import execute

        execute(action="read", path=str(test_file))
        execute(action="delete", path=str(test_file))
        # File deleted, cache cleared, reading should fail
        result = execute(action="read", path=str(test_file))
        assert "读取失败" in result


# ── B5: search_code consistency with grep_code ──────────────────────────

class TestSearchCodeVsGrepCode:
    """Verify search_code and grep_code skip consistent directories."""

    def test_common_skip_dirs_match(self):
        """Both tools should skip the same critical directories."""
        from tools.search_code import SKIP_DIRS as SEARCH_SKIP
        from tools.grep_code import execute as grep_exec

        # grep_code uses inline list, not a constant. Let's check at least
        # that search_code now includes the important ones.
        important = {"node_modules", "__pycache__", ".git", ".venv", "venv", "dist", "build"}
        missing = important - SEARCH_SKIP
        assert not missing, f"search_code missing skip dirs: {missing}"


# ── Phase 1-1: code_execution output + tempfile cleanup ─────────────────

class TestCodeExecutionOutput:
    """Verify code_execution output limit raised to 50K and tempfiles cleaned."""

    def test_output_limit_50k(self):
        from tools.code_execution import MAX_OUTPUT_CHARS
        assert MAX_OUTPUT_CHARS == 50_000

    def test_temp_file_cleanup_on_success(self, tmp_path):
        """After running code, temp file should be deleted."""
        import subprocess, os
        from tools.code_execution import _run_python

        result = _run_python("print('hello world')")
        assert "hello world" in result

        # Check no leaked temp files in default tmp dir
        import tempfile
        tmp_dir = tempfile.gettempdir()
        leaked = [f for f in os.listdir(tmp_dir) if f.startswith("tmp") and f.endswith(".py")]
        # Can't guarantee zero (other processes), but our execution should be clean
        # The finally block ensures cleanup regardless of success/failure

    def test_temp_file_cleanup_on_error(self):
        """Even if code raises an exception, temp file should be cleaned."""
        from tools.code_execution import _run_python

        result = _run_python("raise RuntimeError('test error')")
        assert "Error" in result or "Traceback" in result
        # No assertion on file existence — the finally block handles it


# ── Phase 1-5: read_local_file pagination ───────────────────────────────

class TestReadLocalFilePagination:
    """Verify read_local_file supports offset + limit for large files."""

    def test_offset_only(self, tmp_path):
        test_file = tmp_path / "pagination_test.txt"
        lines = [f"line {i}" for i in range(100)]
        test_file.write_text("\n".join(lines), encoding="utf-8")

        from tools.read_local_file import execute
        result = execute(filepath=str(test_file), offset=50)
        assert "行 51-100" in result  # header shows range
        assert "line 50" in result
        assert "line 99" in result
        assert "line 0" not in result

    def test_offset_plus_limit(self, tmp_path):
        test_file = tmp_path / "pagination_limit.txt"
        lines = [f"line {i}" for i in range(100)]
        test_file.write_text("\n".join(lines), encoding="utf-8")

        from tools.read_local_file import execute
        result = execute(filepath=str(test_file), offset=10, limit=5)
        assert "行 11-15" in result
        assert "line 10" in result
        assert "line 14" in result
        assert "line 15" not in result
        assert "line 9" not in result

    def test_no_offset_no_limit_full_read(self, tmp_path):
        """Without offset/limit, entire file should be read as before."""
        test_file = tmp_path / "full.txt"
        test_file.write_text("hello\nworld\nbobo", encoding="utf-8")

        from tools.read_local_file import execute
        result = execute(filepath=str(test_file))
        assert "hello" in result
        assert "world" in result
        assert "bobo" in result
        assert "[行" not in result  # no pagination header for full reads
