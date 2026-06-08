#!/usr/bin/env python3
"""
测试 15: 长时间运行 - 内存泄漏检测
"""

import sys
import os
import time
import psutil


from core.engine import Engine
from core.tool_executor import execute_tool
from core.llm_caller import create_llm_caller
from config import API_KEY, API_BASE_URL, API_MODEL_NAME
from tools import TOOLS_SCHEMA

def get_memory_usage():
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / 1024 / 1024  # MB

print("长时间运行测试 (模拟连续10个请求)")
print("=" * 50)

llm = create_llm_caller(API_KEY, API_BASE_URL, API_MODEL_NAME, TOOLS_SCHEMA)
engine = Engine(llm, execute_tool)

queries = [
    "你好",
    "现在几点了",
    "1+1等于几",
    "用一句话介绍Python",
    "什么是AI",
    "今天天气怎么样",
    "列出当前目录",
    "搜索Python教程",
    "写一个hello world",
    "再见"
]

mem_before = get_memory_usage()
print(f"初始内存: {mem_before:.1f} MB")

for i, query in enumerate(queries, 1):
    engine.run(query)
    time.sleep(0.5)
    if i % 5 == 0:
        current_mem = get_memory_usage()
        print(f"  第 {i} 个请求后内存: {current_mem:.1f} MB (增长: {current_mem - mem_before:.1f} MB)")

mem_after = get_memory_usage()
print(f"\n最终内存: {mem_after:.1f} MB")
print(f"总增长: {mem_after - mem_before:.1f} MB")

if mem_after - mem_before < 50:
    print("✅ 测试通过：无明显内存泄漏")
else:
    print("❌ 测试失败：可能存在内存泄漏")
