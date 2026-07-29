'''get_current_time / git_status / open_url / restore_checkpoint 单元测试'''

from unittest.mock import patch, MagicMock
from datetime import datetime

import pytest

from tools import get_current_time
from tools import git_status
from tools import open_url
from tools import restore_checkpoint


class TestGetCurrentTime:
    '''get_current_time.execute()'''

    def test_full_format(self):
        result = get_current_time.execute("full")
        today = datetime.now().strftime("%Y-%m-%d")
        assert today in result

    def test_date_format(self):
        result = get_current_time.execute("date")
        today = datetime.now().strftime("%Y-%m-%d")
        assert result == today

    def test_time_format(self):
        result = get_current_time.execute("time")
        parts = result.split(":")
        assert len(parts) == 3

    def test_weekday_format(self):
        result = get_current_time.execute("weekday")
        today_weekday = datetime.now().strftime("%A")
        assert result == today_weekday

    def test_default_format_is_full(self):
        result = get_current_time.execute()
        today = datetime.now().strftime("%Y-%m-%d")
        assert today in result

    def test_register_schema(self):
        registry = {}
        get_current_time.register(lambda n, f, s: registry.update({n: (f, s)}))
        assert "get_current_time" in registry
        schema = registry["get_current_time"][1]
        props = schema["function"]["parameters"]["properties"]
        assert "format" in props
        assert props["format"]["enum"] == ["full", "date", "time", "weekday"]


class TestGitStatus:
    '''git_status.execute()'''

    def test_shows_branch_and_changes(self):
        with patch("tools.git_status.subprocess.run") as mock_run:
            def side_effect(cmd, **kw):
                m = MagicMock()
                if cmd == ["git", "branch", "--show-current"]:
                    m.returncode = 0; m.stdout = "feat/test-branch"; m.stderr = ""
                elif cmd == ["git", "status", "--short"]:
                    m.returncode = 0; m.stdout = " M main.py\n?? new.py"; m.stderr = ""
                elif cmd == ["git", "diff", "--stat"]:
                    m.returncode = 0; m.stdout = " main.py | 2 +-"; m.stderr = ""
                else:
                    m.returncode = 0; m.stdout = ""
                return m
            mock_run.side_effect = side_effect
            result = git_status.execute()
            assert "feat/test-branch" in result
            assert "2 个文件" in result
            assert "main.py | 2 +-" in result

    def test_clean_repo(self):
        with patch("tools.git_status.subprocess.run") as mock_run:
            def side_effect(cmd, **kw):
                m = MagicMock()
                m.returncode = 0; m.stdout = ""; m.stderr = ""
                if cmd == ["git", "branch", "--show-current"]:
                    m.stdout = "main"
                return m
            mock_run.side_effect = side_effect
            result = git_status.execute()
            assert result == "分支: main"

    def test_not_a_git_repo(self):
        with patch("tools.git_status.subprocess.run") as mock_run:
            def side_effect(cmd, **kw):
                m = MagicMock()
                m.returncode = 128; m.stdout = ""; m.stderr = "not a git repository"
                return m
            mock_run.side_effect = side_effect
            result = git_status.execute()
            assert "不是 git 仓库" in result

    def test_custom_path(self):
        with patch("tools.git_status.subprocess.run") as mock_run:
            m = MagicMock(); m.returncode = 0; m.stdout = "feat/x"; m.stderr = ""
            mock_run.return_value = m
            result = git_status.execute(path="/tmp")
            assert "feat/x" in result

    def test_register_schema(self):
        registry = {}
        git_status.register(lambda n, f, s: registry.update({n: (f, s)}))
        assert "git_status" in registry
        schema = registry["git_status"][1]
        assert "path" in schema["function"]["parameters"]["properties"]


class TestOpenUrl:
    '''open_url.execute()'''

    def test_success(self):
        with patch("tools.open_url.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = open_url.execute("https://example.com")
            assert "已在浏览器中打开" in result
            args = mock_run.call_args[0][0]
            assert args == ["open", "https://example.com"]

    def test_failure_returncode(self):
        with patch("tools.open_url.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)
            result = open_url.execute("https://example.com")
            assert "打开失败" in result

    def test_timeout(self):
        with patch("tools.open_url.subprocess.run") as mock_run:
            from subprocess import TimeoutExpired
            mock_run.side_effect = TimeoutExpired(cmd="open", timeout=15)
            result = open_url.execute("https://example.com")
            assert "超时" in result

    def test_file_not_found(self):
        with patch("tools.open_url.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError()
            result = open_url.execute("https://example.com")
            assert "open 命令不可用" in result

    def test_exception(self):
        with patch("tools.open_url.subprocess.run") as mock_run:
            mock_run.side_effect = Exception("something broke")
            result = open_url.execute("https://example.com")
            assert "无法打开" in result
            assert "something broke" in result

    def test_register_schema(self):
        registry = {}
        open_url.register(lambda n, f, s: registry.update({n: (f, s)}))
        assert "open_url" in registry
        schema = registry["open_url"][1]
        assert "url" in schema["function"]["parameters"]["required"]


class TestRestoreCheckpoint:
    '''restore_checkpoint — TOOL_FUNC is None (wired via engine)'''

    def test_tool_name_constant(self):
        assert restore_checkpoint.TOOL_NAME == "restore_checkpoint"

    def test_tool_func_is_none(self):
        assert restore_checkpoint.TOOL_FUNC is None

    def test_register_schema(self):
        registry = {}
        restore_checkpoint.register(lambda n, f, s: registry.update({n: (f, s)}))
        assert "restore_checkpoint" in registry
        schema = registry["restore_checkpoint"][1]
        assert schema["function"]["name"] == "restore_checkpoint"
