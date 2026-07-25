"""View or change Bobo's configuration (provider, model, API key)."""

import os
import re

TOOL_NAME = "bobo_config"


def execute(action: str = "view", key: str = "", value: str = "") -> str:
    """View or modify Bobo configuration."""
    from config import BOBO_DATA_DIR
    env_path = str(BOBO_DATA_DIR / ".env")

    if action == "view":
        # Read current config from environment
        provider = os.environ.get("BOBO_PROVIDER", "deepseek")
        model = os.environ.get("API_MODEL_NAME", "")
        if not model:
            from core.provider import resolve_provider
            cfg = resolve_provider(provider)
            model = cfg.get("model", "")
        key_status = "已配置" if os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY") else "未配置"
        return (
            f"Bobo 当前配置:\n"
            f"  提供商: {provider}\n"
            f"  模型: {model}\n"
            f"  API Key: {key_status}\n"
            f"  Obsidian: {'已连接' if os.environ.get('OBSIDIAN_VAULT') else '未配置'}\n"
            f"  Notion: {'已连接' if os.environ.get('NOTION_API_KEY') else '未配置'}\n"
            f"  GitHub: {'已连接' if os.environ.get('GITHUB_TOKEN') else '未配置'}\n"
            f"\n要修改配置，可以说:\n"
            f"  \"切换到 OpenAI\"\n"
            f"  \"使用 gpt-4o 模型\"\n"
            f"  \"配置 Notion API\"\n"
        )

    if action == "set":
        if not key or not value:
            return "请提供 key 和 value"

        try:
            if os.path.exists(env_path):
                with open(env_path) as f:
                    content = f.read()
                found = False
                for line in content.split("\n"):
                    if line.startswith(key + "="):
                        content = content.replace(line, key + "=" + value)
                        found = True
                        break
                if not found:
                    content += "\n" + key + "=" + value + "\n"
            else:
                os.makedirs(os.path.dirname(env_path), exist_ok=True)
                content = key + "=" + value + "\n"

            with open(env_path, "w") as f:
                f.write(content)

            # Update env for current process
            os.environ[key] = value
            return f"已更新: {key}={value[:8]}..."
        except Exception as e:
            return f"更新失败: {str(e)}"

    return "支持的操作: view (查看), set (修改)"


TOOL_FUNC = execute
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": "查看或修改 Bobo 的配置。action='view' 查看当前配置。action='set' 设置配置项，key 为环境变量名（如 BOBO_PROVIDER, API_MODEL_NAME），value 为值。",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "description": "操作: 'view' 或 'set'"},
                "key": {"type": "string", "description": "环境变量名，如 BOBO_PROVIDER, API_MODEL_NAME, DEEPSEEK_API_KEY"},
                "value": {"type": "string", "description": "要设置的值（action=set 时需要）"}
            },
            "required": ["action"]
        }
    }
}


def register(reg):
    reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA)
