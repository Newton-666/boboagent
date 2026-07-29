'''py_compile_check 单元测试'''

import os
import tempfile
from pathlib import Path

import pytest

from core.code_checks import py_compile_check


class TestPyCompileCheck:

    def test_non_py_file_returns_empty(self):
        assert py_compile_check("readme.md") == ""
        assert py_compile_check("script.js") == ""
        assert py_compile_check("data.json") == ""

    def test_valid_py_file_returns_success(self):
        import textwrap
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write(textwrap.dedent("""\
                x = 1
                print(x)
            """))
            path = f.name
        try:
            result = py_compile_check(path)
            assert "✅" in result
            assert "py_compile 通过" in result
        finally:
            os.unlink(path)

    def test_syntax_error_py_file_returns_failure(self):
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write("def broken(\n")
            path = f.name
        try:
            result = py_compile_check(path)
            assert "❌" in result
            assert "py_compile 失败" in result
        finally:
            os.unlink(path)

    def test_nonexistent_file_returns_error(self):
        result = py_compile_check("/tmp/nonexistent_12345.py")
        # py_compile on missing file could return failure or exception
        assert "✅" not in result  # definitely not success

    def test_empty_py_file_passes(self):
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write("pass\n")
            path = f.name
        try:
            result = py_compile_check(path)
            assert "\u2705" in result
        finally:
            os.unlink(path)

    def test_class_definition_passes(self):
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write("class Foo:\n    pass\n")
            path = f.name
        try:
            result = py_compile_check(path)
            assert "\u2705" in result
        finally:
            os.unlink(path)

    def test_multiline_syntax_error(self):
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write("def foo():\n    return 1\n\ndef bar(\n")
            path = f.name
        try:
            result = py_compile_check(path)
            assert "\u274c" in result
            assert "SyntaxError" in result or "语法" in result
        finally:
            os.unlink(path)

    def test_import_error_is_not_syntax_error(self):
        '''import 错误是运行时错误，py_compile 应通过'''
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write("import nonexistent_module_xyz\n")
            path = f.name
        try:
            result = py_compile_check(path)
            assert "\u2705" in result  # compile-time check passes
        finally:
            os.unlink(path)
