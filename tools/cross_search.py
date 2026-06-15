"""Search across all configured platforms (Obsidian, Notion, email) for a keyword."""

TOOL_NAME = "cross_search"

TOOL_FUNC = None  # handled by engine

TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": (
            "跨平台统一搜索——在 Obsidian、Notion、Email 中同时搜索，"
            "返回按时间排列的统一时间线，自动去重。"
            "能看到一条主题在不同平台上的完整轨迹。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词"}
            },
            "required": ["query"]
        }
    }
}

def register(reg):
    reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA)
