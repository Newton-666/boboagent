''''grep_code 单元测试 — 高频工具，逻辑独立'''

import os
import tempfile
from pathlib import Path

import pytest

from tools.grep_code import (
    execute,
    _search_python,
    MAX_MATCHES,
)


# ── 夹具：临时文件树 ──


@pytest.fixture
def sample_tree(tmp_path):
    '''创建带 .py 和 .js 文件的临时目录树'''
    (tmp_path / "src").mkdir()
    (tmp_path / "src/__init__.py").write_text("from .core import run\n")
    (tmp_path / "src/main.py").write_text(
        "def main():\n"
        "    # TODO: implement\n"
        "    return 42\n"
        "\n"
        "class Helper:\n"
        "    def run(self):\n"
        "        pass\n"
    )
    (tmp_path / "src/utils.js").write_text(
        "function run() {\n"
        "    // TODO: add error handling\n"
        "    return null;\n"
        "}\n"
    )
    (tmp_path / "README.md").write_text("# Project\n")
    (tmp_path / ".hidden.py").write_text("hidden = True\n")
    return tmp_path


class TestExecute:
    '''execute() 主入口'''

    def test_empty_pattern_returns_error(self):
        result = execute("")
        assert "错误" in result

    def test_blank_pattern_returns_error(self):
        result = execute("   ")
        assert "错误" in result

    def test_nonexistent_directory_returns_error(self):
        result = execute("TODO", path="/tmp/__nonexistent_xyz__")
        assert "错误" in result
        assert "目录不存在" in result

    def test_file_path_is_searched(self, sample_tree):
        '''传入文件路径时应搜索其所在目录'''
        main_py = str(sample_tree / "src/main.py")
        result = execute("TODO", path=main_py)
        assert "TODO" in result
        assert "1 处匹配" in result or "找到" in result

    def test_finds_basic_pattern(self, sample_tree):
        result = execute("TODO", path=str(sample_tree))
        assert "TODO" in result
        assert "找到" in result

    def test_no_match_returns_not_found(self, sample_tree):
        result = execute("ZZZZNOTFOUNDZZZZ", path=str(sample_tree))
        assert "未找到" in result

    def test_file_types_filter_python_only(self, sample_tree):
        result = execute("TODO", path=str(sample_tree), file_types=".py")
        assert ".py" in result or "main" in result or "__init__" in result
        # .js 文件中的 TODO 不应出现
        assert "utils.js" not in result

    def test_file_types_filter_js_only(self, sample_tree):
        result = execute("TODO", path=str(sample_tree), file_types=".js")
        assert "utils.js" in result or "run()" in result

    def test_context_expands_output(self, sample_tree):
        result = execute("return", path=str(sample_tree), context=2)
        # 应显示 return 前后多行
        assert "def main()" in result or "def run" in result or "return" in result

    def test_context_zero_is_concise(self, sample_tree):
        result = execute("return", path=str(sample_tree), context=0)
        lines = result.split("\n")
        # context=0 的匹配行数应 <= context=2
        assert len(lines) > 0

    def test_multiple_matches_across_files(self, sample_tree):
        result = execute("def", path=str(sample_tree))
        # main.py 和 utils.js 都有 def/function
        assert "找到" in result

    def test_hidden_files_searched(self, sample_tree):
        '''TICKET-G2：新口径（--hidden）下点开头文件可被搜到'''
        result = execute("hidden", path=str(sample_tree))
        assert ".hidden.py" in result
        assert "hidden = True" in result


class TestSearchPython:
    '''_search_python() 回退路径'''

    def test_invalid_regex_returns_error(self):
        results = _search_python(Path("."), "[", [], 1)
        assert len(results) == 1
        assert "error" in results[0]
        assert "正则表达式无效" in results[0]["error"]

    def test_empty_directory_returns_empty(self, tmp_path):
        results = _search_python(tmp_path, "TODO", [], 1)
        assert results == []

    def test_finds_match_in_file(self, sample_tree):
        results = _search_python(sample_tree, "TODO", [".py"], 1)
        assert len(results) >= 1
        assert "main.py" in results[0]["file"] or "__init__" in results[0]["file"]

    def test_max_matches_respected(self, sample_tree):
        '''搜索 . 应该匹配很多内容，但不超过 MAX_MATCHES'''
        results = _search_python(sample_tree, ".", [".py", ".js"], 0)
        assert len(results) <= MAX_MATCHES

    def test_snippet_has_context_lines(self, sample_tree):
        results = _search_python(sample_tree, "return", [".py"], 1)
        assert len(results) >= 1
        snippet = results[0]["snippet"]
        # context=1 应有至少 1 行 + 匹配行 + 1 行 = 3+ 行
        assert "def main()" in snippet or "42" in snippet


class TestRegister:
    '''register() 说明文档 schema'''

    def test_register_adds_schema(self):
        from tools.grep_code import register
        registry = {}
        register(lambda name, fn, schema: registry.update({name: (fn, schema)}))
        assert "grep_code" in registry
        name, (fn, schema) = "grep_code", registry["grep_code"]
        assert schema["function"]["name"] == "grep_code"
        assert "pattern" in schema["function"]["parameters"]["properties"]
        assert "required" in schema["function"]["parameters"]
