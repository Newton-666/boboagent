#!/usr/bin/env python3
"""
1:1 测试重复打印问题
模拟完整流程，检测 complete 事件和 print_assistant 调用次数
"""

import sys
import os
import time
import json


from core.llm_caller import create_llm_caller
from config import API_KEY, API_BASE_URL, API_MODEL_NAME
from tools import TOOLS_SCHEMA

# 颜色
RESET = '\033[0m'
BOLD = '\033[1m'
BRIGHT_GREEN = '\033[92m'
BRIGHT_WHITE = '\033[97m'
BRIGHT_BLACK = '\033[90m'
BRIGHT_YELLOW = '\033[93m'


def print_separator():
    print(f"  {BRIGHT_BLACK}{'─' * 70}{RESET}")


def print_assistant(content):
    """模拟 print_assistant"""
    print(f"\n  [DEBUG] print_assistant 被调用")
    print(f"  {BRIGHT_GREEN}{BOLD}●{RESET} {content}")
    print()


class DebugCallback:
    def __init__(self):
        self.complete_count = 0
        self.print_count = 0
    
    def __call__(self, event_type, data):
        if event_type == "complete":
            self.complete_count += 1
            content = data.get("content", "")
            print(f"\n  [DEBUG] complete 事件 #{self.complete_count}, 内容长度={len(content)}")
            # 模拟 UI 打印
            print_assistant(content)
            self.print_count += 1
        elif event_type == "tool_call":
            name = data.get("name", "")
            print(f"  {BRIGHT_YELLOW}▶{RESET} 调用工具: {name}")
        elif event_type == "user_input":
            print(f"  [DEBUG] 用户输入: {data.get('content', '')[:50]}")
        else:
            pass


def test_simple_query():
    """测试简单查询"""
    print("\n" + "=" * 70)
    print("测试 1: 简单查询")
    print("=" * 70)
    
    from core.engine import Engine
    from core.tool_executor import execute_tool
    
    llm = create_llm_caller(API_KEY, API_BASE_URL, API_MODEL_NAME, TOOLS_SCHEMA)
    callback = DebugCallback()
    engine = Engine(llm, execute_tool, callback=callback)
    
    query = "你好"
    print(f"\n  用户: {query}")
    print_separator()
    
    engine.run(query)
    
    print_separator()
    print(f"\n  统计: complete 事件 {callback.complete_count} 次, print_assistant {callback.print_count} 次")
    
    return callback.complete_count, callback.print_count


def test_search_query():
    """测试搜索查询"""
    print("\n" + "=" * 70)
    print("测试 2: 搜索查询")
    print("=" * 70)
    
    from core.engine import Engine
    from core.tool_executor import execute_tool
    
    llm = create_llm_caller(API_KEY, API_BASE_URL, API_MODEL_NAME, TOOLS_SCHEMA)
    callback = DebugCallback()
    engine = Engine(llm, execute_tool, callback=callback)
    
    query = "搜索 Python"
    print(f"\n  用户: {query}")
    print_separator()
    
    engine.run(query)
    
    print_separator()
    print(f"\n  统计: complete 事件 {callback.complete_count} 次, print_assistant {callback.print_count} 次")
    
    return callback.complete_count, callback.print_count


def test_travel_query():
    """测试旅游查询（可能触发工具）"""
    print("\n" + "=" * 70)
    print("测试 3: 旅游查询")
    print("=" * 70)
    
    from core.engine import Engine
    from core.tool_executor import execute_tool
    
    llm = create_llm_caller(API_KEY, API_BASE_URL, API_MODEL_NAME, TOOLS_SCHEMA)
    callback = DebugCallback()
    engine = Engine(llm, execute_tool, callback=callback)
    
    query = "北京两天游怎么安排"
    print(f"\n  用户: {query}")
    print_separator()
    
    engine.run(query)
    
    print_separator()
    print(f"\n  统计: complete 事件 {callback.complete_count} 次, print_assistant {callback.print_count} 次")
    
    return callback.complete_count, callback.print_count


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("重复打印问题诊断测试")
    print("=" * 70)
    
    results = []
    
    c1, p1 = test_simple_query()
    results.append(("简单查询", c1, p1))
    
    c2, p2 = test_search_query()
    results.append(("搜索查询", c2, p2))
    
    c3, p3 = test_travel_query()
    results.append(("旅游查询", c3, p3))
    
    print("\n" + "=" * 70)
    print("结果汇总")
    print("=" * 70)
    print(f"\n  {'测试类型':<12} {'complete次数':<12} {'print次数':<12} {'状态':<10}")
    print(f"  {'-' * 50}")
    for name, c, p in results:
        status = "✅ 正常" if c == p == 1 else "❌ 重复"
        print(f"  {name:<12} {c:<12} {p:<12} {status}")
    
    print("\n" + "=" * 70)
