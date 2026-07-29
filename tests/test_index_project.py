'''index_project.py 单元测试 — 提取器 / _extract_summary / _extract_imports / execute'''

from pathlib import Path
from unittest.mock import patch

import pytest

from tools.index_project import (
    _extract_python, _extract_javascript, _extract_go,
    _extract_rust, _extract_c, _extract_summary,
    _extract_imports,
)


# ── Python 提取器 ──

class TestExtractPython:
    def test_class(self):
        result = _extract_python("class MyClass:\n    pass")
        assert "class MyClass" in result

    def test_class_with_bases(self):
        result = _extract_python("class MyDict(dict):\n    pass")
        assert "class MyDict(dict)" in result

    def test_function(self):
        result = _extract_python("def hello(name):\n    return name")
        assert "def hello(name)" in result

    def test_async_function(self):
        result = _extract_python("async def fetch(url):\n    pass")
        assert "async def fetch(url)" in result

    def test_function_with_return_annotation(self):
        result = _extract_python("def add(a, b) -> int:\n    return a + b")
        assert "def add(a, b)" in result

    def test_empty_content(self):
        assert _extract_python("") == []

    def test_no_matches(self):
        assert _extract_python("x = 1\ny = 2") == []


# ── JavaScript 提取器 ──

class TestExtractJavascript:
    def test_class(self):
        result = _extract_javascript("class MyClass {\n}")
        assert "class MyClass" in result

    def test_exported_class(self):
        result = _extract_javascript("export class MyClass {\n}")
        assert "class MyClass" in result

    def test_function(self):
        result = _extract_javascript("function hello(x) {\n}")
        assert "function hello(x)" in result

    def test_async_function(self):
        result = _extract_javascript("async function fetch(url) {\n}")
        assert "async function fetch(url)" in result

    def test_arrow_const(self):
        result = _extract_javascript("const greet = (name) => {")
        assert "const greet = (...) =>" in result[0]

    def test_exported_arrow(self):
        result = _extract_javascript("export const PI = () => {")
        assert "const PI = (...)" in result[0]

    def test_empty(self):
        assert _extract_javascript("") == []


# ── Go 提取器 ──

class TestExtractGo:
    def test_function(self):
        result = _extract_go("func hello(name string) {")
        assert "func hello(name string)" in result

    def test_method_with_receiver(self):
        result = _extract_go("func (s *Service) Run(ctx context.Context) error {")
        assert "func (s *Service)Run" in result[0]

    def test_type_struct(self):
        result = _extract_go("type Config struct {")
        assert "type Config struct" in result

    def test_type_interface(self):
        result = _extract_go("type Runner interface {")
        assert "type Runner interface" in result

    def test_empty(self):
        assert _extract_go("") == []


# ── Rust 提取器 ──

class TestExtractRust:
    def test_fn(self):
        result = _extract_rust("fn hello(x: i32) -> i32 {")
        assert "fn hello(x: i32)" in result[0]

    def test_pub_fn(self):
        result = _extract_rust("pub fn run() {")
        assert "fn run()" in result[0]

    def test_struct(self):
        result = _extract_rust("struct Config {")
        assert "struct Config" in result

    def test_enum(self):
        result = _extract_rust("enum Color {")
        assert "enum Color" in result

    def test_trait(self):
        result = _extract_rust("trait Runner {")
        assert "trait Runner" in result

    def test_impl(self):
        result = _extract_rust("impl Runner for MyStruct {")
        assert "impl Runner" in result

    def test_empty(self):
        assert _extract_rust("") == []


# ── C/C++ 提取器 ──

class TestExtractC:
    def test_function(self):
        result = _extract_c("int main(int argc, char *argv[]) {")
        assert "main(int argc, char *argv[])" in result[0]

    def test_static_function(self):
        result = _extract_c("static void helper() {")
        assert "helper()" in result[0]

    def test_empty(self):
        assert _extract_c("") == []


# ── _extract_summary ──

class TestExtractSummary:
    def test_python_docstring(self):
        content = '"""This is a module for testing."""\nimport os'
        result = _extract_summary(content, "py")
        assert "This is a module for testing" in result

    def test_js_block_comment(self):
        content = '/** A utility module */\nconst x = 1'
        result = _extract_summary(content, "js")
        assert "A utility module" in result

    def test_c_block_comment(self):
        content = '/* core algorithm */\nint main() {}'
        result = _extract_summary(content, "c")
        assert "core algorithm" in result

    def test_shell_comments(self):
        content = '# setup script\n# run before tests\necho done'
        result = _extract_summary(content, "sh")
        assert "setup script" in result

    def test_no_comment_returns_empty(self):
        content = 'x = 1\ny = 2'
        result = _extract_summary(content, "py")
        assert result == ""


# ── _extract_imports ──

class TestExtractImports:
    def test_python_import(self):
        content = "import os\nfrom pathlib import Path"
        result = _extract_imports(content, ".py")
        assert "os" in result
        assert "pathlib" in result

    def test_js_import(self):
        content = "import { useState } from 'react';\nimport { foo } from './bar'"
        result = _extract_imports(content, ".js")
        assert "react" in result
        assert "./bar" in result

    def test_go_import(self):
        content = 'import "fmt"\nimport "os"'
        result = _extract_imports(content, ".go")
        assert "fmt" in result

    def test_c_include(self):
        content = '#include <stdio.h>\n#include "myheader.h"'
        result = _extract_imports(content, ".c")
        assert "stdio.h" in result

    def test_java_import(self):
        content = "import java.util.List;\nimport java.io.*;"
        result = _extract_imports(content, ".java")
        assert "java.util.List" in result

    def test_rust_use(self):
        content = "use std::collections::HashMap;\nextern crate serde"
        result = _extract_imports(content, ".rs")
        assert "std::collections::HashMap" in result

    def test_no_imports(self):
        assert _extract_imports("x = 1", ".py") == []

    def test_capped_at_twenty(self):
        content = "\n".join(f"import a{i}" for i in range(30))
        result = _extract_imports(content, ".py")
        assert len(result) <= 20
