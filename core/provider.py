"""Provider registry — maps provider names to API settings.

A provider is defined by:
  - env_key:   The env var to read for the API key
  - base_url:  The API endpoint for chat completions
  - models:    List of available model names (first is default)
  - reasoning: Reasoning/thinking protocol declaration (TICKET-PROVIDER-ADAPTER)
      field:             streaming chunk field carrying reasoning text
                         ("reasoning_content" DeepSeek / "thinking" Kimi etc.)
      echo_required:     True if tool-turn assistant messages must echo back
                         reasoning on the next request (DeepSeek requires it)
      thinking_mode:     True if thinking is on by default for this model
      stream_reasoning:  True if streaming emits reasoning chunks separately
      disable_supported: True if API accepts explicit thinking disable
                         (payload {"thinking": {"type": "disabled"}})
  - tools: Tool-calling protocol declaration (TICKET-PROVIDER-ADAPTER)
      native:    True if API supports native tool_calls (OpenAI-style)
      parallel:  True if multiple tool_calls per turn supported
      json_mode: True if API has native response_format json_object

  Conservative defaults (missing fields):
      reasoning absent -> no-thinking model (never set/echo reasoning fields)
      tools absent     -> native=False, parallel=False, json_mode=False
  (These keep a partially-declared provider runnable without protocol mismatch.)
"""

import logging
import re

logger = logging.getLogger(__name__)

