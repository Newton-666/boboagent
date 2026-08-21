"""handlers/models.py — Model Picker handler（TUI 交互式模型切换）。"""

import os

from bobo_tui_gateway.server_utils import ok, write_atomic
from config import BOBO_DATA_DIR


def handle_model_options(params: dict, rid: str) -> dict:
    """返回所有 provider 及其 model 列表，供 TUI ModelPicker 渲染。
    API key 的检查只读环境变量，不经过 LLM。
    TICKET-PROVIDER-ADAPTER：本地 provider（lmstudio/ollama）models 声明为空
    时，动态查询其 /v1/models 接口拿真实可用模型列表（LM Studio 管模型仓库，
    动态查询才是事实源）。查询失败静默回退空列表。
    """
    from core.provider import PROVIDERS, get_provider
    from config import API_MODEL_NAME, API_KEY

    active_provider_name = os.environ.get("BOBO_PROVIDER", "deepseek")
    providers_out = []

    for slug, cfg in PROVIDERS.items():
        env_key = cfg.get("env_key", "")
        models = list(cfg.get("models", []))
        # 本地 provider 且声明无模型 → 动态查 /v1/models（LM Studio 已加载/可用的）
        if not models and "localhost" in cfg.get("base_url", ""):
            live = _fetch_local_models(cfg.get("base_url", ""))
            if live:
                models = live
        # 如果 provider 有 env_key，检查是否已配置
        authenticated = True
        if env_key:
            authenticated = bool(os.environ.get(env_key, ""))

        providers_out.append({
            "name": cfg.get("name", slug),
            "slug": slug,
            "auth_type": "api_key" if env_key else "none",
            "authenticated": authenticated,
            "is_current": slug == active_provider_name,
            "key_env": env_key,
            "models": models,
            "total_models": len(models),
            "warning": "" if authenticated else f"Set {env_key} in {BOBO_DATA_DIR}/.env",
        })

    return ok(rid, {
        "model": API_MODEL_NAME,
        "provider": active_provider_name,
        "providers": providers_out,
    })


def _fetch_local_models(base_url: str) -> list:
    """查询本地 OpenAI 兼容端点的 /v1/models，返回模型 id 列表。失败 → []。"""
    try:
        import requests
        # 本地端点禁代理（同 llm_caller 的代理劫持修复）
        proxies = {"http": None, "https": None}
        url = base_url.replace("/chat/completions", "/models")
        r = requests.get(url, timeout=5, proxies=proxies)
        if r.status_code != 200:
            return []
        data = r.json()
        return [m.get("id", "") for m in (data.get("data") or []) if m.get("id")]
    except Exception:
        return []


def handle_model_save_key(params: dict, rid: str, engine_cache: dict) -> dict:
    """保存 API key 到 .env（直接写入，不经过 LLM）。
    前端 ModelPicker 的 key 输入框调用此方法。"""
    slug = params.get("slug", "")
    api_key = params.get("api_key", "").strip()

    if not slug or not api_key:
        return ok(rid, {"ok": False, "error": "slug and api_key required"})

    from core.provider import PROVIDERS
    cfg = PROVIDERS.get(slug)
    if not cfg:
        return ok(rid, {"ok": False, "error": f"unknown provider: {slug}"})

    env_key = cfg.get("env_key", "")
    if not env_key:
        return ok(rid, {"ok": False, "error": f"{slug} does not use an API key"})

    # 原子写入 .env
    env_path = str(BOBO_DATA_DIR / ".env")
    try:
        lines = []
        if os.path.exists(env_path):
            with open(env_path) as f:
                lines = f.readlines()
        found = False
        for i, line in enumerate(lines):
            if line.strip().startswith(f"{env_key}="):
                lines[i] = f"{env_key}={api_key}\n"
                found = True
                break
        if not found:
            lines.append(f"{env_key}={api_key}\n")
        write_atomic(env_path, "".join(lines))

        # 热生效
        os.environ[env_key] = api_key
        engine_cache.pop("_llm", None)

        models = cfg.get("models", [])
        return ok(rid, {"provider": {
            "name": cfg.get("name", slug),
            "slug": slug,
            "auth_type": "api_key",
            "authenticated": True,
            "is_current": os.environ.get("BOBO_PROVIDER", "") == slug,
            "key_env": env_key,
            "models": models,
            "total_models": len(models),
            "warning": "",
        }})
    except Exception as e:
        return ok(rid, {"ok": False, "error": str(e)})


def handle_model_disconnect(params: dict, rid: str, engine_cache: dict) -> dict:
    """移除 provider 的 API key（从 .env 中删除）。"""
    slug = params.get("slug", "")
    if not slug:
        return ok(rid, {"disconnected": False})

    from core.provider import PROVIDERS
    cfg = PROVIDERS.get(slug)
    if not cfg:
        return ok(rid, {"disconnected": False})

    env_key = cfg.get("env_key", "")
    if not env_key:
        return ok(rid, {"disconnected": True})

    env_path = str(BOBO_DATA_DIR / ".env")
    try:
        lines = []
        if os.path.exists(env_path):
            with open(env_path) as f:
                lines = f.readlines()
        lines = [l for l in lines if not l.strip().startswith(f"{env_key}=")]
        write_atomic(env_path, "".join(lines))

        # 清理环境变量和缓存
        os.environ.pop(env_key, None)
        engine_cache.pop("_llm", None)

        return ok(rid, {"disconnected": True})
    except Exception as e:
        return ok(rid, {"disconnected": False, "error": str(e)})


# ── 注册 ──

def register(reg_method, ctx):
    """注册所有 model handler。

    Args:
        reg_method: 方法注册函数（method 装饰器）
        ctx: _ServerContext 实例
    """
    engine_cache = ctx.engine_cache
    reg_method("model.options")(handle_model_options)
    reg_method("model.save_key")(lambda params, rid: handle_model_save_key(params, rid, engine_cache))
    reg_method("model.disconnect")(lambda params, rid: handle_model_disconnect(params, rid, engine_cache))
