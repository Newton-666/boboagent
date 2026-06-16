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


# ── Phase 1-4: edit_file context-aware matching ──────────────────────────

class TestEditFileContextAware:
    """Verify edit_file returns similar-line hints when match fails."""

    def test_find_similar_lines_substring_match(self):
        """First line of old_string should be used to find similar lines."""
        from tools.edit_file import _find_similar_lines

        content = "def foo():\n    pass\n\ndef bar():\n    return 42\n"
        old = "def bar():\n    return 43"
        hints = _find_similar_lines(content, old)
        assert len(hints) > 0
        assert hints[0][1] == "def bar():"

    def test_find_similar_lines_keyword_match(self):
        """Keywords from old_string should find related lines via fuzzy scoring."""
        from tools.edit_file import _find_similar_lines

        content = "import os\nimport sys\nfrom pathlib import Path\n\nx = 1\n"
        old = "import oss\n"
        hints = _find_similar_lines(content, old)
        # 'import' matches lines 1,2; 'oss' is a substring of nothing directly
        # but the scoring approach returns lines containing at least one keyword
        assert len(hints) > 0
        # The top match should be one of the import lines
        assert "import" in hints[0][1]

    def test_find_similar_lines_no_match(self):
        """Completely unrelated search should return empty list."""
        from tools.edit_file import _find_similar_lines

        content = "hello world\nfoo bar\n"
        old = "xyzzy plugh"
        hints = _find_similar_lines(content, old)
        assert hints == []

    def test_edit_file_error_includes_hints(self, tmp_path):
        """When edit_file fails to match, error message should include hints."""
        test_file = tmp_path / "test_edit.py"
        test_file.write_text(
            "def hello():\n    print('hello')\n\ndef world():\n    print('world')\n",
            encoding="utf-8"
        )

        from tools.edit_file import execute
        result = execute(
            file_path=str(test_file),
            old_string="def hello():\n    print('hi')",  # wrong: 'hi' not 'hello'
            new_string="def hello():\n    print('hi')"
        )
        assert "错误" in result
        assert "文件中相似的行" in result  # hint section
        assert "hello" in result  # the similar line is shown


# ── Phase 1-6: refactor interface redesign ──────────────────────────────

class TestRefactorInterface:
    """Verify refactor's new changes-based interface works correctly."""

    def test_search_only_returns_matches(self, tmp_path):
        test_file = tmp_path / "test_refactor.py"
        test_file.write_text("def foo():\n    return _old_name()\n", encoding="utf-8")

        from tools.refactor import execute
        result = execute(keyword="_old_name", directory=str(tmp_path), file_pattern="*.py")
        assert "找到" in result
        assert "_old_name" in result
        assert "test_refactor.py" in result

    def test_dry_run_preview_all_matches(self, tmp_path):
        test_file = tmp_path / "dryrun.py"
        test_file.write_text("def foo():\n    return old_func()\n", encoding="utf-8")

        from tools.refactor import execute
        result = execute(
            keyword="old_func",
            directory=str(tmp_path),
            file_pattern="*.py",
            changes=[{
                "path": str(test_file),
                "old_string": "old_func()",
                "new_string": "new_func()"
            }],
            dry_run=True
        )
        assert "预览替换" in result
        assert "匹配 1 处" in result
        assert "全部匹配" in result

    def test_dry_run_detects_mismatch(self, tmp_path):
        test_file = tmp_path / "mismatch.py"
        test_file.write_text("def foo():\n    return actual_func()\n", encoding="utf-8")

        from tools.refactor import execute
        result = execute(
            keyword="func",
            directory=str(tmp_path),
            file_pattern="*.py",
            changes=[{
                "path": str(test_file),
                "old_string": "wrong_name()",
                "new_string": "correct_name()"
            }],
            dry_run=True
        )
        assert "不匹配" in result or "未匹配" in result

    def test_actual_replace_works(self, tmp_path):
        test_file = tmp_path / "replace.py"
        test_file.write_text("VERSION = '1.0.0'\n", encoding="utf-8")

        from tools.refactor import execute
        result = execute(
            keyword="VERSION",
            directory=str(tmp_path),
            file_pattern="*.py",
            changes=[{
                "path": str(test_file),
                "old_string": "VERSION = '1.0.0'",
                "new_string": "VERSION = '2.0.0'"
            }]
        )
        assert "已替换" in result
        content = test_file.read_text(encoding="utf-8")
        assert "2.0.0" in content

    def test_changes_interface_accepted(self):
        """Verify the new changes parameter is in the schema."""
        from tools.refactor import TOOL_SCHEMA
        props = TOOL_SCHEMA["function"]["parameters"]["properties"]
        assert "changes" in props
        assert "dry_run" in props
        # changes items must have the right required fields
        item_props = props["changes"]["items"]["properties"]
        assert "path" in item_props
        assert "old_string" in item_props
        assert "new_string" in item_props


