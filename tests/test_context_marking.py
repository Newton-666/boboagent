"""Context Engineering — Result Marking 回归测试。

验证：
- 标记工具（read_local_file 等）的结果被替换为 [RESULT] 标记
- 非标记工具（execute_terminal 等）的结果原样保留
- 错误结果（以 错误/❌ 开头）不标记
- 标记内容正确保存到 workspace，load_result 能取回
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestMarkingLogic:
    @pytest.fixture
    def engine(self, tmp_path, monkeypatch):
        from core.engine import Engine
        from tests.mock_llm import MockLLMCaller, text_response
        import core.tool_runner as tr
        monkeypatch.setattr(tr.ToolRunnerMixin, "WORKSPACE_DIR", str(tmp_path / "workspace"))
        caller = MockLLMCaller([text_response("ok")])
        return Engine(caller, None, test_mode=True)

    def test_qualifying_tool_gets_marked(self, engine):
        # 需要超 2000 字符才触发标记（默认阈值 BOBO_CONTEXT_MARKING_MIN_CHARS=2000）
        big_result = "x" * 2500
        result = engine._maybe_mark_result(
            "read_local_file", {"file_path": "/tmp/x.txt"},
            big_result, 3,
        )
        assert result.startswith("[RESULT]")
        assert "id:" in result
        assert "3_" in result  # round number in ID

    def test_below_threshold_not_marked(self, engine):
        result = engine._maybe_mark_result(
            "read_local_file", {"file_path": "/tmp/x.txt"},
            "short result", 3,
        )
        assert not result.startswith("[RESULT]")
        assert result == "short result"

    def test_non_qualifying_tool_passes_through(self, engine):
        result = engine._maybe_mark_result(
            "execute_terminal", {"command": "ls"},
            "file1 file2", 3,
        )
        assert not result.startswith("[RESULT]")
        assert result == "file1 file2"

    def test_error_result_not_marked(self, engine):
        result = engine._maybe_mark_result(
            "web_search", {"query": "x"},
            "错误: timeout", 3,
        )
        assert not result.startswith("[RESULT]")
        assert "错误" in result

    def test_emoji_error_not_marked(self, engine):
        result = engine._maybe_mark_result(
            "read_local_file", {"file_path": "/x.txt"},
            "❌ 读取失败", 3,
        )
        assert not result.startswith("[RESULT]")

    def test_blocked_command_not_marked(self, engine):
        result = engine._maybe_mark_result(
            "grep_code", {"pattern": "x"},
            "⛔ 安全策略拦截: bad command", 3,
        )
        assert not result.startswith("[RESULT]")


class TestLoadResult:
    @pytest.fixture
    def workspace(self, tmp_path, monkeypatch):
        import tools.load_result as lr
        ws = tmp_path / "workspace"
        monkeypatch.setattr(lr, "WORKSPACE_DIR", str(ws))
        return ws

    def test_load_existing_result(self, workspace):
        workspace.mkdir()
        path = workspace / "5_abc12345.json"
        path.write_text(
            json.dumps({"tool": "web_search", "args": '{"query":"x"}', "content": "search result text"}),
            encoding="utf-8",
        )
        from tools.load_result import execute
        result = execute("5_abc12345")
        assert "[FULL RESULT]" in result
        assert "search result text" in result

    def test_load_missing_result(self, workspace):
        from tools.load_result import execute
        result = execute("nonexistent_id")
        assert "[NOT FOUND]" in result
        assert "重新调用原工具" in result

    def test_max_chars_truncation(self, workspace):
        workspace.mkdir()
        (workspace / "1_testid.json").write_text(
            json.dumps({"tool": "read_local_file", "args": '{"file_path":"/x"}',
                        "content": "a" * 2000}),
            encoding="utf-8",
        )
        from tools.load_result import execute
        result = execute("1_testid", max_chars=500)
        assert "...(截断" in result
        assert len(result) < 1200  # 500 chars content + header

    def test_invalid_json(self, workspace):
        workspace.mkdir()
        (workspace / "1_bad.json").write_text("not json", encoding="utf-8")
        from tools.load_result import execute
        result = execute("1_bad")
        assert "[ERROR]" in result
