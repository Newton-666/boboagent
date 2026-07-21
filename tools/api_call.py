"""Call a registered custom API endpoint."""

import json
from config import BOBO_DATA_DIR
import os
import requests

TOOL_NAME = "api_call"


def execute(api: str, endpoint: str, params: str = "", body: str = "") -> str:
    """Call a registered API endpoint with optional params/body."""
    # Load the API config
    path = os.path.expanduser(f"{BOBO_DATA_DIR}/apis/{api}.json")
    if not os.path.exists(path):
        available = _list_apis()
        hint = f"\n已注册的 API: {', '.join(available)}" if available else ""
        return f"API '{api}' 未注册，请先用 api_register 注册{hint}"

    with open(path, "r") as f:
        config = json.load(f)

    # Find the endpoint
    endpoint_def = None
    for ep in config.get("endpoints", []):
        if ep.get("name") == endpoint:
            endpoint_def = ep
            break
    if not endpoint_def:
        names = [ep.get("name", "?") for ep in config.get("endpoints", [])]
        return f"端点 '{endpoint}' 不存在。可用端点: {', '.join(names)}"

    # Build URL with path params
    base_url = config["base_url"].rstrip("/")
    path_template = endpoint_def.get("path", "/")
    method = endpoint_def.get("method", "GET").upper()

    # Parse and substitute params
    try:
        parsed_params = json.loads(params) if params else {}
    except json.JSONDecodeError:
        return f"params JSON 解析失败: {params}"

    url_path = path_template
    if parsed_params:
        for k, v in parsed_params.items():
            placeholder = "{" + k + "}"
            if placeholder in url_path:
                url_path = url_path.replace(placeholder, str(v))

    url = base_url + url_path

    # Build headers
    headers = {"Content-Type": "application/json"}
    auth_type = config.get("auth_type", "")
    auth_key = config.get("auth_key", "")
    if auth_type == "bearer" and auth_key:
        headers["Authorization"] = f"Bearer {auth_key}"
    elif auth_type == "header" and auth_key:
        headers["X-API-Key"] = auth_key

    # Parse body
    try:
        parsed_body = json.loads(body) if body else None
    except json.JSONDecodeError:
        return f"body JSON 解析失败: {body}"

    # Make request
    try:
        if method == "GET":
            resp = requests.get(url, headers=headers, params=parsed_params if parsed_params else None, timeout=15)
        elif method == "POST":
            resp = requests.post(url, headers=headers, json=parsed_body, timeout=15)
        elif method == "PUT":
            resp = requests.put(url, headers=headers, json=parsed_body, timeout=15)
        elif method == "DELETE":
            resp = requests.delete(url, headers=headers, timeout=15)
        else:
            return f"不支持的 HTTP 方法: {method}"

        result = resp.text[:4000]
        if resp.status_code >= 400:
            return f"API 返回错误 (HTTP {resp.status_code}): {result}"
        return result

    except requests.exceptions.RequestException as e:
        return f"请求失败: {str(e)}"


def _list_apis() -> list:
    apis_dir = str(BOBO_DATA_DIR / "apis")
    if not os.path.exists(apis_dir):
        return []
    return sorted(
        f.replace(".json", "")
        for f in os.listdir(apis_dir)
        if f.endswith(".json")
    )


TOOL_FUNC = execute
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": (
            "调用一个之前通过 api_register 注册的自定义 API 端点。"
            "自动处理认证和 URL 参数替换。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "api": {"type": "string", "description": "API 名称（与 api_register 时一致）"},
                "endpoint": {"type": "string", "description": "端点名称（注册时定义的 name）"},
                "params": {"type": "string", "description": "JSON 对象，路径参数/查询参数"},
                "body": {"type": "string", "description": "JSON 字符串，POST/PUT 请求体"},
            },
            "required": ["api", "endpoint"]
        }
    }
}

def register(reg):
    reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA)
