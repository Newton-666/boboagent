#!/usr/bin/env python3
"""
测试 12: 内容去重效果
验证重复内容被过滤
"""

import sys
import os


from core.engine import Engine
from core.tool_executor import execute_tool
from core.llm_caller import create_llm_caller
from config import API_KEY, API_BASE_URL, API_MODEL_NAME
from tools import TOOLS_SCHEMA

collected_content = []

def callback(event_type, data):
    if event_type == "complete":
        content = data.get("content", "")
        collected_content.append(content)
        print(f"收到内容长度: {len(content)} 字符")

llm = create_llm_caller(API_KEY, API_BASE_URL, API_MODEL_NAME, TOOLS_SCHEMA)
engine = Engine(llm, execute_tool, callback=callback)

# 可能会产生重复内容的查询
query = "用一句话介绍Python"
print(f"查询: {query}\n")
engine.run(query)

print(f"\n收到 {len(collected_content)} 次 complete 事件")
if len(collected_content) == 1:
    print("✅ 测试通过：只有一个 complete 事件")
else:
    print(f"❌ 测试失败：有 {len(collected_content)} 个 complete 事件")
    
if collected_content:
    print(f"内容预览: {collected_content[0][:100]}...")
