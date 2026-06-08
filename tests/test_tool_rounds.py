#!/usr/bin/env python3
"""
测试 11: 工具调用轮数限制
验证超过5轮会停止
"""

import sys
import os
import time


from core.engine import Engine
from core.tool_executor import execute_tool
from core.llm_caller import create_llm_caller
from config import API_KEY, API_BASE_URL, API_MODEL_NAME
from tools import TOOLS_SCHEMA

rounds_used = 0

def callback(event_type, data):
    global rounds_used
    if event_type == "tool_call":
        rounds_used += 1
        print(f"  🔧 第 {rounds_used} 轮工具调用")
    elif event_type == "error":
        print(f"  ❌ 错误: {data.get('content', '')}")
    elif event_type == "complete":
        print(f"  ✅ 完成")

llm = create_llm_caller(API_KEY, API_BASE_URL, API_MODEL_NAME, TOOLS_SCHEMA)
engine = Engine(llm, execute_tool, callback=callback)

# 一个可能触发多轮工具调用的问题
query = "帮我查一下今天天气，然后搜索Python教程，再查一下当前时间，然后搜索AI新闻，再列一下当前目录"
print(f"查询: {query}\n")
engine.run(query)
print(f"\n总工具调用轮数: {rounds_used}")
if rounds_used <= 5:
    print("✅ 测试通过：工具调用轮数在限制内")
else:
    print("❌ 测试失败：工具调用轮数超过限制")
