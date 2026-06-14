"""打开 URL 工具"""

import subprocess

TOOL_NAME = "open_url"

def execute(url: str) -> str:
    """在浏览器中打开 URL"""
    try:
        subprocess.run(['open', url], capture_output=True)
        return f"✅ 已在浏览器中打开: {url}"
    except Exception:
        return f"❌ 无法打开: {url}"

def register(reg):
    reg("open_url", execute, {
        "type": "function",
        "function": {
            "name": "open_url",
            "description": "在默认浏览器中打开网址。适用场景：用户要求'打开这个链接'、'访问这个网站'。",
            "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}
        }
    })
