#!/usr/bin/env python3
"""测试 UI 回调是否正常接收事件"""

import sys

from core.engine import Engine
from core.llm_caller import create_llm_caller
from core.tool_executor import execute_tool
from config import API_KEY, API_BASE_URL, API_MODEL_NAME
from tools import TOOLS_SCHEMA

# 模拟 UI 回调
def on_event(event_type, data):
    print(f"[UI] 收到事件: {event_type}")
    if event_type == "complete":
        content = data.get("content", "")
        print(f"[UI] 回复内容长度: {len(content)}")
        print(f"[UI] 回复预览: {content[:100]}...")

print("初始化...")
llm_caller = create_llm_caller(API_KEY, API_BASE_URL, API_MODEL_NAME, TOOLS_SCHEMA)
engine = Engine(llm_caller, execute_tool, callback=on_event)

print("\n=== 测试 1 ===")
engine.run("what tools do you use to see my mac desktop")

print("\n=== 测试 2 ===")
engine.run("I thought that you can only see obsidian?")

print("\n测试完成")
