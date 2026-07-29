'''GitHub 工具单元测试 — mock subprocess.run'''

from unittest.mock import patch, MagicMock

import pytest

from tools import (
    github_check_auth,
    github_setup,
    github_create_repo,
    github_create_pr,
    github_pr_diff,
    github_pr_comment,
)


class TestGithubCheckAuth:
    '''github_check_auth.execute()'''

    def test_installed_and_logged_in(self):
        with patch("tools.github_check_auth.subprocess.run") as mock_run:
            def side_effect(cmd, **kw):
                m = MagicMock()
                if cmd[0] == "gh" and cmd[1] == "--version":
                    m.returncode = 0
                elif cmd[0] == "gh" and cmd[1] == "auth":
                    m.returncode = 0
                    m.stdout = "Logged in to github.com as user"
                return m
            mock_run.side_effect = side_effect
            result = github_check_auth.execute()
            assert "已安装并登录" in result

    def test_installed_not_logged_in(self):
        with patch("tools.github_check_auth.subprocess.run") as mock_run:
            def side_effect(cmd, **kw):
                m = MagicMock()
                if cmd[0] == "gh" and cmd[1] == "--version":
                    m.returncode = 0
                elif cmd[0] == "gh" and cmd[1] == "auth":
                    m.returncode = 1
                    m.stderr = "not logged in"
                return m
            mock_run.side_effect = side_effect
            result = github_check_auth.execute()
            assert "已安装但未登录" in result

    def test_gh_not_installed(self):
        with patch("tools.github_check_auth.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError()
            result = github_check_auth.execute()
            assert "未安装" in result

    def test_exception_handled(self):
        with patch("tools.github_check_auth.subprocess.run") as mock_run:
            mock_run.side_effect = Exception("connection error")
            result = github_check_auth.execute()
            assert "检查失败" in result
            assert "connection error" in result

    def test_register_schema(self):
        registry = {}
        github_check_auth.register(lambda n, f, s: registry.update({n: (f, s)}))
        assert "github_check_auth" in registry


class TestGithubSetup:
    '''github_setup.execute()'''

    def test_invalid_token_too_short(self):
        result = github_setup.execute("short")
        assert "请输入有效的" in result

    def test_saves_token_and_logs_in(self):
        with patch("tools.github_setup.subprocess.run") as mock_run:
            with patch("tools.github_setup.os.makedirs"):
                with patch("tools.github_setup.open") as mock_open:
                    mock_run.return_value = MagicMock(returncode=0, stderr="")
                    mock_file = MagicMock()
                    mock_open.return_value.__enter__.return_value = mock_file
                    result = github_setup.execute("ghp_" + "a" * 20)
                    assert "已配置成功" in result

    def test_gh_not_installed_still_saves_token(self):
        with patch("tools.github_setup.subprocess.run") as mock_run:
            with patch("tools.github_setup.os.makedirs"):
                with patch("tools.github_setup.open") as mock_open:
                    mock_run.side_effect = FileNotFoundError()
                    mock_file = MagicMock()
                    mock_open.return_value.__enter__.return_value = mock_file
                    result = github_setup.execute("ghp_" + "b" * 20)
                    assert "Token 已保存" in result
                    assert "GitHub CLI 未安装" in result

    def test_register_schema(self):
        registry = {}
        github_setup.register(lambda n, f, s: registry.update({n: (f, s)}))
        assert "github_setup" in registry
        schema = registry["github_setup"][1]
        assert "token" in schema["function"]["parameters"]["properties"]


class TestGithubCreateRepo:
    '''github_create_repo.execute()'''

    def test_creates_public_repo(self):
        with patch("tools.github_create_repo.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="https://github.com/user/repo")
            result = github_create_repo.execute("my-repo")
            assert "已创建" in result

    def test_creates_private_repo(self):
        with patch("tools.github_create_repo.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="https://github.com/user/repo")
            result = github_create_repo.execute("my-repo", public=False)
            assert "已创建" in result
            args = mock_run.call_args[0][0]
            assert "--private" in args
            assert "--public" not in args

    def test_with_description(self):
        with patch("tools.github_create_repo.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="done")
            result = github_create_repo.execute("my-repo", description="A test repo")
            assert "已创建" in result
            args = mock_run.call_args[0][0]
            assert "--description" in args
            assert "A test repo" in args

    def test_gh_not_installed(self):
        with patch("tools.github_create_repo.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError()
            result = github_create_repo.execute("my-repo")
            assert "需要安装" in result

    def test_timeout_handled(self):
        with patch("tools.github_create_repo.subprocess.run") as mock_run:
            from subprocess import TimeoutExpired
            mock_run.side_effect = TimeoutExpired(cmd="gh", timeout=30)
            result = github_create_repo.execute("my-repo")
            assert "超时" in result

    def test_register_schema(self):
        registry = {}
        github_create_repo.register(lambda n, f, s: registry.update({n: (f, s)}))
        assert "github_create_repo" in registry


class TestGithubCreatePr:
    '''github_create_pr.execute()'''

    def test_create_pr_with_title(self):
        with patch("tools.github_create_pr.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="https://github.com/user/repo/pull/1")
            result = github_create_pr.execute("Fix bug #42")
            assert "PR 已创建" in result

    def test_create_pr_with_body(self):
        with patch("tools.github_create_pr.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="https://github.com/user/repo/pull/2")
            result = github_create_pr.execute("Add feature", body="Closes #10")
            assert "PR 已创建" in result
            args = mock_run.call_args[0][0]
            assert "--body" in args
            assert "Closes #10" in args

    def test_custom_base(self):
        with patch("tools.github_create_pr.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="done")
            result = github_create_pr.execute("Title", body="Desc", base="develop")
            args = mock_run.call_args[0][0]
            assert "--base" in args
            assert "develop" in args

    def test_failure_returns_stderr(self):
        with patch("tools.github_create_pr.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="no commits")
            result = github_create_pr.execute("Title")
            assert "创建失败" in result
            assert "no commits" in result

    def test_register_schema(self):
        registry = {}
        github_create_pr.register(lambda n, f, s: registry.update({n: (f, s)}))
        assert "github_create_pr" in registry
        schema = registry["github_create_pr"][1]
        assert "title" in schema["function"]["parameters"]["required"]


class TestGithubPrDiff:
    '''github_pr_diff.execute()'''

    def test_diff_with_pr_number(self):
        with patch("tools.github_pr_diff.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="@@ -1,3 +1,4 @@")
            result = github_pr_diff.execute(pr_number=5)
            assert "@@ -1,3 +1,4 @@" in result

    def test_diff_with_repo(self):
        with patch("tools.github_pr_diff.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="diff content")
            result = github_pr_diff.execute(pr_number=3, repo="owner/repo")
            args = mock_run.call_args[0][0]
            assert "-R" in args
            assert "owner/repo" in args

    def test_empty_diff(self):
        with patch("tools.github_pr_diff.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="")
            result = github_pr_diff.execute()
            assert "没有差异" in result

    def test_long_diff_truncated(self):
        with patch("tools.github_pr_diff.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="x" * 10000)
            result = github_pr_diff.execute(pr_number=1)
            assert "截断" in result
            assert len(result) < 8020

    def test_failure(self):
        with patch("tools.github_pr_diff.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="not found")
            result = github_pr_diff.execute(pr_number=999)
            assert "获取失败" in result
            assert "not found" in result

    def test_register_schema(self):
        registry = {}
        github_pr_diff.register(lambda n, f, s: registry.update({n: (f, s)}))
        assert "github_pr_diff" in registry


class TestGithubPrComment:
    '''github_pr_comment.execute()'''

    def test_general_comment(self):
        with patch("tools.github_pr_comment.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="Comment posted")
            result = github_pr_comment.execute(pr_number=1, body="LGTM!")
            assert "评论已发布" in result
            args = mock_run.call_args[0][0]
            assert "pr" in args
            assert "comment" in args
            assert "LGTM!" in args

    def test_inline_review_with_path_and_line(self):
        with patch("tools.github_pr_comment.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="Review submitted")
            result = github_pr_comment.execute(pr_number=1, body="Fix this", path="main.py", line=42)
            assert "评论已发布" in result
            args = mock_run.call_args[0][0]
            assert "review" in args
            assert "--comment" in args

    def test_failure(self):
        with patch("tools.github_pr_comment.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="PR not found")
            result = github_pr_comment.execute(pr_number=999, body="test")
            assert "评论失败" in result
            assert "PR not found" in result

    def test_timeout(self):
        with patch("tools.github_pr_comment.subprocess.run") as mock_run:
            from subprocess import TimeoutExpired
            mock_run.side_effect = TimeoutExpired(cmd="gh", timeout=30)
            result = github_pr_comment.execute(pr_number=1, body="hello")
            assert "超时" in result

    def test_register_schema(self):
        registry = {}
        github_pr_comment.register(lambda n, f, s: registry.update({n: (f, s)}))
        assert "github_pr_comment" in registry
        schema = registry["github_pr_comment"][1]
        required = schema["function"]["parameters"]["required"]
        assert "pr_number" in required
        assert "body" in required
