#!/usr/bin/env python3
"""测试完整流程：LLM -> 工具 -> LLM -> 最终答案"""

import sys
import os
import json
import time


from core.llm_caller import create_llm_caller
from core.tool_executor import execute_tool
from config import API_KEY, API_BASE_URL, API_MODEL_NAME
from tools import TOOLS_SCHEMA

def debug_callback(event_type, data):
    print(f"[DEBUG] {event_type}: {list(data.keys()) if isinstance(data, dict) else data}")

llm = create_llm_caller(API_KEY, API_BASE_URL, API_MODEL_NAME, TOOLS_SCHEMA)

# 手动模拟完整流程
messages = [
    {"role": "system", "content": "你是Bobo，专业助手。需要时调用工具。"},
    {"role": "user", "content": "明天早晨乘坐G532去北京，列出出行计划"}
]

print("=== 第一次 LLM 调用 ===")
response1 = llm(messages, use_tools=True)
print(f"响应1: {response1.get('choices', [{}])[0].get('message', {}).get('content', '')[:100]}")
tool_calls = response1.get('choices', [{}])[0].get('message', {}).get('tool_calls', [])
print(f"工具调用: {[tc.get('function', {}).get('name') for tc in tool_calls]}")

if tool_calls:
    # 执行工具
    tool_results = []
    for tc in tool_calls:
        tool_name = tc.get('function', {}).get('name')
        args_str = tc.get('function', {}).get('arguments', '{}')
        args = json.loads(args_str)
        print(f"\n执行工具: {tool_name}({args})")
        result = execute_tool(tool_name, args)
        tool_results.append({
            "tool_call_id": tc.get('id'),
            "role": "tool",
            "content": result
        })
    
    # 第二次调用 LLM
    messages.append(response1['choices'][0]['message'])
    messages.extend(tool_results)
    
    print("\n=== 第二次 LLM 调用 ===")
    response2 = llm(messages, use_tools=False)
    content2 = response2.get('choices', [{}])[0].get('message', {}).get('content', '')
    print(f"最终答案:\n{content2}")
else:
    print("没有工具调用")
