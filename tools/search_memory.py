"""搜索长期记忆"""

TOOL_NAME = "search_memory"

def execute(query: str) -> str:
    from .v5_memory import search_knowledge_base
    return search_knowledge_base(query)

TOOL_FUNC = execute
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": """【用途】在长期记忆库中搜索之前保存的信息。
【适用场景】用户问"还记得XX吗"、"我之前让你记住的XX是什么"。""",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}
    }
}
def register(reg): reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA)
