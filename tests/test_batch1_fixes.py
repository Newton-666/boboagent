"""Regression tests for batch1 fixes: worker LLM caller cache key, output dedup in code blocks."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestWorkerLLMCallerCache:
    """Fix #4: _llm_caller_cache must miss after provider/model/key changes."""

    @pytest.fixture(autouse=True)
    def _reset_cache(self):
        import tools.spawn_worker as sw
        sw._llm_caller_cache = None
        sw._llm_caller_cache_key = None
        yield
        sw._llm_caller_cache = None
        sw._llm_caller_cache_key = None

    def _patch(self, monkeypatch, config):
        import core.provider
        import core.llm_caller
        created = []

        monkeypatch.setattr(core.provider, "resolve_provider", lambda *a, **kw: config)
        monkeypatch.setattr(
            core.llm_caller, "create_llm_caller",
            lambda **kw: created.append(kw) or kw,
        )
        return created

    def test_same_config_reuses_cached_caller(self, monkeypatch):
        import tools.spawn_worker as sw
        config = {"name": "deepseek", "model": "m1", "api_key": "sk-aaa", "base_url": "u"}
        created = self._patch(monkeypatch, config)

        first = sw._get_llm_caller()
        second = sw._get_llm_caller()
        assert first is second
        assert len(created) == 1

    def test_different_api_key_produces_new_caller(self, monkeypatch):
        import tools.spawn_worker as sw
        config = {"name": "deepseek", "model": "m1", "api_key": "sk-aaa", "base_url": "u"}
        created = self._patch(monkeypatch, config)

        first = sw._get_llm_caller()
        config["api_key"] = "sk-bbb"
        second = sw._get_llm_caller()
        assert first is not second
        assert len(created) == 2
        assert second["api_key"] == "sk-bbb"

    def test_different_provider_produces_new_caller(self, monkeypatch):
        import tools.spawn_worker as sw
        config = {"name": "deepseek", "model": "m1", "api_key": "sk-aaa", "base_url": "u"}
        created = self._patch(monkeypatch, config)

        first = sw._get_llm_caller()
        config["name"] = "openai"
        second = sw._get_llm_caller()
        assert first is not second
        assert len(created) == 2

    def test_different_model_produces_new_caller(self, monkeypatch):
        import tools.spawn_worker as sw
        config = {"name": "deepseek", "model": "m1", "api_key": "sk-aaa", "base_url": "u"}
        created = self._patch(monkeypatch, config)

        first = sw._get_llm_caller()
        config["model"] = "m2"
        second = sw._get_llm_caller()
        assert first is not second
        assert len(created) == 2

    def test_cache_key_does_not_contain_plaintext_key(self, monkeypatch):
        import tools.spawn_worker as sw
        config = {"name": "deepseek", "model": "m1", "api_key": "sk-secret-key", "base_url": "u"}
        self._patch(monkeypatch, config)

        sw._get_llm_caller()
        assert "sk-secret-key" not in str(sw._llm_caller_cache_key)


class TestFormatFinalOutputCodeBlock:
    """Fix #6: _format_final_output must not dedup lines inside code fences."""

    def _format(self, content):
        from core.tool_runner import ToolRunnerMixin
        return ToolRunnerMixin._format_final_output(None, content)

    def test_duplicate_lines_inside_code_block_preserved(self):
        content = (
            "说明文字\n"
            "```python\n"
            "def a():\n"
            "    return 1\n"
            "def b():\n"
            "    return 1\n"
            "```\n"
            "结束"
        )
        result = self._format(content)
        assert result.count("    return 1") == 2
        assert "def a():" in result and "def b():" in result

    def test_duplicate_lines_outside_code_block_still_deduped(self):
        content = "重复行\n重复行\n唯一行"
        result = self._format(content)
        assert result.count("重复行") == 1
        assert "唯一行" in result

    def test_mixed_inside_and_outside(self):
        content = (
            "配置说明\n"
            "配置说明\n"
            "```yaml\n"
            "key: value\n"
            "key: value\n"
            "```\n"
            "配置说明"
        )
        result = self._format(content)
        # 围栏外：3 次 -> 1 次；围栏内：2 次保留
        assert result.count("配置说明") == 1
        assert result.count("key: value") == 2
