"""抓取网页并转换为 Markdown（委托给 crawler.py）"""

TOOL_NAME = "web_extract"

def execute(url: str) -> str:
    from .crawler import web_fetch_markdown
    return web_fetch_markdown(url)

TOOL_FUNC = execute
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": "抓取网页内容并转换为 Markdown 格式，便于保存到笔记。适用场景：用户要求'把这个网页保存到笔记'、'提取文章内容'。",
        "parameters": {"type": "object", "properties": {"url": {"type": "string", "description": "要提取内容的网页 URL"}}, "required": ["url"]}
    }
}
def register(reg): reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA)
