#!/usr/bin/env python3
"""简单测试工具调用"""

import sys
import json

from core.llm_caller import create_llm_caller
from config import API_KEY, API_BASE_URL, API_MODEL_NAME
from tools import TOOLS_SCHEMA

print("初始化...")
llm = create_llm_caller(API_KEY, API_BASE_URL, API_MODEL_NAME, TOOLS_SCHEMA)

# 模拟工具调用后的消息
messages = [
    {"role": "system", "content": "你是助手，根据搜索结果回答。"},
    {"role": "user", "content": "搜索AI"},
    {"role": "assistant", "content": None, "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "web_search", "arguments": "{\"query\": \"AI\"}"}}]},
    {"role": "tool", "tool_call_id": "call_1", "content": "搜索结果：AI是人工智能"}
]

print("消息:", json.dumps(messages, ensure_ascii=False, indent=2)[:500])
print("\n调用 LLM...")
response = llm(messages)
print("响应类型:", type(response))

if isinstance(response, dict):
    content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
    print(f"内容: {content}")
else:
    print(f"响应: {response}")
