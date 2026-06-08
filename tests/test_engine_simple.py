#!/usr/bin/env python3
"""简单测试 Engine 是否能连续处理多个请求"""

import sys

from core.engine import Engine
from core.llm_caller import create_llm_caller
from core.tool_executor import execute_tool
from config import API_KEY, API_BASE_URL, API_MODEL_NAME
from tools import TOOLS_SCHEMA

print("初始化 Engine...")
llm_caller = create_llm_caller(API_KEY, API_BASE_URL, API_MODEL_NAME, TOOLS_SCHEMA)
engine = Engine(llm_caller, execute_tool)

# 测试 1
print("\n=== 测试 1 ===")
print("输入: what tools do you use to see my mac desktop")
engine.run("what tools do you use to see my mac desktop")
print(f"History 长度: {len(engine.history)}")

# 测试 2
print("\n=== 测试 2 ===")
print("输入: I thought that you can only see obsidian?")
engine.run("I thought that you can only see obsidian?")
print(f"History 长度: {len(engine.history)}")

print("\n测试完成")
