"""Provider registry — maps provider names to API settings.

A provider is defined by:
  - env_key:   The env var to read for the API key
  - base_url:  The API endpoint for chat completions
  - models:    List of available model names (first is default)
"""

PROVIDERS = {
    "deepseek": {
        "env_key": "DEEPSEEK_API_KEY",
        "base_url": "https://api.deepseek.com/v1/chat/completions",
        "models": ["deepseek-chat", "deepseek-reasoner"],
        "context_length": 1000000,
    },
    "openai": {
        "env_key": "OPENAI_API_KEY",
        "base_url": "https://api.openai.com/v1/chat/completions",
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
        "context_length": 128000,
    },
    "anthropic": {
        "env_key": "ANTHROPIC_API_KEY",
        "base_url": "https://api.anthropic.com/v1/messages",
        "models": ["claude-sonnet-4-20250514", "claude-haiku-3-20240307"],
        "context_length": 200000,
    },
    "openrouter": {
        "env_key": "OPENROUTER_API_KEY",
        "base_url": "https://openrouter.ai/api/v1/chat/completions",
        "models": ["openai/gpt-4o", "anthropic/claude-sonnet-4", "google/gemini-2.0-flash"],
        "context_length": 128000,
    },
    "google": {
        "env_key": "GOOGLE_API_KEY",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "models": ["gemini-2.0-flash", "gemini-2.0-pro"],
        "context_length": 1000000,
    },
    "ollama": {
        "env_key": "",  # No API key needed
        "base_url": "http://localhost:11434/v1/chat/completions",
        "models": ["llama3", "mistral", "qwen2.5"],
        "context_length": 32768,
    },
    "custom": {
        "env_key": "CUSTOM_API_KEY",
        "base_url": "",  # Must be set by user
        "models": [],
        "context_length": 128000,
    },
}


def get_provider(name: str) -> dict | None:
    """Return the provider config dict, or None if unknown."""
    return PROVIDERS.get(name)


def list_providers() -> list[str]:
    """Return all known provider names."""
    return list(PROVIDERS.keys())


def resolve_provider(provider_name: str = None, env_file: str = None) -> dict:
    """Resolve the active provider configuration.

    Priority:
      1. Explicit provider_name argument
      2. BOBO_PROVIDER env var
      3. DeepSeek (default)

    Returns a dict with keys: name, api_key, base_url, model.
    """
    import os

    if env_file:
        from dotenv import load_dotenv
        load_dotenv(env_file)

    name = (provider_name or os.environ.get("BOBO_PROVIDER") or "deepseek").lower()
    provider = get_provider(name)

    # Fallback: try custom provider prefix
    if not provider:
        if name.startswith("custom:"):
            provider = get_provider("custom")
    if not provider:
        name = "deepseek"
        provider = get_provider("deepseek")
        if not provider:
            raise ValueError("Default provider 'deepseek' not found in registry")

    env_key = provider["env_key"]
    api_key = os.environ.get(env_key, "") if env_key else ""

    base_url = provider["base_url"]
    base_url = os.environ.get("API_BASE_URL", base_url)

    model = os.environ.get("API_MODEL_NAME", "")
    if not model and provider["models"]:
        model = provider["models"][0]

    return {
        "name": name,
        "api_key": api_key,
        "base_url": base_url,
        "model": model,
        "context_length": provider.get("context_length", 128000),
    }
