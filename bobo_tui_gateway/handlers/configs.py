"""handlers/configs.py — 配置相关 handler（setup 状态/提交、配置读取/写入/全量）。"""

import os
import re
from pathlib import Path

from bobo_tui_gateway.server_utils import ok, err, write_atomic
import config as _cfg

# 由 register() 注入，供 handle_config_set 访问 server 的 engine_cache
_engine_cache = None


def handle_setup_status(params: dict, rid: str) -> dict:
    return ok(rid, {
        "provider_configured": bool(_cfg.API_KEY),
        "provider": _cfg.ACTIVE_PROVIDER,
        # COST-3：providers 下拉（qwen = 阿里云百炼官方接入，2026-08）
        "providers": ["deepseek", "openai", "anthropic", "openrouter", "google", "ollama", "qwen", "custom"],
    })


def handle_setup_submit(params: dict, rid: str) -> dict:
    """保存用户通过 TUI 设置表单提交的 API Key。"""
    provider = params.get("provider", "deepseek")
    api_key = params.get("api_key", "").strip()
    if not api_key:
        return ok(rid, {"ok": False, "error": "API Key 不能为空"})

    env_path = str(_cfg.BOBO_DATA_DIR / ".env")
    os.makedirs(os.path.dirname(env_path), exist_ok=True)

    from core.provider import get_provider
    provider_cfg = get_provider(provider)
    if not provider_cfg:
        return ok(rid, {"ok": False, "error": f"不支持的提供商: {provider}"})

    env_key = provider_cfg.get("env_key", "")
    if not env_key:
        return ok(rid, {"ok": False, "error": f"{provider} 不需要 API Key（如 Ollama）"})

    # 写入 .env 文件
    try:
        key_eq = env_key + "="
        if os.path.exists(env_path):
            with open(env_path) as f:
                content = f.read()
            found = False
            for line in content.split("\n"):
                if line.startswith(key_eq):
                    content = content.replace(line, key_eq + api_key)
                    found = True
                    break
            if not found:
                content += "\n" + key_eq + api_key
        else:
            content = key_eq + api_key + "\n"
        if provider != "deepseek":
            prov_line = "BOBO_PROVIDER="
            found = False
            for line in content.split("\n"):
                if line.startswith(prov_line):
                    content = content.replace(line, prov_line + provider)
                    found = True
                    break
            if not found:
                content += "\n" + prov_line + provider
        write_atomic(env_path, content)
        # TICKET-D1b B3: 写 .env 后同步刷新 os.environ + config 缓存（热生效，禁止重启）
        os.environ[env_key] = api_key
        if provider != "deepseek":
            os.environ["BOBO_PROVIDER"] = provider
        _cfg.refresh_config_cache()
        return ok(rid, {"ok": True, "message": f"{provider} 已配置", "provider_configured": True})
    except Exception as e:
        return ok(rid, {"ok": False, "error": str(e)})


def handle_config_get(params: dict, rid: str) -> dict:
    """config.get 分派：key=full → 全量配置（前端 useConfigSync/createGatewayEventHandler
    以 config.get {key:'full'} 拉取 ConfigFullResponse，契约见 gatewayTypes.ts）；
    key=mtime → .env 文件 mtime（驱动前端 mtime 轮询，配置热改后触发重新同步）；
    其余 key → 单值（model 等，保持旧行为）。

    TICKET-QWEN-THINKING：此前只返回 {"value": model}，key=full 落到空串 →
    前端 applyDisplay 读到 cfg.config 缺失 → showReasoning 恒为 false →
    recordReasoningDelta 门控丢弃全部 thinking（Qwen/DeepSeek/Kimi 思考过程一律不显示）。
    """
    key = params.get("key", "")
    if key == "full":
        return handle_config_full(params, rid)
    if key == "mtime":
        try:
            env_path = Path(_cfg.BOBO_DATA_DIR) / ".env"
            mt = int(env_path.stat().st_mtime) if env_path.exists() else 0
        except OSError:
            mt = 0
        return ok(rid, {"mtime": mt})
    values = {"model": _cfg.API_MODEL_NAME}
    return ok(rid, {"value": values.get(key, "")})


