"""Configure Notion integration with an API key."""

import os
from config import BOBO_DATA_DIR
import re

TOOL_NAME = "notion_setup"


def execute(api_key: str) -> str:
    """Save a Notion API key and verify it works."""
    if not api_key or len(api_key) < 10:
        return "Notion API Key 无效，请在 https://www.notion.so/my-integrations 创建"

    env_path = str(BOBO_DATA_DIR / ".env")
    os.makedirs(os.path.dirname(env_path), exist_ok=True)

    try:
        if os.path.exists(env_path):
            with open(env_path, "r") as f:
                content = f.read()
            pattern = r"^NOTION_API_KEY=.*$"
            if re.search(pattern, content, re.MULTILINE):
                content = re.sub(pattern, f"NOTION_API_KEY={api_key}", content, flags=re.MULTILINE)
            else:
                content += f"\nNOTION_API_KEY={api_key}"
            with open(env_path, "w") as f:
                f.write(content)
        else:
            with open(env_path, "w") as f:
                f.write(f"NOTION_API_KEY={api_key}\n")
    except Exception as e:
        return f"保存失败: {str(e)}"

    # Test the key
    import requests
    try:
        resp = requests.get(
            "https://api.notion.com/v1/users/me",
            headers={"Authorization": f"Bearer {api_key}", "Notion-Version": "2022-06-28"},
            timeout=10,
        )
        if resp.status_code == 200:
            name = resp.json().get("name", "")
            return f"Notion 已连接 ({name})。可以搜索页面、读取内容、创建新页面。"
        return f"API Key 无效 (HTTP {resp.status_code})"
    except requests.exceptions.RequestException as e:
        return f"连接失败: {str(e)}"


TOOL_FUNC = execute
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": "配置 Notion 集成。提供 Notion Integration Token，Bobo 会保存并验证。",
        "parameters": {
            "type": "object",
            "properties": {
                "api_key": {
                    "type": "string",
                    "description": "Notion Integration Token，在 https://www.notion.so/my-integrations 创建"
                }
            },
            "required": ["api_key"]
        }
    }
}


def register(reg):
    reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA)
