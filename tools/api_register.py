"""Register a custom API endpoint so Bobo can call it without writing Python code."""

import json
import os
import re

TOOL_NAME = "api_register"

# API 名称将拼进文件路径 ~/.bobo/apis/{name}.json，必须严格限制字符集
_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")


def execute(name: str, base_url: str, auth_type: str = "",
            auth_key: str = "", endpoints: str = "") -> str:
    """Register a custom API. Provide base URL, auth, and endpoint definitions."""
    if not name or not base_url:
        return "需要提供 API 名称和 base_url"

    if not _NAME_PATTERN.match(name):
        return "❌ API 名称只能包含字母、数字、下划线和连字符（最长 64 字符）"

    # Parse endpoints from JSON string
    try:
        parsed_endpoints = json.loads(endpoints) if endpoints else []
    except json.JSONDecodeError as e:
        return f"endpoints JSON 解析失败: {e}"

    if not isinstance(parsed_endpoints, list):
        return "endpoints 必须是 JSON 数组"

    config = {
        "name": name,
        "base_url": base_url.rstrip("/"),
        "auth_type": auth_type,  # "bearer", "header", ""
        "auth_key": auth_key,
        "endpoints": parsed_endpoints,
    }

    # Save to ~/.bobo/apis/{name}.json
    apis_dir = os.path.expanduser("~/.bobo/apis")
    os.makedirs(apis_dir, exist_ok=True)
    path = os.path.join(apis_dir, f"{name}.json")

    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        ep_count = len(parsed_endpoints)
        return (
            f"API '{name}' 已注册 ({ep_count} 个端点)\n"
            f"base_url: {base_url}\n"
            f"配置文件: {path}\n\n"
            f"现在可以使用 api_call 调用，例如:\n"
            f"  api_call(api=\"{name}\", endpoint=\"search\", params={{\"query\": \"...\"}})"
        )
    except Exception as e:
        return f"保存失败: {str(e)}"


TOOL_FUNC = execute
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": (
            "注册一个自定义 API 服务。提供 base URL、认证方式、"
            "和若干端点的定义，无需编写 Python 代码。"
            "之后可以用 api_call 工具调用这些端点。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "API 名称（如 'my-notes', 'jira'），用于后续 api_call 调用"
                },
                "base_url": {
                    "type": "string",
                    "description": "API 基础 URL（如 'https://api.github.com'）"
                },
                "auth_type": {
                    "type": "string",
                    "description": "认证方式: 'bearer'（Bearer Token）, 'header'（自定义请求头）, ''（无认证）"
                },
                "auth_key": {
                    "type": "string",
                    "description": "认证密钥（Bearer Token 或请求头值）"
                },
                "endpoints": {
                    "type": "string",
                    "description": (
                        "JSON 数组，每个元素定义: "
                        "{\"name\": \"search\", \"method\": \"GET\", \"path\": \"/notes?q={query}\"}"
                    )
                }
            },
            "required": ["name", "base_url"]
        }
    }
}

def register(reg):
    reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA)
