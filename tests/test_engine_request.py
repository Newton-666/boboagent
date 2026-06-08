import sys
import os
import json
import requests

from core.engine import Engine
from core.tool_executor import execute_tool
from core.llm_caller import create_llm_caller
from config import API_KEY, API_BASE_URL, API_MODEL_NAME
from tools import TOOLS_SCHEMA

# 直接调用 llm_caller 看请求
def debug_llm_caller(messages):
    payload = {
        "model": API_MODEL_NAME,
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": 8192,
    }
    if TOOLS_SCHEMA:
        payload["tools"] = TOOLS_SCHEMA
        payload["tool_choice"] = "auto"
    
    print(f"\n[DEBUG] 请求 payload (部分):")
    print(f"  model: {payload['model']}")
    print(f"  messages 数量: {len(payload['messages'])}")
    print(f"  has tools: {'tools' in payload}")
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }
    
    response = requests.post(API_BASE_URL, json=payload, headers=headers)
    print(f"  状态码: {response.status_code}")
    if response.status_code != 200:
        print(f"  错误: {response.text[:300]}")
    
    return response.json()

# 测试
messages = [
    {"role": "system", "content": "你是助手"},
    {"role": "user", "content": "你好"}
]

print("测试 llm_caller with tools...")
result = debug_llm_caller(messages)
print(f"结果: {result.get('choices', [{}])[0].get('message', {}).get('content', '')[:50]}")
