"""浏览器自动化工具 - 纯 Python 实现"""

import subprocess
import time
from typing import Optional

TOOL_NAME_PREFIX = "browser_"


def open_url(url: str) -> str:
    """在浏览器中打开 URL"""
    try:
        subprocess.run(["open", url], capture_output=True)
        return f"✅ 已在浏览器中打开: {url}"
    except Exception as e:
        return f"❌ 打开失败: {e}"


def get_page_title(url: str, timeout: int = 10) -> str:
    """获取网页标题"""
    try:
        import requests
        from bs4 import BeautifulSoup
        resp = requests.get(url, timeout=timeout, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })
        soup = BeautifulSoup(resp.text, 'html.parser')
        title = soup.find('title')
        return title.get_text().strip() if title else "无标题"
    except Exception as e:
        return f"❌ 获取失败: {e}"


def register(reg):
    reg("browser_open", open_url, {
        "type": "function",
        "function": {
            "name": "browser_open",
            "description": """【用途】在默认浏览器中打开网址。

【适用场景】用户想要：
- 打开一个网站（如"打开百度"、"打开 python.org"）
- 查看某个网页（如"帮我看看这个网站"）
- 访问链接（如"打开这个链接"）
- 任何涉及"打开网址"、"访问网站"、"浏览网页"的请求

【示例】"打开 https://www.python.org"、"帮我打开百度"、"访问那个链接"

【注意】需要完整的 URL（如 https://...），如果没有 http:// 会自动添加。""",
            "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}
        }
    })
    
    reg("browser_get_title", get_page_title, {
        "type": "function",
        "function": {
            "name": "browser_get_title",
            "description": """【用途】获取网页标题，不打开浏览器。

【适用场景】用户想要知道某个网页的标题是什么。

【示例】"看看 python.org 的标题是什么"、"这个网页叫什么名字"。

【注意】需要完整的 URL。""",
            "parameters": {"type": "object", "properties": {"url": {"type": "string"}, "timeout": {"type": "integer"}}, "required": ["url"]}
        }
    })
