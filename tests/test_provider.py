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
        assert "deepseek-chat" in cfg["models"]
        assert cfg["context_length"] == 1_000_000

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
        assert len(providers) == 7

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
        assert result["model"] == "deepseek-chat"

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

    def test_fallback_to_deepseek_on_unknown(self, monkeypatch):
        monkeypatch.setenv("BOBO_PROVIDER", "some_unknown_provider")
        result = resolve_provider()
        assert result["name"] == "deepseek"  # fallback

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
