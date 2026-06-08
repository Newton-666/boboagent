#!/usr/bin/env python3
"""
测试提醒工具
"""

import sys
import time

print("=" * 60)
print("提醒工具测试")
print("=" * 60)

# 1. 直接测试工具函数
print("\n1. 直接测试 set_reminder:")
from tools.reminder import set_reminder, list_reminders

result = set_reminder("测试提醒 - 3秒后", 3)
print(f"   {result}")

# 2. 列出提醒
print("\n2. 列出活跃提醒:")
result = list_reminders()
print(f"   {result}")

# 3. 等待提醒触发
print("\n3. 等待提醒触发 (3秒)...")
time.sleep(4)

# 4. 再次列出
print("\n4. 再次列出提醒:")
result = list_reminders()
print(f"   {result}")

# 5. 测试 Bobo 调用
print("\n5. 测试 Bobo 调用:")
from core.engine import Engine
from core.tool_executor import execute_tool
from core.llm_caller import create_llm_caller
from config import API_KEY, API_BASE_URL, API_MODEL_NAME
from tools import TOOLS_SCHEMA
from display import Display

Display.start_thinking_animation = lambda self: None
Display.stop_thinking_animation = lambda self: None

llm_caller = create_llm_caller(API_KEY, API_BASE_URL, API_MODEL_NAME, TOOLS_SCHEMA)
engine = Engine(llm_caller, execute_tool)

print("\n   输入: 5秒后提醒我喝水")
result = engine.run("5秒后提醒我喝水")
print(f"   回复: {result}")

print("\n" + "=" * 60)
print("测试完成")
print("=" * 60)
