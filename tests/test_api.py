import sys
import os
import json

from core.llm_caller import create_llm_caller
from config import API_KEY, API_BASE_URL, API_MODEL_NAME
from tools import TOOLS_SCHEMA

llm = create_llm_caller(API_KEY, API_BASE_URL, API_MODEL_NAME, TOOLS_SCHEMA)

# 测试简单消息
messages = [{"role": "user", "content": "你好"}]
print("请求 messages:", json.dumps(messages, ensure_ascii=False))

response = llm(messages)
print("响应:", response)

# 测试带 system prompt 的消息
messages2 = [
    {"role": "system", "content": "你是助手"},
    {"role": "user", "content": "你好"}
]
print("\n请求 messages2:", json.dumps(messages2, ensure_ascii=False))
response2 = llm(messages2)
print("响应2:", response2)
