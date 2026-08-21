"""Tests for core/provider.py — provider resolution, model selection, fallback."""

import os
import pytest
from core.provider import get_provider, list_providers, resolve_provider, PROVIDERS


class TestGetProvider:
    """Tests for get_provider(name)."""

    def test_known_provider_deepseek(self):
        cfg = get_provider("deepseek")
        assert cfg is not None
        assert cfg["env_key"] == "DEEPSEEK_API_KEY"
        assert "deepseek-v4-pro" in cfg["models"]
        assert cfg["context_length"] == 128_000  # TICKET-023 窗口修正

    def test_known_provider_openai(self):
        cfg = get_provider("openai")
        assert cfg is not None
        assert cfg["env_key"] == "OPENAI_API_KEY"
        assert "gpt-4o" in cfg["models"]

    def test_known_provider_anthropic(self):
        cfg = get_provider("anthropic")
        assert cfg is not None
        assert cfg["env_key"] == "ANTHROPIC_API_KEY"
        assert any("claude" in m for m in cfg["models"])

    def test_known_provider_ollama(self):
        cfg = get_provider("ollama")
        assert cfg is not None
        assert cfg["env_key"] == ""  # No API key needed
        assert "localhost" in cfg["base_url"]

    def test_unknown_provider_returns_none(self):
        assert get_provider("nonexistent") is None

    def test_case_insensitive(self):
        # get_provider does exact match — resolve_provider handles lowercase
        assert get_provider("DEEPSEEK") is None


class TestListProviders:
    """Tests for list_providers()."""

    def test_returns_all_known_providers(self):
        providers = list_providers()
        assert "deepseek" in providers
        assert "openai" in providers
        assert "anthropic" in providers
        assert "openrouter" in providers
        assert "google" in providers
        assert "ollama" in providers
        assert "custom" in providers
        # TICKET-PROVIDER-ADAPTER：新增 glm + lmstudio（共 10 个）
        assert len(providers) == 10  # deepseek, openai, anthropic, openrouter, google, ollama, moonshot, lmstudio, glm, custom

    def test_returns_list(self):
        assert isinstance(list_providers(), list)


