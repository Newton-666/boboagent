#!/usr/bin/env python3
"""
测试 10: 压力测试 - 真实 UI 模拟
- 连续多个请求
- 快速交替不同类型
- 资源稳定性
"""

import sys
import os
import time
import threading


from core.engine import Engine
from core.tool_executor import execute_tool
from core.llm_caller import create_llm_caller
from config import API_KEY, API_BASE_URL, API_MODEL_NAME
from tools import TOOLS_SCHEMA

# 颜色
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
CYAN = '\033[96m'
RESET = '\033[0m'
BOLD = '\033[1m'


def print_test(name):
    print(f"\n  {CYAN}▶ 测试: {name}{RESET}")


def print_ok(msg=""):
    print(f"    {GREEN}✓{RESET} {msg}")


def print_fail(msg=""):
    print(f"    {RED}✗{RESET} {msg}")


class SilentCallback:
    def __init__(self):
        self.errors = []
        self.complete_count = 0
    
    def __call__(self, event_type, data):
        if event_type == "error":
            self.errors.append(data.get("content", ""))
        elif event_type == "complete":
            self.complete_count += 1


def test_sequential_requests():
    """测试连续请求"""
    print_test("连续请求 (5次)")
    
    llm = create_llm_caller(API_KEY, API_BASE_URL, API_MODEL_NAME, TOOLS_SCHEMA)
    
    queries = [
        "你好",
        "现在几点了",
        "1+1等于几",
        "用一句话介绍Python",
        "再见"
    ]
    
    callback = SilentCallback()
    engine = Engine(llm, execute_tool, callback=callback)
    
    start = time.time()
    for query in queries:
        engine.run(query)
        time.sleep(0.5)  # 避免过快
    elapsed = time.time() - start
    
    if callback.errors:
        print_fail(f"出现 {len(callback.errors)} 个错误")
        return False
    
    print_ok(f"完成 {len(queries)} 个请求，耗时 {elapsed:.1f}秒")
    return True


def test_alternating_requests():
    """测试交替不同类型请求"""
    print_test("交替请求 (不同类型)")
    
    llm = create_llm_caller(API_KEY, API_BASE_URL, API_MODEL_NAME, TOOLS_SCHEMA)
    
    queries = [
        "搜索 Python",
        "你好",
        "现在几点了",
        "写一个hello world",
        "列出当前目录",
        "1+2*3等于几"
    ]
    
    callback = SilentCallback()
    engine = Engine(llm, execute_tool, callback=callback)
    
    start = time.time()
    for query in queries:
        engine.run(query)
        time.sleep(0.5)
    elapsed = time.time() - start
    
    if callback.errors:
        print_fail(f"出现 {len(callback.errors)} 个错误")
        return False
    
    print_ok(f"完成 {len(queries)} 个请求，耗时 {elapsed:.1f}秒")
    return True


def main():
    print("\n" + "=" * 70)
    print(f"  {BOLD}压力测试{RESET}")
    print("=" * 70)
    
    results = []
    
    results.append(("连续请求", test_sequential_requests()))
    results.append(("交替请求", test_alternating_requests()))
    
    print("\n" + "=" * 70)
    print(f"  {BOLD}测试结果{RESET}")
    print("=" * 70)
    
    passed = 0
    for name, ok in results:
        status = f"{GREEN}✓{RESET}" if ok else f"{RED}✗{RESET}"
        print(f"  {status} {name}")
        if ok:
            passed += 1
    
    print(f"\n  {BOLD}通过率: {passed}/{len(results)} ({passed*100//len(results)}%){RESET}")
    
    if passed == len(results):
        print(f"\n  {GREEN}{BOLD}✅ 压力测试通过{RESET}")
    else:
        print(f"\n  {RED}{BOLD}❌ 部分测试失败{RESET}")
    
    print("=" * 70)


if __name__ == "__main__":
    main()
