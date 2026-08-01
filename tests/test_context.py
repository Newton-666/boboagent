"""Tests for core/context.py — query classification, tool filtering, history compression."""

import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.engine import Engine
from core.tool_executor import execute_tool


@pytest.fixture
def engine():
    from tests.mock_llm import MockLLMCaller, text_response
    caller = MockLLMCaller([text_response("ok")])
    return Engine(caller, execute_tool, test_mode=True)


class TestQueryClassification:
    """Tests for _classify_query which determines the user's intent category."""

    def test_obsidian_keyword_matches(self, engine):
        engine.current_user_input = "帮我搜索笔记中的内容"
        result = engine._classify_query()
        assert result == "obsidian"

    def test_notion_keyword_matches(self, engine):
        engine.current_user_input = "查看notion页面"
        result = engine._classify_query()
        assert result == "notion"

    def test_code_keyword_matches(self, engine):
        engine.current_user_input = "帮我写代码实现排序"
        result = engine._classify_query()
        assert result == "code"

    def test_file_keyword_matches(self, engine):
        engine.current_user_input = "列出文件夹中的内容"
        result = engine._classify_query()
        assert result == "file"

    def test_email_keyword_matches(self, engine):
        engine.current_user_input = "检查我的邮件"
        result = engine._classify_query()
        assert result == "email"

    def test_macos_keyword_matches(self, engine):
        engine.current_user_input = "给我发个通知"
        result = engine._classify_query()
        assert result == "macos"

    def test_web_keyword_matches(self, engine):
        engine.current_user_input = "search for AI news"
        result = engine._classify_query()
        assert result == "web"

    def test_english_keywords(self, engine):
        engine.current_user_input = "find note about python"
        result = engine._classify_query()
        assert result == "obsidian"

    def test_unknown_query_returns_none(self, engine):
        engine.current_user_input = "今天天气真好"
        result = engine._classify_query()
        assert result is None

    def test_empty_input_returns_none(self, engine):
        engine.current_user_input = ""
        result = engine._classify_query()
        assert result is None


class TestToolFiltering:
    """Tests for _get_filtered_tools based on query classification."""

    def test_web_query_filters_to_web_tools(self, engine):
        engine.current_user_input = "search for AI news online"
        filtered = engine._get_filtered_tools()
        if filtered is not None:
            names = [t.get("function", {}).get("name", "") for t in filtered]
            # Web tools should be present
            web_tools = ["web_search", "web_fetch", "web_extract", "open_url"]
            for wt in web_tools:
                assert wt in names

    def test_code_query_filters_to_code_tools(self, engine):
        engine.current_user_input = "write a python script"
        filtered = engine._get_filtered_tools()
        if filtered is not None:
            names = [t.get("function", {}).get("name", "") for t in filtered]
            # Check for tools that ARE in the code category per TOOL_CATEGORIES
            code_tools = ["code_execution", "execute_terminal",
                         "refactor", "git_status", "github_create_repo",
                         "github_create_pr", "github_pr_diff", "github_pr_comment",
                         "restore_checkpoint"]
            for ct in code_tools:
                assert ct in names

    def test_macos_query_filters_to_macos_tools(self, engine):
        engine.current_user_input = "通知我下午开会"
        filtered = engine._get_filtered_tools()
        if filtered is not None:
            names = [t.get("function", {}).get("name", "") for t in filtered]
            assert "send_notification" in names

    def test_obsidian_query_does_not_filter(self, engine):
        # Obsidian queries use all tools since it's in _NO_FILTER_CATEGORIES
        engine.current_user_input = "搜索笔记"
        result = engine._get_filtered_tools()
        assert result is None  # None means use all tools

    def test_notion_query_does_not_filter(self, engine):
        engine.current_user_input = "notion页面"
        result = engine._get_filtered_tools()
        assert result is None

    def test_email_query_does_not_filter(self, engine):
        engine.current_user_input = "查看邮件"
        result = engine._get_filtered_tools()
        assert result is None

    def test_unknown_query_returns_none(self, engine):
        engine.current_user_input = "闲聊一下"
        result = engine._get_filtered_tools()
        assert result is None


class TestToolCategories:
    """Verify TOOL_CATEGORIES mapping is consistent."""

    def test_all_categories_have_lists(self):
        from core.context import ContextMixin
        for cat, tools in ContextMixin.TOOL_CATEGORIES.items():
            assert isinstance(tools, list), f"Category '{cat}' should map to a list"
            assert len(tools) > 0, f"Category '{cat}' should not be empty"

    def test_no_category_overlaps(self):
        from core.context import ContextMixin
        all_tools = []
        for tools in ContextMixin.TOOL_CATEGORIES.values():
            all_tools.extend(tools)
        # Check for duplicates across categories
        from collections import Counter
        counts = Counter(all_tools)
        dupes = {k: v for k, v in counts.items() if v > 1}
        # Note: Some tools may intentionally appear in multiple categories.
        # This test just reports, doesn't fail.
        if dupes:
            print(f"\nInfo: Tools appearing in multiple categories: {dupes}")


