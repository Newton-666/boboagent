import sys
import os
import json
import requests

from core.llm_caller import create_llm_caller
from config import API_KEY, API_BASE_URL, API_MODEL_NAME
from tools import TOOLS_SCHEMA

print(f"API_KEY: {API_KEY[:10]}...")
print(f"API_BASE_URL: {API_BASE_URL}")
print(f"API_MODEL_NAME: {API_MODEL_NAME}")

# 手动构造请求
payload = {
    "model": API_MODEL_NAME,
    "messages": [{"role": "user", "content": "你好"}],
    "temperature": 0.3,
    "max_tokens": 8192,
}

headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {API_KEY}"
}

print("\n发送请求...")
response = requests.post(API_BASE_URL, json=payload, headers=headers)
print(f"状态码: {response.status_code}")
print(f"响应: {response.text[:200]}")
