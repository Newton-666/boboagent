#!/usr/bin/env python3
"""性能测试 - 使用原生的 display 显示效果"""

import sys
import time

from config import API_KEY, API_BASE_URL, API_MODEL_NAME
from tools import TOOLS_SCHEMA
from display import Display
from core.llm_caller import create_llm_caller
from core.engine import Engine
from core.tool_executor import execute_tool

# 使用原生 Display，不修改方法
display = Display()

# 包装 execute_tool
original_execute = execute_tool

def execute_tool_with_display(tool_name, arguments):
    # 显示工具调用开始（不显示动画，避免干扰）
    display.show_tool(tool_name, "running")
    start = time.time()
    result = original_execute(tool_name, arguments)
    elapsed = time.time() - start
    # 显示工具调用结束
    status = "done" if ("✅" in result or "成功" in result) else "error"
    display.show_tool(tool_name, status)
    return result

print("=" * 60)
print("性能测试 - 原生显示效果")
print("=" * 60)

print("\n创建引擎...")
llm_caller = create_llm_caller(API_KEY, API_BASE_URL, API_MODEL_NAME, TOOLS_SCHEMA)
engine = Engine(llm_caller, execute_tool_with_display)

print("\n" + "-" * 40)
print("测试: Python调研")
print("-" * 40)

start_total = time.time()
result = engine.run("Python调研")
total_elapsed = time.time() - start_total

print(f"\n" + "-" * 40)
print(f"总耗时: {total_elapsed:.1f}s")
print(f"回复预览: {result[:200]}...")
print("=" * 60)
