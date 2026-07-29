'''web_search / web_extract / web_fetch 单元测试 — mock crawler'''

from unittest.mock import patch

import pytest

from tools import web_search
from tools import web_extract
from tools import web_fetch


class TestWebSearch:
    '''web_search.execute() — 委托给 crawler.web_search'''

    def test_execute_calls_crawler(self):
        with patch("tools.crawler.web_search") as mock_ws:
            mock_ws.return_value = "mock search result"
            result = web_search.execute("python testing", max_results=3)
            mock_ws.assert_called_once_with("python testing", 3)
            assert result == "mock search result"

    def test_default_max_results(self):
        with patch("tools.crawler.web_search") as mock_ws:
            mock_ws.return_value = "results"
            web_search.execute("test")
            mock_ws.assert_called_once_with("test", 5)

    def test_empty_query(self):
        with patch("tools.crawler.web_search") as mock_ws:
            mock_ws.return_value = ""
            result = web_search.execute("")
            assert result == ""

    def test_register_schema(self):
        registry = {}
        web_search.register(lambda n, f, s: registry.update({n: (f, s)}))
        assert "web_search" in registry
        schema = registry["web_search"][1]
        assert schema["function"]["name"] == "web_search"
        assert "query" in schema["function"]["parameters"]["properties"]
        assert "max_results" in schema["function"]["parameters"]["properties"]
        assert schema["function"]["parameters"]["required"] == ["query"]


class TestWebExtract:
    '''web_extract.execute() — 委托给 crawler.web_fetch_markdown'''

    def test_execute_calls_crawler(self):
        with patch("tools.crawler.web_fetch_markdown") as mock_fetch:
            mock_fetch.return_value = "# Page Title\n\nContent"
            result = web_extract.execute("https://example.com")
            mock_fetch.assert_called_once_with("https://example.com")
            assert "# Page Title" in result

    def test_empty_url_returns_empty(self):
        with patch("tools.crawler.web_fetch_markdown") as mock_fetch:
            mock_fetch.return_value = ""
            result = web_extract.execute("")
            assert result == ""

    def test_register_schema(self):
        registry = {}
        web_extract.register(lambda n, f, s: registry.update({n: (f, s)}))
        assert "web_extract" in registry
        schema = registry["web_extract"][1]
        assert schema["function"]["name"] == "web_extract"
        assert "url" in schema["function"]["parameters"]["properties"]
        assert schema["function"]["parameters"]["required"] == ["url"]


class TestWebFetch:
    '''web_fetch.execute() — 委托给 crawler.web_fetch'''

    def test_execute_calls_crawler(self):
        with patch("tools.crawler.web_fetch") as mock_fetch:
            mock_fetch.return_value = "full page content here"
            result = web_fetch.execute("https://example.com/page")
            mock_fetch.assert_called_once_with("https://example.com/page")
            assert "full page content" in result

    def test_register_schema(self):
        registry = {}
        web_fetch.register(lambda n, f, s: registry.update({n: (f, s)}))
        assert "web_fetch" in registry
        schema = registry["web_fetch"][1]
        assert schema["function"]["name"] == "web_fetch"
        assert "url" in schema["function"]["parameters"]["properties"]
