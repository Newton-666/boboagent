"""Tests for server_utils — ok/err/write_atomic 工具函数。"""

import os
import tempfile
import pytest

# server_utils 依赖 bobo_tui_gateway.transport，导入前先 mock
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# 隔离导入 server_utils，mock transport 避免副作用
@pytest.fixture(autouse=True)
def mock_transport(monkeypatch):
    monkeypatch.setattr("bobo_tui_gateway.server_utils.write_json", lambda x: None)


from bobo_tui_gateway.server_utils import ok, err, write_atomic


class TestOk:
    def test_ok_basic(self):
        result = ok("req_1", {"value": 42})
        assert result["jsonrpc"] == "2.0"
        assert result["id"] == "req_1"
        assert result["result"] == {"value": 42}

    def test_ok_empty_result(self):
        result = ok("r2", {})
        assert result["jsonrpc"] == "2.0"
        assert result["id"] == "r2"
        assert result["result"] == {}


class TestErr:
    def test_err_basic(self):
        result = err("req_1", -32600, "Invalid Request")
        assert result["jsonrpc"] == "2.0"
        assert result["id"] == "req_1"
        assert result["error"]["code"] == -32600
        assert result["error"]["message"] == "Invalid Request"

    def test_err_custom_code(self):
        result = err("r3", -32000, "Server error")
        assert result["error"]["code"] == -32000
        assert result["error"]["message"] == "Server error"


class TestWriteAtomic:
    def test_write_atomic_creates_file(self):
        tmpdir = tempfile.mkdtemp()
        path = os.path.join(tmpdir, "test.txt")
        write_atomic(path, "hello atomic")
        assert os.path.isfile(path)
        with open(path, "r") as f:
            assert f.read() == "hello atomic"

    def test_write_atomic_overwrites(self):
        tmpdir = tempfile.mkdtemp()
        path = os.path.join(tmpdir, "test.txt")
        write_atomic(path, "version 1")
        write_atomic(path, "version 2")
        with open(path, "r") as f:
            assert f.read() == "version 2"

    def test_write_atomic_creates_parent_dirs(self):
        tmpdir = tempfile.mkdtemp()
        path = os.path.join(tmpdir, "sub", "deep", "file.txt")
        write_atomic(path, "nested")
        assert os.path.isfile(path)
        with open(path, "r") as f:
            assert f.read() == "nested"
