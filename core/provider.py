"""Provider registry — maps provider names to API settings.

A provider is defined by:
  - env_key:   The env var to read for the API key
  - base_url:  The API endpoint for chat completions
  - models:    List of available model names (first is default)
"""

PROVIDERS = {
    "deepseek": {
        "name": "DeepSeek",
        "env_key": "DEEPSEEK_API_KEY",
        "base_url": "https://api.deepseek.com/v1/chat/completions",
        "models": ["deepseek-v4-pro", "deepseek-v4-flash"],
        # 128K：DeepSeek 实际上下文窗口为 128K（deepseek-chat / deepseek-reasoner）。
        # 错误的高估会让 token 预算失效，宁可低估。
        "context_length": 128000,
        # TICKET-E4b：deepseek-v4-flash / v4-pro 官方真实窗口 1M（2026-04 发布）。
        # 128000 保留为老型号兜底；model_context 按型号覆盖。
        "model_context": {"deepseek-v4-flash": 1000000, "deepseek-v4-pro": 1000000},
    },
    "openai": {
        "name": "OpenAI",
        "env_key": "OPENAI_API_KEY",
        "base_url": "https://api.openai.com/v1/chat/completions",
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
        "context_length": 128000,
    },
    "anthropic": {
        "name": "Anthropic",
        "env_key": "ANTHROPIC_API_KEY",
        "base_url": "https://api.anthropic.com/v1/messages",
        "models": ["claude-sonnet-4-20250514", "claude-haiku-3-20240307"],
        "context_length": 200000,
    },
    "openrouter": {
        "name": "OpenRouter",
        "env_key": "OPENROUTER_API_KEY",
        "base_url": "https://openrouter.ai/api/v1/chat/completions",
        "models": ["openai/gpt-4o", "anthropic/claude-sonnet-4", "google/gemini-2.0-flash"],
        "context_length": 128000,
    },
    "google": {
        "name": "Google",
        "env_key": "GOOGLE_API_KEY",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "models": ["gemini-2.0-flash", "gemini-2.0-pro"],
        "context_length": 128000,  # 保守值：Gemini 2.0 Flash 官方 1M，但高估会让 token 预算失效
    },
    "ollama": {
        "name": "Ollama",
        "env_key": "",  # No API key needed
        "base_url": "http://localhost:11434/v1/chat/completions",
        "models": ["llama3", "mistral", "qwen2.5"],
        "context_length": 32768,
    },
    "moonshot": {
        "name": "Moonshot (Kimi)",
        "env_key": "MOONSHOT_API_KEY",
        "base_url": "https://api.moonshot.cn/v1/chat/completions",
        "models": ["kimi-k3", "kimi-k2.6", "kimi-k2.7-code-highspeed"],
        "context_length": 1048576,  # k3=1M
        "model_context": {"kimi-k2.6": 262144, "kimi-k2.7-code-highspeed": 262144},
        "temperature": 1.0,
        "max_tokens": 32768,
    },
    "custom": {
        "name": "Custom",
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
        # 未知 provider → 用 128k 保守窗口（避免 DeepSeek 1M 窗口导致溢出）
        return {
            "name": name,
            "api_key": os.environ.get("CUSTOM_API_KEY", ""),
            "base_url": os.environ.get("API_BASE_URL", ""),
            "model": os.environ.get("API_MODEL_NAME", ""),
            "context_length": 128000,
        }

    env_key = provider["env_key"]
    api_key = os.environ.get(env_key, "") if env_key else ""

    base_url = provider["base_url"]
    base_url = os.environ.get("API_BASE_URL", base_url)

    model = os.environ.get("API_MODEL_NAME", "")
    if not model and provider["models"]:
        model = provider["models"][0]

    # 每模型上下文窗口：model_context[model] → provider context_length → 128k 兜底
    model_ctx = (provider.get("model_context") or {}).get(model)
    context_len = model_ctx or provider.get("context_length", 128000)

    return {
        "name": name,
        "api_key": api_key,
        "base_url": base_url,
        "model": model,
        "context_length": context_len,
    }


def get_context_length(provider_name: str = None, model_name: str = None) -> int:
    """返回当前 provider/model 组合的上下文窗口大小（token 数）。
    优先 BOBO_CONTEXT_LENGTH 环境变量覆盖，其次每模型配置，最后 provider 默认。
    """
    import os
    env_override = os.environ.get("BOBO_CONTEXT_LENGTH", "")
    if env_override:
        try:
            return int(env_override)
        except ValueError:
            pass
    cfg = resolve_provider(provider_name)
    # 如果指定了 model_name，再查一次 model_context（resolve_provider 已用 os.environ 中的 model）
    if model_name and cfg.get("model") != model_name:
        provider = get_provider(cfg["name"])
        if provider:
            model_ctx = (provider.get("model_context") or {}).get(model_name)
            if model_ctx:
                return model_ctx
    return cfg.get("context_length", 128000)