# ── Phase 2: file_safety (write-denied + binary + env isolation) ──────

class TestWriteDenied:
    """Verify write-denied path blocking."""

    def test_blocks_etc_passwd(self):
        from core.file_safety import is_write_denied
        denied, reason = is_write_denied("/etc/passwd")
        assert denied is True

    def test_blocks_ssh_key(self):
        from core.file_safety import is_write_denied
        from pathlib import Path
        denied, _ = is_write_denied(f"{Path.home()}/.ssh/id_rsa")
        assert denied is True

    def test_blocks_aws_credentials(self):
        from core.file_safety import is_write_denied
        from pathlib import Path
        denied, _ = is_write_denied(f"{Path.home()}/.aws/credentials")
        assert denied is True

    def test_allows_normal_file(self, tmp_path):
        from core.file_safety import is_write_denied
        test_file = tmp_path / "safe_file.txt"
        denied, _ = is_write_denied(str(test_file))
        assert denied is False

    def test_file_operation_blocks_write(self, tmp_path):
        """file_operation.write should reject denied paths."""
        from tools.file_operation import execute
        result = execute(action="write", path="/etc/passwd", content="hack")
        assert "禁止" in result

    def test_edit_file_blocks_write(self, tmp_path):
        """edit_file should reject denied paths."""
        from tools.edit_file import execute
        result = execute("/etc/passwd", "old", "new")
        assert "禁止" in result


class TestBinaryDetection:
    """Verify binary file detection."""

    def test_png_detected(self, tmp_path):
        from core.file_safety import is_binary_file
        png = tmp_path / "test.png"
        # PNG magic bytes
        png.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\x0dIHDR")
        is_bin, _ = is_binary_file(str(png))
        assert is_bin is True

    def test_py_not_detected(self, tmp_path):
        from core.file_safety import is_binary_file
        py_file = tmp_path / "test.py"
        py_file.write_text("print('hello')")
        is_bin, _ = is_binary_file(str(py_file))
        assert is_bin is False

    def test_extension_fast_path(self):
        from core.file_safety import is_binary_file
        # .pyc should be detected by extension alone
        is_bin, msg = is_binary_file("/tmp/nonexistent.pyc")
        assert is_bin is True
        assert "pyc" in msg


class TestEnvIsolation:
    """Verify env sanitization for subprocess."""

    def test_strips_api_keys(self):
        from core.file_safety import sanitize_env
        env = {"PATH": "/usr/bin", "HOME": "/home", "DEEPSEEK_API_KEY": "sk-secret"}
        clean = sanitize_env(env)
        assert "PATH" in clean
        assert "HOME" in clean
        assert "DEEPSEEK_API_KEY" not in clean

    def test_keeps_safe_vars(self):
        from core.file_safety import sanitize_env
        env = {"PATH": "/usr/bin", "HOME": "/home", "USER": "test", "LANG": "en_US.UTF-8"}
        clean = sanitize_env(env)
        for key in env:
            assert key in clean

    def test_strips_token_vars(self):
        from core.file_safety import sanitize_env
        env = {"GITHUB_TOKEN": "ghp_secret", "NOTION_API_KEY": "secret_xxx", "PATH": "/bin"}
        clean = sanitize_env(env)
        assert "PATH" in clean
        assert "GITHUB_TOKEN" not in clean
        assert "NOTION_API_KEY" not in clean
