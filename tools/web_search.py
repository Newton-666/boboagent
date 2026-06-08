"""DuckDuckGo 网页搜索"""

TOOL_NAME = "web_search"

def execute(query: str) -> str:
    from .crawler import web_search
    return web_search(query)

TOOL_FUNC = execute
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": """【用途】使用 DuckDuckGo 搜索引擎在互联网上搜索最新信息。
【适用场景】用户要求"搜索XX"、"查一下XX"、"网上怎么说"、"最新消息"、"XX是什么"。
【返回】标题、摘要和链接列表。""",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}
    }
}
def register(reg): reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA)
