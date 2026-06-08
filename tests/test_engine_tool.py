#!/usr/bin/env python3
"""测试 Engine 工具调用流程"""

import sys
import json

from core.engine import Engine
from core.llm_caller import create_llm_caller
from core.tool_executor import execute_tool
from config import API_KEY, API_BASE_URL, API_MODEL_NAME
from tools import TOOLS_SCHEMA

class DebugCallback:
    def __call__(self, event_type, data):
        if event_type == "complete":
            print(f"\n[DEBUG] complete 事件，内容长度: {len(data.get('content', ''))}")
            if data.get('content'):
                print(f"[DEBUG] 内容预览: {data['content'][:100]}")
        elif event_type == "tool_result":
            print(f"[DEBUG] 工具结果: {data.get('name')} 耗时 {data.get('duration', 0):.1f}s")
        elif event_type == "thinking":
            pass
        else:
            print(f"[DEBUG] {event_type}: {data.get('phase', data.get('name', ''))}")

print("初始化...")
llm = create_llm_caller(API_KEY, API_BASE_URL, API_MODEL_NAME, TOOLS_SCHEMA)
callback = DebugCallback()
engine = Engine(llm, execute_tool, callback=callback)

# 测试带工具的查询
query = "搜索一下 Python 是什么"
print(f"\n用户: {query}")
print("-" * 50)

engine.run(query)

print("-" * 50)
print(f"History 长度: {len(engine.history)}")
if engine.history:
    last = engine.history[-1]
    print(f"最后一条消息 role: {last.get('role')}")
    if last.get('role') == 'assistant':
        print(f"内容: {last.get('content', '')[:200]}")