PROVIDERS = {
    "deepseek": {
        "name": "DeepSeek",
        "env_key": "DEEPSEEK_API_KEY",
        "base_url": "https://api.deepseek.com/v1/chat/completions",
        "models": ["deepseek-v4-flash", "deepseek-v4-pro"],
        # 128K：DeepSeek 实际上下文窗口为 128K（deepseek-chat / deepseek-reasoner）。
        # 错误的高估会让 token 预算失效，宁可低估。
        "context_length": 128000,
        # TICKET-E4b：deepseek-v4-flash / v4-pro 官方真实窗口 1M（2026-04 发布）。
        # 128000 保留为老型号兜底；model_context 按型号覆盖。
        "model_context": {"deepseek-v4-flash": 1000000, "deepseek-v4-pro": 1000000,
                          "deepseek-v4-flash-vision-exp": 1000000},  # vision-exp 同 v4-flash 系 1M（owner 实弹修复 2026-08-21）
        # COST-3：v4 系前缀继承 → 未来 deepseek-v4-* 新模型自动 1M，消除逐条枚举漏登记
        "context_family": {"deepseek-v4-": 1000000},
        "dynamic_models": True,  # 动态拉 /v1/models（DeepSeek 上新模型自动可见，实测 3 个含 vision）
        # TICKET-PROVIDER-ADAPTER：协议声明（thinking 字段=reasoning_content，
        # 工具轮后必须回传，支持显式关 thinking）
        "reasoning": {
            "field": "reasoning_content",
            "echo_required": True,
            "thinking_mode": True,
            "stream_reasoning": True,
            "disable_supported": True,
        },
        "tools": {"native": True, "parallel": True, "json_mode": False},
    },
    "openai": {
        "name": "OpenAI",
        "env_key": "OPENAI_API_KEY",
        "base_url": "https://api.openai.com/v1/chat/completions",
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
        "context_length": 128000,
        # gpt-4o 无 thinking 协议（默认无推理字段，无需回传）
        "reasoning": {
            "field": "reasoning_content",
            "echo_required": False,
            "thinking_mode": False,
            "stream_reasoning": False,
            "disable_supported": False,
        },
        "tools": {"native": True, "parallel": True, "json_mode": True},
    },
    "anthropic": {
        "name": "Anthropic",
        "env_key": "ANTHROPIC_API_KEY",
        "base_url": "https://api.anthropic.com/v1/messages",
        "models": ["claude-sonnet-4-20250514", "claude-haiku-3-20240307"],
        "context_length": 200000,
        # Claude：thinking 通过 extended thinking 参数开启（默认关），
        # 回传非必需（不带 thinking 字段即可）
        "reasoning": {
            "field": "thinking",
            "echo_required": False,
            "thinking_mode": False,
            "stream_reasoning": True,
            "disable_supported": True,
        },
        "tools": {"native": True, "parallel": True, "json_mode": False},
    },
    "openrouter": {
        "name": "OpenRouter",
        "env_key": "OPENROUTER_API_KEY",
        "base_url": "https://openrouter.ai/api/v1/chat/completions",
        "models": ["openai/gpt-4o", "anthropic/claude-sonnet-4", "google/gemini-2.0-flash"],
        "context_length": 128000,
        # OpenRouter 透传各家协议——按 OpenAI 兼容处理（reasoning 字段各家不同，
        # 保守默认不回传；实际取决于背后模型）
        "reasoning": {
            "field": "reasoning_content",
            "echo_required": False,
            "thinking_mode": False,
            "stream_reasoning": True,
            "disable_supported": False,
        },
        "tools": {"native": True, "parallel": True, "json_mode": False},
    },
    "google": {
        "name": "Google",
        "env_key": "GOOGLE_API_KEY",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "models": ["gemini-2.0-flash", "gemini-2.0-pro"],
        "context_length": 128000,  # 保守值：Gemini 2.0 Flash 官方 1M，但高估会让 token 预算失效
        # Gemini：OpenAI 兼容端点，thinking 通过 thinkingConfig 开启（默认关）
        "reasoning": {
            "field": "reasoning_content",
            "echo_required": False,
            "thinking_mode": False,
            "stream_reasoning": True,
            "disable_supported": False,
        },
        "tools": {"native": True, "parallel": True, "json_mode": True},
    },
    "ollama": {
        "name": "Ollama",
        "env_key": "",  # No API key needed
        "base_url": "http://localhost:11434/v1/chat/completions",
        "models": ["llama3", "mistral", "qwen2.5"],
        "context_length": 32768,
        # 本地模型：OpenAI 兼容端点，无 thinking 协议（保守默认）
        "reasoning": {
            "field": "reasoning_content",
            "echo_required": False,
            "thinking_mode": False,
            "stream_reasoning": False,
            "disable_supported": False,
        },
        "tools": {"native": True, "parallel": False, "json_mode": False},
    },
    "moonshot": {
        "name": "Moonshot (Kimi)",
        "env_key": "MOONSHOT_API_KEY",
        "base_url": "https://api.moonshot.cn/v1/chat/completions",
        "models": ["kimi-k3", "kimi-k2.6", "kimi-k2.7-code-highspeed"],
        "context_length": 128000,  # COST-3 兜底：moonshot-v1 系等未声明模型回退 128K（kimi-k3 走 model_context 精确 1M）
        "model_context": {"kimi-k3": 1000000, "kimi-k2.6": 262144, "kimi-k2.7-code-highspeed": 262144},
        # COST-3：kimi-k2.x 家族继承 → 未来 kimi-k2.* 新模型自动 256K；kimi-k3 精确 1M 命中优先
        "context_family": {"kimi-k2.": 262144},
        "temperature": 1.0,
        "max_tokens": 32768,
        "dynamic_models": True,  # 动态拉 /v1/models（实测 12 个，含 kimi-k2.7-code + vision 系列）
        # Kimi K3：OpenAI 兼容端点实弹验证（2026-08-20）——thinking 字段=
        # reasoning_content（与 DeepSeek 同名，非 thinking）；工具轮后需回传
        # reasoning_content 内容；支持显式关 thinking（{"thinking":{"type":"disabled"}}）
        "reasoning": {
            "field": "reasoning_content",
            "echo_required": True,
            "thinking_mode": True,
            "stream_reasoning": True,
            "disable_supported": True,
        },
        "tools": {"native": True, "parallel": True, "json_mode": False},
    },
    "lmstudio": {
        "name": "LM Studio",
        "env_key": "",  # 本地无 key
        "base_url": "http://localhost:1234/v1/chat/completions",
        "models": [],  # 用户加载什么模型就用什么（API_MODEL_NAME 指定）
        "context_length": 32768,
        # LM Studio 本地：OpenAI 兼容端点，thinking 取决于加载的模型
        # （保守默认：无 thinking 协议，不回传）
        "reasoning": {
            "field": "reasoning_content",
            "echo_required": False,
            "thinking_mode": False,
            "stream_reasoning": False,
            "disable_supported": False,
        },
        "tools": {"native": True, "parallel": False, "json_mode": False},
    },
    "glm": {
        "name": "GLM (Zhipu)",
        "env_key": "GLM_API_KEY",
        "base_url": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
        "models": ["glm-5.3", "glm-5.2", "glm-5.1", "glm-5", "glm-4.7"],  # 兜底（官方 /v1/models 动态拉取优先）
        "dynamic_models": True,  # 设置页动态查官方 /v1/models（模型名永不过时）
        "context_length": 128000,
        # 智谱 GLM：OpenAI 兼容端点。GLM-4.5+ 支持 thinking（reasoning_content
        # 字段）；官方 /v1/models 可实时查询（models.py 对非 localhost 也支持
        # 动态拉取——见 _fetch_remote_models）。
        "reasoning": {
            "field": "reasoning_content",
            "echo_required": False,
            "thinking_mode": True,
            "stream_reasoning": True,
            "disable_supported": False,
        },
        "tools": {"native": True, "parallel": True, "json_mode": True},
    },
    "custom": {
        "name": "Custom",
        "env_key": "CUSTOM_API_KEY",
        "base_url": "",  # Must be set by user
        "models": [],
        "context_length": 128000,
        # 用户自定义端点：OpenAI 兼容假设（保守默认，无 thinking 协议）
        "reasoning": {
            "field": "reasoning_content",
            "echo_required": False,
            "thinking_mode": False,
            "stream_reasoning": False,
            "disable_supported": False,
        },
        "tools": {"native": True, "parallel": False, "json_mode": False},
    },
}


