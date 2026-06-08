"""保存到长期记忆"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TOOL_NAME = "save_memory"

def execute(content: str, memory_type: str = "knowledge") -> str:
    from tools.v5_memory import save_to_knowledge_base
    return save_to_knowledge_base(content, memory_type)

TOOL_FUNC = execute
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "save_memory",
        "description": """【用途】保存永久性知识到长期记忆库。

适用场景：
- 记住事实、知识点、偏好（如"我喜欢Python"）
- 不会过期的信息

不适用场景：
- 有时间限制的事情（如"明天开会"）→ 请用 set_reminder

示例：
- "记住我的邮箱是 xxx@example.com" → 保存到记忆
- "记住我喜欢喝咖啡" → 保存到记忆""",
        "parameters": {"type": "object", "properties": {
            "content": {"type": "string"},
            "memory_type": {"type": "string"}
        }, "required": ["content"]}
    }
}
def register(reg): reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA)
