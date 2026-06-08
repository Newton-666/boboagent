#!/usr/bin/env python3
"""测试正确的工具调用格式"""

import sys
import json

from core.llm_caller import create_llm_caller
from config import API_KEY, API_BASE_URL, API_MODEL_NAME
from tools import TOOLS_SCHEMA

print("初始化...")
llm = create_llm_caller(API_KEY, API_BASE_URL, API_MODEL_NAME, TOOLS_SCHEMA)

# 方式1: 标准 OpenAI 格式
messages = [
    {"role": "system", "content": "你是助手，根据搜索结果回答。"},
    {"role": "user", "content": "搜索AI"},
    {"role": "assistant", "content": "", "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "web_search", "arguments": "{\"query\": \"AI\"}"}}]},
    {"role": "tool", "tool_call_id": "call_1", "content": "搜索结果：AI是人工智能"}
]

print("\n方式1 (content为空字符串):")
response1 = llm(messages)
content1 = response1.get("choices", [{}])[0].get("message", {}).get("content", "")
print(f"内容: {content1[:100] if content1 else '空'}")

# 方式2: content 用空字符串但去掉
messages2 = [
    {"role": "system", "content": "你是助手，根据搜索结果回答。"},
    {"role": "user", "content": "搜索AI"},
    {"role": "assistant", "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "web_search", "arguments": "{\"query\": \"AI\"}"}}]},
    {"role": "tool", "tool_call_id": "call_1", "content": "搜索结果：AI是人工智能"}
]

print("\n方式2 (无content字段):")
response2 = llm(messages2)
content2 = response2.get("choices", [{}])[0].get("message", {}).get("content", "")
print(f"内容: {content2[:100] if content2 else '空'}")

# 方式3: 使用 tool_calls 后直接问
messages3 = [
    {"role": "system", "content": "你是助手。"},
    {"role": "user", "content": "根据搜索结果：AI是人工智能，请总结。"}
]

print("\n方式3 (直接问):")
response3 = llm(messages3)
content3 = response3.get("choices", [{}])[0].get("message", {}).get("content", "")
print(f"内容: {content3[:100] if content3 else '空'}")