def handle_config_set(params: dict, rid: str) -> dict:
    key = params.get("key", "")
    value = params.get("value", "")
    if key == "model" and value:
        # 解析 value: "deepseek-reasoner" 或 "deepseek-reasoner --provider deepseek #tui"
        model_name = value.split("--provider")[0].strip()
        model_name = re.sub(r"\s+#tui\s*$", "", model_name).strip()
        # 写入 .env
        env_path = str(_cfg.BOBO_DATA_DIR / ".env")
        try:
            lines = []
            if os.path.exists(env_path):
                with open(env_path) as f:
                    lines = f.readlines()
            found = False
            for i, line in enumerate(lines):
                if line.strip().startswith("API_MODEL_NAME="):
                    lines[i] = f"API_MODEL_NAME={model_name}\n"
                    found = True
                    break
            if not found:
                lines.append(f"API_MODEL_NAME={model_name}\n")
            # 如果 value 中包含 --provider，也更新 BOBO_PROVIDER
            provider_match = re.search(r"--provider\s+(\S+)", value)
            if provider_match:
                prov = provider_match.group(1)
                found_p = False
                for i, line in enumerate(lines):
                    if line.strip().startswith("BOBO_PROVIDER="):
                        lines[i] = f"BOBO_PROVIDER={prov}\n"
                        found_p = True
                        break
                if not found_p:
                    lines.append(f"BOBO_PROVIDER={prov}\n")
            # 同步 provider 特定的默认参数到 .env + os.environ。
            # 新 provider 有默认值 → 写入；没有 → 移除旧值（防 sticky 温度/token 残留）。
            from core.provider import get_provider as _get_prov
            _active_prov = _get_prov(prov if provider_match else "deepseek")
            for _pkey, _envkey in [("temperature", "BOBO_TEMPERATURE"), ("max_tokens", "BOBO_MAX_TOKENS")]:
                _pval = _active_prov.get(_pkey) if _active_prov else None
                if _pval:
                    # 写入/更新
                    _found = False
                    for _i, _line in enumerate(lines):
                        if _line.strip().startswith(f"{_envkey}="):
                            lines[_i] = f"{_envkey}={_pval}\n"
                            _found = True
                            break
                    if not _found:
                        lines.append(f"{_envkey}={_pval}\n")
                    os.environ[_envkey] = str(_pval)
                else:
                    # 新 provider 无此默认 → 移除旧行 + 清理 os.environ
                    lines = [_l for _l in lines if not _l.strip().startswith(f"{_envkey}=")]
                    os.environ.pop(_envkey, None)
            write_atomic(env_path, "".join(lines))
            # 热生效：更新基础 env vars + 清缓存
            os.environ["API_MODEL_NAME"] = model_name
            if provider_match:
                os.environ["BOBO_PROVIDER"] = prov
            if _engine_cache is not None:
                _engine_cache.pop("_llm", None)  # 清除缓存的 LLM caller
            # 清除 config.py 的 provider 缓存（必须设为 None，空 dict 不触发重新解析）
            _cfg.refresh_config_cache()
            return ok(rid, {"value": model_name, "saved": True,
                             "note": "已生效，下一回合将使用新模型"})
        except Exception as e:
            return ok(rid, {"value": value, "error": str(e)})
    return ok(rid, {"value": value})


def handle_config_full(params: dict, rid: str) -> dict:
    return ok(rid, {
        "config": {
            "display": {
                "streaming": True,
                "show_reasoning": True,
                "tui_compact": False,
                "details_mode": "expanded",
            }
        }
    })


# ── 注册 ──

def register(reg_method, engine_cache=None):
    """注册所有 config handler。

    Args:
        reg_method: 方法注册函数（server.py 的 method 装饰器等价物）
        engine_cache: server 模块的 _engine_cache dict（供 handle_config_set 热刷新用）
    """
    global _engine_cache
    if engine_cache is not None:
        _engine_cache = engine_cache
    reg_method("setup.status")(handle_setup_status)
    reg_method("setup.submit")(handle_setup_submit)
    reg_method("config.get")(handle_config_get)
    reg_method("config.set")(handle_config_set)
    reg_method("config.full")(handle_config_full)
