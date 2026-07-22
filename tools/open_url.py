"""打开 URL 工具"""

import subprocess

TOOL_NAME = "open_url"

def execute(url: str) -> str:
    """在浏览器中打开 URL"""
    try:
        result = subprocess.run(['open', url], capture_output=True, timeout=15)
        if result.returncode != 0:
            return f"❌ 打开失败（open 返回 {result.returncode}）: {url}"
        return f"✅ 已在浏览器中打开: {url}"
    except subprocess.TimeoutExpired:
        return f"❌ 打开超时: {url}"
    except FileNotFoundError:
        return "❌ open 命令不可用（非 macOS 系统）"
    except Exception as e:
        return f"❌ 无法打开: {e}"

def register(reg):
    reg("open_url", execute, {
        "type": "function",
        "function": {
            "name": "open_url",
            "description": "在默认浏览器中打开网址。适用场景：用户要求'打开这个链接'、'访问这个网站'。",
            "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}
        }
    })
