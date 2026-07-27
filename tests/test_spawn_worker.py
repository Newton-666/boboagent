"""Tests for spawn_worker result extraction logic."""

import pytest
from tools.spawn_worker import _extract_worker_result


def make_msg(role: str, content: str = "", tool_calls: list = None):
    """构建 history 消息。"""
    msg = {"role": role, "content": content}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    return msg


class TestExtractWorkerResult:
    """_extract_worker_result 的回归和行为测试。"""

    # ── 单轮（回归：行为不变）──

    def test_single_assistant_message(self):
        history = [
            make_msg("user", "什么是闭包？"),
            make_msg("assistant", "闭包是指函数内部定义的函数可以访问外部函数的局部变量。"),
        ]
        result = _extract_worker_result(history)
        assert "闭包" in result

    def test_single_assistant_with_tool_before(self):
        """工具轮 assistant 被跳过，只取最后纯文本。"""
        history = [
            make_msg("user", "查一下"),
            make_msg("assistant", "让我搜索一下", tool_calls=[{"id": "1", "function": {"name": "web_search"}}]),
            make_msg("tool", "搜索结果..."),
            make_msg("assistant", "搜索结果显示..."),
        ]
        result = _extract_worker_result(history)
        assert "搜索结果" in result
        assert "让我搜索" not in result  # 工具轮过渡语被跳过

    # ── 多轮拼接（核心修复）──

    def test_multi_round_concat(self):
        """多轮纯文本 assistant 消息应全部拼接。"""
        history = [
            make_msg("user", "分析方案"),
            make_msg("assistant", "方案第一部分：架构设计..."),
            make_msg("user", "继续"),
            make_msg("assistant", "方案第二部分：具体实现..."),
            make_msg("assistant", "以上即完整方案。"),
        ]
        result = _extract_worker_result(history)
        assert "架构设计" in result
        assert "具体实现" in result
        assert "完整方案" in result
        # 三段之间用 \\n\\n 分隔
        assert "\n\n" in result

    def test_multi_round_with_tool_between(self):
        """中间夹杂工具调用轮时应只拼接纯文本轮。"""
        history = [
            make_msg("user", "重构代码"),
            make_msg("assistant", "先看看代码结构"),
            make_msg("assistant", "让我搜索一下", tool_calls=[{"id": "1", "function": {"name": "grep_code"}}]),
            make_msg("tool", "grep 结果..."),
            make_msg("assistant", "让我再看看文件", tool_calls=[{"id": "2", "function": {"name": "read_local_file"}}]),
            make_msg("tool", "文件内容..."),
            make_msg("assistant", "重构方案如下：..."),
        ]
        result = _extract_worker_result(history)
        # 第一段纯文本（先看看）和最后一段（重构方案）应被拼接
        assert "先看看代码结构" in result
        assert "重构方案如下" in result
        # 工具轮过渡语不出现
        assert "让我搜索" not in result
        assert "让我再看看" not in result

    # ── 边界 ──

    def test_empty_history(self):
        assert _extract_worker_result([]) == "(Worker 没有产生回复)"

    def test_only_user_messages(self):
        history = [make_msg("user", "hello"), make_msg("user", "anyone?")]
        assert _extract_worker_result(history) == "(Worker 没有产生回复)"

    def test_all_tool_calls_no_final(self):
        """全部 assistant 消息都带 tool_calls，无纯文本收尾。"""
        history = [
            make_msg("user", "搜索"),
            make_msg("assistant", "查", tool_calls=[{"id": "1"}]),
            make_msg("tool", "..."),
            make_msg("assistant", "再查", tool_calls=[{"id": "2"}]),
            make_msg("tool", "..."),
        ]
        result = _extract_worker_result(history)
        assert result == "(Worker 没有产生回复)"

    def test_null_or_empty_content(self):
        """content 为 None 或空串的处理。"""
        history = [
            make_msg("user", "hi"),
            make_msg("assistant", None),
            make_msg("assistant", ""),
            make_msg("assistant", "   "),
            make_msg("assistant", "实际内容"),
        ]
        result = _extract_worker_result(history)
        assert result == "实际内容"  # None/空串/纯空白均跳过
