#!/usr/bin/env python3
"""
真实复杂问题测试 - 1:1 还原完整交互
"""

import sys
import os
import time
import json
import re


from core.engine import Engine
from core.tool_executor import execute_tool
from core.llm_caller import create_llm_caller
from config import API_KEY, API_BASE_URL, API_MODEL_NAME
from tools import TOOLS_SCHEMA
from display import print_separator, print_logo, print_tool, print_assistant

# 颜色
BRIGHT_MAGENTA = '\033[95m'
BRIGHT_WHITE = '\033[97m'
BRIGHT_YELLOW = '\033[93m'
RESET = '\033[0m'


class Timer:
    def __init__(self):
        self.start_time = None
    
    def start(self):
        self.start_time = time.time()
    
    def stop(self):
        return time.time() - self.start_time


class ThinkingUI:
    def __init__(self):
        self.has_printed = False
    
    def on_engine_event(self, event_type, data):
        if event_type == "tool_call":
            name = data.get("name", "")
            args = data.get("args", {})
            print_tool(name, args, "running")
        elif event_type == "tool_result":
            duration = data.get("duration", 0)
            success = data.get("success", False)
            result = data.get("result", "")
            status = "success" if success else "error"
            print_tool("", "", status, duration=duration, output=result[:200])
        elif event_type == "complete":
            content = data.get("content", "")
            if not self.has_printed:
                print_assistant(content)
                self.has_printed = True


def run_test(question, test_name):
    """运行单个测试"""
    print("\n" + "=" * 70)
    print(f"  🧪 {test_name}")
    print("=" * 70)
    
    print(f"\n  {BRIGHT_MAGENTA}> {RESET}{BRIGHT_WHITE}{question}{RESET}")
    print_separator()
    
    # 初始化
    llm = create_llm_caller(API_KEY, API_BASE_URL, API_MODEL_NAME, TOOLS_SCHEMA)
    ui = ThinkingUI()
    engine = Engine(llm, execute_tool, callback=ui.on_engine_event)
    
    # 执行
    timer = Timer()
    timer.start()
    engine.run(question)
    elapsed = timer.stop()
    
    print_separator()
    print(f"  {BRIGHT_YELLOW}⏱️ 耗时: {elapsed:.1f}秒{RESET}")
    print_separator()
    print()


def main():
    print("\n" + "=" * 70)
    print("  🧸 Bobo 复杂问题真实测试")
    print("=" * 70)
    print_logo()
    
    # 测试 1: 代码生成 + 解释
    test1 = """
请帮我写一个 Python 脚本，功能是：
1. 读取一个 JSON 文件
2. 提取所有键值对
3. 生成一个 Markdown 表格
4. 保存为 .md 文件

要求：代码要有错误处理，并解释每一步的作用。
"""
    run_test(test1.strip(), "测试 1: 代码生成 + 解释")
    
    # 测试 2: 多步搜索 + 分析
    test2 = """
帮我搜索一下 2026 年 AI Agent 领域的最新进展。
要求：
1. 搜索至少 2 个相关话题
2. 总结关键趋势
3. 给出至少 3 个开源项目参考
"""
    run_test(test2.strip(), "测试 2: 多步搜索 + 分析")
    
    # 测试 3: 文件操作 + 规划
    test3 = """
我想整理我的 Downloads 文件夹。
请帮我：
1. 列出下载文件夹的内容
2. 分析文件类型分布
3. 给出分类整理的建议
"""
    run_test(test3.strip(), "测试 3: 文件操作 + 规划")
    
    print("\n" + "=" * 70)
    print("  ✅ 所有测试完成")
    print("=" * 70)


if __name__ == "__main__":
    main()