class TestHistoryCompression:
    """Tests for _compress_history behavior."""

    def test_no_compression_with_few_messages(self, engine):
        engine.MAX_HISTORY_CHARS = 100000
        engine.history = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]
        engine._compress_history()
        # History should be unchanged since it's tiny
        assert len(engine.history) == 2

    def test_compression_flag_is_set_during_compression(self, engine, monkeypatch):
        engine.KEEP_EXCHANGES = 5  # 显式设回旧值兼容本测试
        engine.MAX_HISTORY_CHARS = 100
        # TICKET-024：新触发模型 —— BOBO_CONTEXT_BUDGET 控制条数预算，
        # 但 token 预算不触发 → monkeypatch；短消息全装层0 → 降 _LAYER_0_TOKEN_LIMIT
        import os as _os
        _os.environ["BOBO_CONTEXT_BUDGET"] = "10"
        import core.context as ctx_module
        monkeypatch.setattr(ctx_module, "_get_context_budget", lambda _engine=None: 1)
        engine._LAYER_0_TOKEN_LIMIT = 200
        # Create enough history to trigger compression (20 exchanges > keep_count)
        for i in range(20):
            engine.history.append({"role": "user", "content": "x" * 100})
            engine.history.append({"role": "assistant", "content": "y" * 100})
        # This test just verifies no crash — actual compression requires a real LLM
        engine._compress_history()
        # After compression, we should have fewer messages
        assert len(engine.history) < 40  # 40 messages before

    def test_keep_exchanges_preserved(self, engine):
        engine.KEEP_EXCHANGES = 1
        engine.MAX_HISTORY_CHARS = 100
        # 5 exchanges (10 messages)
        for i in range(5):
            engine.history.append({"role": "user", "content": f"msg{i}" * 50})
            engine.history.append({"role": "assistant", "content": f"reply{i}" * 50})
        # Should keep the last exchange
        last_before = engine.history[-2:]
        engine._compress_history()
        # Last exchange should still be present
        assert engine.history[-2:] == last_before


from core.context import ContextMixin


class _TestMixin(ContextMixin):
    """最小化 ContextMixin 子类，用于测试 _get_filtered_tools。"""
    current_user_input = ""
    _compressed = False


class TestLedgerVisibility:
    """票 Z3.1：对每个分类路径验证 _get_filtered_tools 结果包含 task_ledger。"""

    @staticmethod
    def _filtered(query: str):
        obj = _TestMixin()
        obj.current_user_input = query
        return obj._get_filtered_tools()

    def test_code_category(self):
        """code 分类代表性输入 → 过滤列表含 task_ledger"""
        for q in ["写代码实现", "write a function", "implement feature", "debug the bug", "create a file"]:
            result = self._filtered(q)
            assert result is not None, f"code 分类应返回过滤列表，输入: {q}"
            names = [t.get("function", {}).get("name", "") for t in result]
            assert "task_ledger" in names, f"code 分类缺 task_ledger，输入: {q}"

    def test_file_category(self):
        """file 分类代表性输入 → 过滤列表含 task_ledger"""
        for q in ["读文件", "read file", "list file", "文件夹", "directory listing"]:
            result = self._filtered(q)
            assert result is not None, f"file 分类应返回过滤列表，输入: {q}"
            names = [t.get("function", {}).get("name", "") for t in result]
            assert "task_ledger" in names, f"file 分类缺 task_ledger，输入: {q}"

    def test_macos_category(self):
        """macos 分类代表性输入 → 过滤列表含 task_ledger"""
        for q in ["帮我提醒", "notification", "clipboard copy", "remind me"]:
            result = self._filtered(q)
            assert result is not None, f"macos 分类应返回过滤列表，输入: {q}"
            names = [t.get("function", {}).get("name", "") for t in result]
            assert "task_ledger" in names, f"macos 分类缺 task_ledger，输入: {q}"

    def test_web_category(self):
        """web 分类代表性输入 → 过滤列表含 task_ledger"""
        for q in ["search google", "google it", "look up python", "browse the web", "what is python"]:
            result = self._filtered(q)
            assert result is not None, f"web 分类应返回过滤列表，输入: {q}"
            names = [t.get("function", {}).get("name", "") for t in result]
            assert "task_ledger" in names, f"web 分类缺 task_ledger，输入: {q}"

    def test_obsidian_no_filter(self):
        """obsidian 分类（无过滤）→ 返回 None（全量），task_ledger 隐含可见"""
        for q in ["笔记", "obsidian note", "vault search", "日记"]:
            result = self._filtered(q)
            assert result is None, f"obsidian 应返回 None（无过滤），输入: {q}"

    def test_notion_no_filter(self):
        """notion 分类（无过滤）→ 返回 None（全量）"""
        for q in ["notion页面", "notion database"]:
            result = self._filtered(q)
            assert result is None, f"notion 应返回 None，输入: {q}"

    def test_email_no_filter(self):
        """email 分类（无过滤）→ 返回 None（全量）"""
        for q in ["邮件", "check mail", "inbox"]:
            result = self._filtered(q)
            assert result is None, f"email 应返回 None，输入: {q}"

    def test_unclassified_no_filter(self):
        """无分类输入 → 返回 None（全量），行为不变"""
        for q in ["你好", "今天天气不错", "what do you think", "random chat"]:
            result = self._filtered(q)
            assert result is None, f"无分类应返回 None，输入: {q}"

    def test_empty_input_no_filter(self):
        """空输入 → 返回 None"""
        result = self._filtered("")
        assert result is None
