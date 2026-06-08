#!/usr/bin/env python3
"""
测试模糊意图 - LLM 能否正确识别并调用工具
"""

import sys

from core.engine import Engine
from core.tool_executor import execute_tool
from core.llm_caller import create_llm_caller
from config import API_KEY, API_BASE_URL, API_MODEL_NAME
from tools import TOOLS_SCHEMA
from display import Display

Display.start_thinking_animation = lambda self: None
Display.stop_thinking_animation = lambda self: None

print("=" * 70)
print("模糊意图测试 - 检测 LLM 能否正确调用工具")
print("=" * 70)

llm_caller = create_llm_caller(API_KEY, API_BASE_URL, API_MODEL_NAME, TOOLS_SCHEMA)
engine = Engine(llm_caller, execute_tool)

# 测试用例：同一个意图的不同表达方式
test_cases = [
    # 日历/日程
    ("标准", "查看我最近的行程", "list_calendar_events"),
    ("模糊1", "接下来有什么安排", "list_calendar_events"),
    ("模糊2", "我今天有什么计划", "list_calendar_events"),
    ("模糊3", "看看日历", "list_calendar_events"),
    ("模糊4", "最近有什么日程", "list_calendar_events"),
    
    # 时间
    ("标准", "现在几点", "get_current_time"),
    ("模糊1", "几点了", "get_current_time"),
    ("模糊2", "告诉我当前时间", "get_current_time"),
    
    # 邮件
    ("标准", "看看有没有新邮件", "read_recent"),
    ("模糊1", "检查邮箱", "read_recent"),
    ("模糊2", "有新消息吗", "read_recent"),
    
    # 搜索
    ("标准", "搜索一下Python", "web_search"),
    ("模糊1", "帮我查查Python", "web_search"),
    ("模糊2", "Python是什么", "web_search"),
]

results = []
for intent, expr, expected_tool in test_cases:
    print(f"\n📝 [{intent}] {expr}")
    print(f"   期望工具: {expected_tool}")
    
    engine.reset()
    # 只取第一轮工具调用
    engine.history.append({"role": "user", "content": expr})
    messages = [{"role": "system", "content": engine.system_prompt}] + engine.history
    response = engine.llm_caller(messages)
    
    if "error" in response:
        print(f"   ❌ API错误: {response['error'][:50]}")
        results.append((expr, expected_tool, None, False))
        continue
    
    content, tool_calls = engine._extract_response(response)
    
    if tool_calls:
        called_tools = [tc["function"]["name"] for tc in tool_calls]
        print(f"   ✅ 调用了: {called_tools}")
        success = expected_tool in called_tools
        results.append((expr, expected_tool, called_tools, success))
    else:
        print(f"   ❌ 没有调用工具，直接回复: {content[:50]}...")
        results.append((expr, expected_tool, None, False))

print("\n" + "=" * 70)
print("测试结果汇总")
print("=" * 70)

passed = sum(1 for r in results if r[3])
failed = len(results) - passed

print(f"\n✅ 通过: {passed}")
print(f"❌ 失败: {failed}")

if failed > 0:
    print("\n失败的用例:")
    for expr, expected, called, _ in results:
        if not _:
            print(f"   - '{expr}' → 期望 {expected}, 实际 {called}")

print("\n" + "=" * 70)
