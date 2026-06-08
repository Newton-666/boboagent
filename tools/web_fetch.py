"""获取网页完整内容"""

TOOL_NAME = "web_fetch"

def execute(url: str) -> str:
    from .crawler import web_fetch
    return web_fetch(url)

TOOL_FUNC = execute
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": """【用途】获取指定网址的完整网页文本内容。
【适用场景】用户提供了链接并要求"看看这篇文章"、"抓取这个网页"、"读取这个页面"。
【注意】需要用户提供完整 URL。""",
        "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}
    }
}
def register(reg): reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA)
