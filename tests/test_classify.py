#!/usr/bin/env python3
"""测试智能分类 - 先分析给方案，确认后再移动"""

import sys
import time

from display import Display
from core.llm_caller import create_llm_caller
from core.engine import Engine
from core.tool_executor import execute_tool
from config import API_KEY, API_BASE_URL, API_MODEL_NAME
from tools import TOOLS_SCHEMA

display = Display()

_original_execute = execute_tool

def execute_with_display(tool_name, arguments):
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
    return Engine(llm_caller, execute_with_display)

print("=" * 60)
print("测试智能分类 - 分析 → 确认 → 移动")
print("=" * 60)

engine = create_engine()

# 第一步：分析
print("\n📝 用户: 帮我看一下 Python简介.md 应该放哪里")
result1 = engine.run("帮我看一下 Python简介.md 应该放哪里")
print(f"\n🤖 Bobo:\n{result1}")

# 第二步：确认（模拟用户确认）
print("\n" + "=" * 60)
print("\n📝 用户: 确认")
result2 = engine.run("确认")
print(f"\n🤖 Bobo:\n{result2}")

print("\n" + "=" * 60)
print("测试完成")
print("=" * 60)