# ── Vision 能力声明（TICKET-VISION-INPUT，COST-3 特批标记）──
# 哪些 provider/model 支持图像输入（多模态）。默认无 vision（未声明=False）。
# 非 vision 模型发图 → 由调用方（read_local_file 图片分支）明确报错，不静默。
# DeepSeek：vision 模型名含 "vision"（如 deepseek-v4-flash-vision-exp，owner 实弹 2026-08-21）。
# OpenAI：gpt-4o 系列支持图像输入；Google：Gemini 2.0 系列支持；OpenRouter 透传各家。
_VISION_RULES = {
    "deepseek": {"substring": "vision"},            # 任何含 vision 的 deepseek 模型
    "openai": {"models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"]},
    "google": {"models": ["gemini-2.0-flash", "gemini-2.0-pro"]},
    "openrouter": {"substring": "gpt-4o"},
    "moonshot": {"substring": "vision"},            # kimi vision 系列（若有）
}


def supports_vision(provider_name: str, model_name: str) -> bool:
    """判断 provider/model 是否支持图像输入（vision）。

    规则：per-provider _VISION_RULES（models 精确列表 / substring 子串匹配）。
    未声明 / 未命中 = False（保守：非 vision 模型发图 → 调用方明确报错而非静默）。
    """
    if not model_name:
        return False
    rule = _VISION_RULES.get((provider_name or "").lower())
    if not rule:
        return False
    if model_name in (rule.get("models") or []):
        return True
    sub = rule.get("substring")
    if sub and sub in model_name:
        return True
    return False


def _match_context_length(provider: dict, model_name: str) -> int | None:
    """解析模型上下文窗口，按优先级：精确 → 前缀家族 → 正则家族 → None。

    COST-3：把 model_context 从"逐条精确枚举"升级为"精确修正 + 前缀/家族继承"。
    未来 deepseek-v4-* / kimi-k2.* 等新模型自动继承家族窗口，消除漏登记就回退默认
    低估（如 vision-exp 漏 1M → 回退 128K）的病根。返回 None 由调用方回退 provider
    默认并打 warn 告警，不再静默低估。
    """
    if not model_name:
        return None
    model_context = provider.get("model_context") or {}
    if model_name in model_context:
        return model_context[model_name]
    # 前缀家族继承：如 deepseek-v4-* → 1M、kimi-k2.x → 256K
    for prefix, ctx in (provider.get("context_family") or {}).items():
        if model_name.startswith(prefix):
            return ctx
    # 正则家族：如 moonshot-v1.* 等未精确命中的系
    for pattern, ctx in (provider.get("context_family_regex") or {}).items():
        if re.search(pattern, model_name):
            return ctx
    return None


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

    # 每模型上下文窗口：精确 → 家族继承 → provider 默认（COST-3，不再静默低估）
    model_ctx = _match_context_length(provider, model)
    if model_ctx is None:
        logger.warning(
            "COST-3 模型窗口未确认：%s/%s 未声明 context，回退 provider 默认 %s。"
            "请补登记 model_context 或 context_family，避免窗口被低估。",
            name, model, provider.get("context_length", 128000))
    context_len = model_ctx if model_ctx is not None else provider.get("context_length", 128000)

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
    provider = get_provider(cfg["name"])
    # 显式指定 model_name 时再查一次（resolve_provider 已按 os.environ 中的 model 解析）
    if model_name and provider and cfg.get("model") != model_name:
        model_ctx = _match_context_length(provider, model_name)
        if model_ctx is not None:
            return model_ctx
        logger.warning(
            "COST-3 模型窗口未确认：%s/%s 未声明 context，回退 provider 默认 %s。",
            cfg["name"], model_name, provider.get("context_length", 128000))
        return provider.get("context_length", 128000)
    return cfg.get("context_length", 128000)
