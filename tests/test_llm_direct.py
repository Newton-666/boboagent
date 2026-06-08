import sys
import os

from core.llm_caller import create_llm_caller
from config import API_KEY, API_BASE_URL, API_MODEL_NAME

# 不传 tools_schema
llm = create_llm_caller(API_KEY, API_BASE_URL, API_MODEL_NAME, tools_schema=None)

prompt = "用一句话回答：1+1等于几？"
messages = [{"role": "user", "content": prompt}]

print("调用 LLM (无 tools)...")
response = llm(messages, use_tools=False)
print(f"响应类型: {type(response)}")

if isinstance(response, dict) and 'error' not in response:
    content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
    print(f"内容: {content}")
else:
    print(f"错误: {response}")
