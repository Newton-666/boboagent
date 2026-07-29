'''run_tests.py 单元测试 — _detect_framework / _run_pytest / execute / register'''

from unittest.mock import patch, MagicMock
from pathlib import Path

import pytest

from tools.run_tests import _detect_framework, execute, _run_pytest


class TestDetectFramework:
    '''_detect_framework — 自动检测测试框架'''

    def test_detect_pytest_via_pyproject(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[tool.pytest]")
        assert _detect_framework(tmp_path) == "pytest"

    def test_detect_pytest_via_setup_cfg(self, tmp_path):
        (tmp_path / "setup.cfg").write_text("[tool:pytest]")
        assert _detect_framework(tmp_path) == "pytest"

    def test_detect_pytest_via_test_files(self, tmp_path):
        (tmp_path / "test_foo.py").write_text("")
        assert _detect_framework(tmp_path) == "pytest"

    def test_detect_pytest_via_alternative_naming(self, tmp_path):
        (tmp_path / "foo_test.py").write_text("")
        assert _detect_framework(tmp_path) == "pytest"

    def test_detect_pytest_via_tests_dir(self, tmp_path):
        (tmp_path / "tests").mkdir()
        assert _detect_framework(tmp_path) == "pytest"

    def test_detect_jest_via_package_json(self, tmp_path):
        (tmp_path / "package.json").write_text('{"scripts": {"test": "jest"}}')
        assert _detect_framework(tmp_path) == "jest"

    def test_detect_go_via_test_files(self, tmp_path):
        (tmp_path / "foo_test.go").write_text("package foo")
        assert _detect_framework(tmp_path) == "go"

    def test_no_framework_detected(self, tmp_path):
        (tmp_path / "README.md").write_text("no tests here")
        assert _detect_framework(tmp_path) is None

    def test_with_makefile(self, tmp_path):
        (tmp_path / "Makefile").write_text("test:\n\techo")
        assert _detect_framework(tmp_path) is None


class TestRunPytest:
    '''_run_pytest — mock subprocess 验证输出解析'''

    def test_all_passed(self):
        with patch("tools.run_tests.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="collected 10 items\n...\n10 passed in 0.10s",
                stderr=""
            )
            result = _run_pytest(Path("/fake"))
            assert "10 通过" in result

    def test_some_failed(self):
        with patch("tools.run_tests.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout="collected 5 items\n...FAILURES...\n3 failed, 2 passed",
                stderr=""
            )
            result = _run_pytest(Path("/fake"))
            assert "3 失败" in result
            assert "2 通过" in result

    def test_pytest_not_installed(self):
        with patch("tools.run_tests.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError()
            result = _run_pytest(Path("/fake"))
            assert "pytest 未安装" in result

    def test_timeout(self):
        with patch("tools.run_tests.subprocess.run") as mock_run:
            from subprocess import TimeoutExpired
            mock_run.side_effect = TimeoutExpired(cmd="pytest", timeout=120)
            result = _run_pytest(Path("/fake"))
            assert "超时" in result

    def test_no_output_returns_placeholder(self):
        with patch("tools.run_tests.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = _run_pytest(Path("/fake"))
            assert "(无输出)" in result


class TestExecute:
    '''execute() — 完整调度流程'''

    def test_with_explicit_framework(self):
        with patch("tools.run_tests._run_pytest") as mock_pytest:
            mock_pytest.return_value = "[pytest] done"
            result = execute(path="/tmp", framework="pytest")
            assert "done" in result

    def test_nonexistent_path(self):
        result = execute(path="/nonexistent/path/xyz")
        assert "错误" in result

    def test_path_is_file(self):
        with patch("pathlib.Path.is_dir", return_value=False):
            with patch("pathlib.Path.exists", return_value=True):
                result = execute(path="/tmp/some_file.txt")
                assert "不是目录" in result

    def test_unsupported_framework(self):
        result = execute(path="/tmp", framework="unknown")
        assert "不支持的测试框架" in result

    def test_no_framework_detected(self, tmp_path):
        with patch("tools.run_tests._detect_framework", return_value=None):
            result = execute(path=str(tmp_path))
            assert "未自动检测到测试框架" in result
            assert "Makefile" not in result

    def test_makefile_suggestion(self, tmp_path):
        (tmp_path / "Makefile").write_text("test:\n\techo hello")
        with patch("tools.run_tests._detect_framework", return_value=None):
            result = execute(path=str(tmp_path))
            assert "Makefile" in result

    def test_register_schema(self):
        registry = {}
        from tools import run_tests
        run_tests.register(lambda n, f, s: registry.update({n: (f, s)}))
        assert "run_tests" in registry
        schema = registry["run_tests"][1]
        props = schema["function"]["parameters"]["properties"]
        assert "path" in props
        assert "framework" in props
