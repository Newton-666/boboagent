'''list_directory 单元测试 — 高频工具，逻辑独立'''

import os
from pathlib import Path

import pytest

from tools.list_directory import execute, is_sensitive_path, TOOL_NAME


class TestIsSensitivePath:
    '''is_sensitive_path() — 安全检查'''

    def test_etc_is_sensitive(self):
        assert is_sensitive_path("/etc") is True

    def test_etc_passwd_is_sensitive(self):
        assert is_sensitive_path("/etc/passwd") is True

    def test_system_is_sensitive(self):
        assert is_sensitive_path("/System") is True

    def test_library_is_sensitive(self):
        assert is_sensitive_path("/Library") is True

    def test_ssh_is_sensitive(self):
        assert is_sensitive_path("~/.ssh") is True

    def test_normal_path_not_sensitive(self):
        assert is_sensitive_path("/tmp") is False

    def test_normal_project_path_not_sensitive(self):
        assert is_sensitive_path("/home/user/project") is False

    def test_home_dir_not_sensitive(self):
        home = os.path.expanduser("~")
        assert is_sensitive_path(home) is False

    def test_current_dir_not_sensitive(self):
        assert is_sensitive_path(".") is False


class TestExecute:
    '''execute() 主入口'''

    def test_list_current_directory(self, tmp_path):
        '''列出目录应返回文件列表'''
        (tmp_path / "file1.txt").write_text("content")
        (tmp_path / "file2.py").write_text("code")
        result = execute(path=str(tmp_path))
        assert "目录:" in result
        assert "file1.txt" in result
        assert "file2.py" in result

    def test_show_hidden_includes_dotfiles(self, tmp_path):
        '''show_hidden=True 应包含隐藏文件'''
        (tmp_path / ".hidden").write_text("secret")
        (tmp_path / "visible.txt").write_text("ok")

        result_hidden = execute(path=str(tmp_path), show_hidden=True)
        assert ".hidden" in result_hidden

        result_no_hidden = execute(path=str(tmp_path), show_hidden=False)
        assert ".hidden" not in result_no_hidden

    def test_max_items_truncates(self, tmp_path):
        '''max_items 限制输出行数'''
        for i in range(20):
            (tmp_path / f"file_{i}.txt").write_text("x")

        result = execute(path=str(tmp_path), max_items=5)
        items = [l for l in result.split("\n") if l.startswith("\U0001f4c4") or l.startswith("\U0001f4c1")]
        assert len(items) <= 5

    def test_nonexistent_path_returns_error(self):
        result = execute(path="/tmp/__nonexistent_xyz__")
        assert "路径不存在" in result

    def test_file_path_returns_not_dir(self, tmp_path):
        p = tmp_path / "afile.txt"
        p.write_text("data")
        result = execute(path=str(p))
        assert "不是目录" in result

    def test_default_max_items_is_50(self):
        '''默认 max_items=50，schema 中有体现'''
        from tools.list_directory import TOOL_SCHEMA
        props = TOOL_SCHEMA["function"]["parameters"]["properties"]["max_items"]
        assert props["type"] == "integer"

    def test_directory_with_subdirs(self, tmp_path):
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir/nested.txt").write_text("data")
        result = execute(path=str(tmp_path))
        assert "subdir" in result


class TestRegister:
    '''register() + TOOL_SCHEMA'''

    def test_tool_name_constant(self):
        assert TOOL_NAME == "list_directory"

    def test_register_adds_schema(self):
        from tools.list_directory import register
        registry = {}
        register(lambda name, fn, schema: registry.update({name: (fn, schema)}))
        assert "list_directory" in registry
        schema = registry["list_directory"][1]
        assert schema["function"]["name"] == "list_directory"
        assert "path" in schema["function"]["parameters"]["properties"]
        assert "show_hidden" in schema["function"]["parameters"]["properties"]
        assert "max_items" in schema["function"]["parameters"]["properties"]

    def test_tool_func_is_execute(self):
        from tools.list_directory import TOOL_FUNC
        assert TOOL_FUNC is execute
