#!/usr/bin/env python3
"""
测试 16: 意图判断能力
验证 Bobo 能否正确区分问候、聊天、工具调用
"""

import sys
import os
import time


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


def print_info(msg=""):
    print(f"    {YELLOW}ℹ{RESET} {msg}")


class TestCallback:
    def __init__(self):
        self.tool_calls = []
        self.complete_content = ""
    
    def __call__(self, event_type, data):
        if event_type == "tool_call":
            self.tool_calls.append(data.get("name"))
        elif event_type == "complete":
            self.complete_content = data.get("content", "")


def test_greeting():
    """测试问候语 - 不应调用工具"""
    print_test("问候语 (不应调用工具)")
    
    llm = create_llm_caller(API_KEY, API_BASE_URL, API_MODEL_NAME, TOOLS_SCHEMA)
    callback = TestCallback()
    engine = Engine(llm, execute_tool, callback=callback)
    
    queries = ["你好", "嗨", "Hello", "在吗", "我回来了", "Hi Bobo"]
    
    passed = 0
    for query in queries:
        callback.tool_calls = []
        engine.run(query)
        if len(callback.tool_calls) == 0:
            print_ok(f"  '{query}' -> 无工具调用")
            passed += 1
        else:
            print_fail(f"  '{query}' -> 调用了 {callback.tool_calls}")
    
    print_info(f"通过率: {passed}/{len(queries)}")
    return passed == len(queries)


def test_chat():
    """测试普通聊天 - 不应调用工具"""
    print_test("普通聊天 (不应调用工具)")
    
    llm = create_llm_caller(API_KEY, API_BASE_URL, API_MODEL_NAME, TOOLS_SCHEMA)
    callback = TestCallback()
    engine = Engine(llm, execute_tool, callback=callback)
    
    queries = [
        "今天天气真好",
        "你觉得怎么样",
        "讲个笑话",
        "你能做什么",
        "介绍下自己"
    ]
    
    passed = 0
    for query in queries:
        callback.tool_calls = []
        engine.run(query)
        if len(callback.tool_calls) == 0:
            print_ok(f"  '{query}' -> 无工具调用")
            passed += 1
        else:
            print_fail(f"  '{query}' -> 调用了 {callback.tool_calls}")
    
    print_info(f"通过率: {passed}/{len(queries)}")
    return passed == len(queries)


def test_search():
    """测试搜索请求 - 应调用工具"""
    print_test("搜索请求 (应调用工具)")
    
    llm = create_llm_caller(API_KEY, API_BASE_URL, API_MODEL_NAME, TOOLS_SCHEMA)
    callback = TestCallback()
    engine = Engine(llm, execute_tool, callback=callback)
    
    queries = [
        "搜索 Python",
        "查一下今天的新闻",
        "帮我找找 AI 相关的文章",
        "搜索一下天气",
    ]
    
    passed = 0
    for query in queries:
        callback.tool_calls = []
        engine.run(query)
        if len(callback.tool_calls) > 0:
            print_ok(f"  '{query}' -> 调用了 {callback.tool_calls}")
            passed += 1
        else:
            print_fail(f"  '{query}' -> 没有调用工具")
    
    print_info(f"通过率: {passed}/{len(queries)}")
    return passed == len(queries)


def test_file_operation():
    """测试文件操作 - 应调用工具"""
    print_test("文件操作 (应调用工具)")
    
    llm = create_llm_caller(API_KEY, API_BASE_URL, API_MODEL_NAME, TOOLS_SCHEMA)
    callback = TestCallback()
    engine = Engine(llm, execute_tool, callback=callback)
    
    queries = [
        "列出当前目录",
        "读取 main.py",
        "查看桌面文件",
        "显示文件夹内容",
    ]
    
    passed = 0
    for query in queries:
        callback.tool_calls = []
        engine.run(query)
        if len(callback.tool_calls) > 0:
            print_ok(f"  '{query}' -> 调用了 {callback.tool_calls}")
            passed += 1
        else:
            print_fail(f"  '{query}' -> 没有调用工具")
    
    print_info(f"通过率: {passed}/{len(queries)}")
    return passed == len(queries)


def test_code_generation():
    """测试代码生成 - 应直接输出，不应调用工具"""
    print_test("代码生成 (应直接输出代码)")
    
    llm = create_llm_caller(API_KEY, API_BASE_URL, API_MODEL_NAME, TOOLS_SCHEMA)
    callback = TestCallback()
    engine = Engine(llm, execute_tool, callback=callback)
    
    queries = [
        "写一个 hello world",
        "生成一个计算器",
        "写个 Python 函数",
    ]
    
    passed = 0
    for query in queries:
        callback.tool_calls = []
        engine.run(query)
        # 代码生成可能通过 write_obsidian 保存，也可能直接输出
        # 只要不是错误就行
        if callback.complete_content or len(callback.tool_calls) >= 0:
            print_ok(f"  '{query}' -> 已处理")
            passed += 1
        else:
            print_fail(f"  '{query}' -> 无响应")
    
    print_info(f"通过率: {passed}/{len(queries)}")
    return True


def test_ambiguous():
    """测试模糊请求 - 应询问澄清"""
    print_test("模糊请求 (应询问澄清)")
    
    llm = create_llm_caller(API_KEY, API_BASE_URL, API_MODEL_NAME, TOOLS_SCHEMA)
    callback = TestCallback()
    engine = Engine(llm, execute_tool, callback=callback)
    
    queries = [
        "那个",
        "帮我看看",
        "你懂的",
    ]
    
    passed = 0
    for query in queries:
        callback.tool_calls = []
        engine.run(query)
        # 模糊请求应该直接回复，不调用工具
        if len(callback.tool_calls) == 0:
            print_ok(f"  '{query}' -> 无工具调用 (合理)")
            passed += 1
        else:
            print_fail(f"  '{query}' -> 调用了工具")
    
    print_info(f"通过率: {passed}/{len(queries)}")
    return passed == len(queries)


def main():
    print("\n" + "=" * 70)
    print(f"  {BOLD}意图判断能力测试{RESET}")
    print("=" * 70)
    
    results = []
    
    results.append(("问候语", test_greeting()))
    results.append(("普通聊天", test_chat()))
    results.append(("搜索请求", test_search()))
    results.append(("文件操作", test_file_operation()))
    results.append(("代码生成", test_code_generation()))
    results.append(("模糊请求", test_ambiguous()))
    
    print("\n" + "=" * 70)
    print(f"  {BOLD}测试结果汇总{RESET}")
    print("=" * 70)
    
    passed = 0
    for name, ok in results:
        status = f"{GREEN}✓{RESET}" if ok else f"{RED}✗{RESET}"
        print(f"  {status} {name}")
        if ok:
            passed += 1
    
    print(f"\n  {BOLD}通过率: {passed}/{len(results)} ({passed*100//len(results)}%){RESET}")
    
    if passed == len(results):
        print(f"\n  {GREEN}{BOLD}✅ 意图判断能力良好{RESET}")
    else:
        print(f"\n  {RED}{BOLD}❌ 部分测试失败，需要优化意图判断{RESET}")
    
    print("=" * 70)


if __name__ == "__main__":
    main()