class TestResolveProvider:
    """Tests for resolve_provider() — the main entry point."""

    def test_defaults_to_deepseek(self, monkeypatch):
        # Clear any env vars that might interfere
        monkeypatch.delenv("BOBO_PROVIDER", raising=False)
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        monkeypatch.delenv("API_BASE_URL", raising=False)
        monkeypatch.delenv("API_MODEL_NAME", raising=False)

        result = resolve_provider()
        assert result["name"] == "deepseek"
        assert result["api_key"] == ""  # no key set
        assert "deepseek.com" in result["base_url"]
        assert result["model"] == "deepseek-v4-flash"  # TICKET-PROVIDER-ADAPTER：默认 flash（原 pro）

    def test_explicit_name_overrides_env(self, monkeypatch):
        monkeypatch.setenv("BOBO_PROVIDER", "deepseek")
        result = resolve_provider(provider_name="openai")
        assert result["name"] == "openai"

    def test_env_var_selection(self, monkeypatch):
        monkeypatch.setenv("BOBO_PROVIDER", "ollama")
        monkeypatch.delenv("API_MODEL_NAME", raising=False)
        result = resolve_provider()
        assert result["name"] == "ollama"
        assert "localhost" in result["base_url"]

    def test_model_env_override(self, monkeypatch):
        monkeypatch.setenv("API_MODEL_NAME", "gpt-4-turbo")
        monkeypatch.setenv("BOBO_PROVIDER", "openai")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        result = resolve_provider()
        assert result["model"] == "gpt-4-turbo"

    def test_base_url_env_override(self, monkeypatch):
        monkeypatch.setenv("API_BASE_URL", "https://custom.proxy.com/v1")
        result = resolve_provider(provider_name="deepseek")
        assert result["base_url"] == "https://custom.proxy.com/v1"

    def test_api_key_from_env(self, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-mytestkey123")
        result = resolve_provider(provider_name="deepseek")
        assert result["api_key"] == "sk-mytestkey123"

    def test_fallback_uses_conservative_window(self, monkeypatch):
        monkeypatch.setenv("BOBO_PROVIDER", "some_unknown_provider")
        result = resolve_provider()
        assert result["context_length"] == 128000  # 未知 provider 保守 128k

    def test_custom_provider_prefix(self, monkeypatch):
        monkeypatch.setenv("BOBO_PROVIDER", "custom:myproxy")
        monkeypatch.setenv("CUSTOM_API_KEY", "custom-key-123")
        monkeypatch.setenv("API_BASE_URL", "https://myproxy.com/v1")
        monkeypatch.delenv("API_MODEL_NAME", raising=False)
        result = resolve_provider()
        assert result["name"] in ("custom", "custom:myproxy")

    def test_context_length_included(self):
        result = resolve_provider(provider_name="deepseek")
        assert "context_length" in result
        # TICKET-E4b：默认模型 deepseek-v4-pro 命中 model_context → 1M
        assert result["context_length"] == 1_000_000

    def test_ollama_no_api_key_needed(self, monkeypatch):
        monkeypatch.setenv("BOBO_PROVIDER", "ollama")
        result = resolve_provider()
        assert result["api_key"] == ""

    def test_google_provider(self, monkeypatch):
        monkeypatch.setenv("BOBO_PROVIDER", "google")
        monkeypatch.setenv("GOOGLE_API_KEY", "google-key-123")
        monkeypatch.delenv("API_MODEL_NAME", raising=False)
        result = resolve_provider()
        assert result["name"] == "google"
        assert "gemini" in result["model"].lower() or result["model"] == "gemini-2.0-flash"


class TestDeepSeekModelContext:
    """TICKET-E4b：DeepSeek 分型号窗口（v4 系列 1M，老型号兜底 128K）。"""

    def test_deepseek_v4_flash_1m(self, monkeypatch):
        monkeypatch.setenv("BOBO_PROVIDER", "deepseek")
        monkeypatch.setenv("API_MODEL_NAME", "deepseek-v4-flash")
        result = resolve_provider()
        assert result["name"] == "deepseek"
        assert result["model"] == "deepseek-v4-flash"
        assert result["context_length"] == 1_000_000

    def test_deepseek_v4_pro_1m(self, monkeypatch):
        monkeypatch.setenv("BOBO_PROVIDER", "deepseek")
        monkeypatch.setenv("API_MODEL_NAME", "deepseek-v4-pro")
        result = resolve_provider()
        assert result["model"] == "deepseek-v4-pro"
        assert result["context_length"] == 1_000_000

    def test_deepseek_legacy_model_fallback_128k(self, monkeypatch):
        # 老型号（deepseek-chat 等）不在 model_context → 走 context_length 兜底 128K
        monkeypatch.setenv("BOBO_PROVIDER", "deepseek")
        monkeypatch.setenv("API_MODEL_NAME", "deepseek-chat")
        result = resolve_provider()
        assert result["model"] == "deepseek-chat"
        assert result["context_length"] == 128_000

    def test_deepseek_no_model_env_default_1m(self, monkeypatch):
        # 未设 API_MODEL_NAME → 默认模型 deepseek-v4-pro 命中 1M
        monkeypatch.setenv("BOBO_PROVIDER", "deepseek")
        monkeypatch.delenv("API_MODEL_NAME", raising=False)
        result = resolve_provider()
        assert result["context_length"] == 1_000_000

    def test_get_context_length_v4_flash(self, monkeypatch):
        monkeypatch.setenv("BOBO_PROVIDER", "deepseek")
        monkeypatch.setenv("API_MODEL_NAME", "deepseek-v4-flash")
        monkeypatch.delenv("BOBO_CONTEXT_LENGTH", raising=False)
        from core.provider import get_context_length
        assert get_context_length() == 1_000_000

    def test_get_context_length_legacy(self, monkeypatch):
        monkeypatch.setenv("BOBO_PROVIDER", "deepseek")
        monkeypatch.setenv("API_MODEL_NAME", "deepseek-chat")
        monkeypatch.delenv("BOBO_CONTEXT_LENGTH", raising=False)
        from core.provider import get_context_length
        assert get_context_length() == 128_000
