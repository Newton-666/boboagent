#!/usr/bin/env python3
"""测试搜索优先级 - 知识性问题 vs 时效性问题"""

import sys
import time

from display import Display
from core.llm_caller import create_llm_caller
from core.engine import Engine
from core.tool_executor import execute_tool
from config import API_KEY, API_BASE_URL, API_MODEL_NAME
from tools import TOOLS_SCHEMA

display = Display()
tool_calls_log = []

_original_execute = execute_tool

def execute_with_log(tool_name, arguments):
    tool_calls_log.append(tool_name)
    display.show_tool(tool_name, "running")
    start = time.time()
    result = _original_execute(tool_name, arguments)
    elapsed = time.time() - start
    is_success = not result.startswith("❌")
    status = "done" if is_success else "error"
    display.show_tool(tool_name, status)
    return result

def create_engine():
    llm_caller = create_llm_caller(API_KEY, API_BASE_URL, API_MODEL_NAME, TOOLS_SCHEMA)
    return Engine(llm_caller, execute_with_log)

def clear_log():
    global tool_calls_log
    tool_calls_log = []

print("=" * 60)
print("测试搜索优先级")
print("=" * 60)

engine = create_engine()

# 测试1：时效性问题（应该直接联网）
print("\n📝 测试1: 时效性问题 - '量子计算最新进展'")
print("-" * 40)
clear_log()
result1 = engine.run("量子计算最新进展")
print(f"调用的工具: {tool_calls_log}")
print(f"是否直接联网: {'web_search' in tool_calls_log}")
print(f"回复预览: {result1[:150]}...")

# 重置引擎
engine.reset()
clear_log()

# 测试2：知识性问题（应该先搜 Obsidian）
print("\n" + "=" * 60)
print("\n📝 测试2: 知识性问题 - 'Python是什么'")
print("-" * 40)
result2 = engine.run("Python是什么")
print(f"调用的工具: {tool_calls_log}")
print(f"是否先搜 Obsidian: {'search_obsidian' in tool_calls_log}")
print(f"回复预览: {result2[:150]}...")

print("\n" + "=" * 60)
print("测试完成")
print("=" * 60)
