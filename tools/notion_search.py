"""Search Notion pages by title or content."""

import os
import requests

TOOL_NAME = "notion_search"

_check = lambda: bool(os.environ.get("NOTION_API_KEY", ""))

HEADERS = {"Notion-Version": "2022-06-28"}


def execute(query: str, limit: int = 10) -> str:
    """Search Notion pages by keyword."""
    api_key = os.environ.get("NOTION_API_KEY", "")
    if not api_key:
        return "Notion 未配置，请先运行 notion_setup"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        **HEADERS,
    }

    payload = {
        "query": query,
        "page_size": min(limit, 20),
    }

    try:
        resp = requests.post(
            "https://api.notion.com/v1/search",
            json=payload,
            headers=headers,
            timeout=15,
        )
        if resp.status_code != 200:
            return f"搜索失败 (HTTP {resp.status_code})"

        data = resp.json()
        results = data.get("results", [])
        if not results:
            return f"没有找到包含 '{query}' 的页面"

        lines = [f"找到 {len(results)} 个页面:"]
        for page in results:
            props = page.get("properties", {})
            title = "未命名"
            for prop in props.values():
                if prop.get("type") == "title":
                    title_parts = prop.get("title", [])
                    if title_parts:
                        title = "".join(t.get("plain_text", "") for t in title_parts)
                    break
            url = page.get("url", "")
            page_type = page.get("object", "page")
            edited = page.get("last_edited_time", "")[:10]  # YYYY-MM-DD
            date_info = f" ({edited})" if edited else ""
            lines.append(f"  {title}{date_info} ({page_type})")
            if url:
                lines.append(f"    {url}")

        return "\n".join(lines)

    except requests.exceptions.RequestException as e:
        return f"连接失败: {str(e)}"


TOOL_FUNC = execute
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": "在 Notion 中搜索页面和数据库。需要先通过 notion_setup 配置 API Key。",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词"},
                "limit": {"type": "integer", "description": "返回结果数（最多 20）"},
            },
            "required": ["query"],
        },
    },
}


def register(reg):
    reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA, check_fn=_check)
