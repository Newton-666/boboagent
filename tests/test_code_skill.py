#!/usr/bin/env python3
"""
1:1 测试 - 代码编写技能
测试三个新工具: project_info, file_operation, code_execution
"""

import sys
import os
import time


from core.engine import Engine
from core.tool_executor import execute_tool
from core.llm_caller import create_llm_caller
from config import API_KEY, API_BASE_URL, API_MODEL_NAME
from tools import TOOLS_SCHEMA
from display import print_separator, print_assistant, print_tool, print_step, print_tree_end

# 颜色
BRIGHT_MAGENTA = '\033[95m'
BRIGHT_WHITE = '\033[97m'
BRIGHT_YELLOW = '\033[93m'
BRIGHT_BLACK = '\033[90m'
BRIGHT_CYAN = '\033[96m'
BRIGHT_GREEN = '\033[92m'
RESET = '\033[0m'
BOLD = '\033[1m'


def clear_line():
    sys.stdout.write('\r\033[K')
    sys.stdout.flush()


class LiveTimer:
    def __init__(self):
        self.start_time = None
        self.running = False
    
    def start(self):
        self.start_time = time.time()
        self.running = True
        print(f"  {BRIGHT_YELLOW}├─ thinking...{RESET}")
    
    def stop(self):
        if not self.running:
            return
        elapsed = time.time() - self.start_time
        self.running = False
        clear_line()
        print(f"  {BRIGHT_YELLOW}├─ thinking ({elapsed:.0f}s){RESET}")
        print(f"  {BRIGHT_BLACK}│{RESET}")


class ThinkingUI:
    def __init__(self):
        self.has_printed = False
        self.timer = LiveTimer()
    
    def on_engine_event(self, event_type, data):
        if event_type == "tool_call":
            name = data.get("name", "")
            args = data.get("args", {})
            if 'path' in args:
                query = args.get('path', '')
            elif 'code' in args:
                query = args.get('code', '')[:40]
            else:
                query = str(args)[:40]
            print(f"  {BRIGHT_BLACK}│{RESET}    {BRIGHT_CYAN}⚙ {name}{RESET} {BRIGHT_BLACK}({query}){RESET}")
        elif event_type == "tool_result":
            duration = data.get("duration", 0)
            result = data.get("result", "")
            print(f"  {BRIGHT_BLACK}│{RESET}      {BRIGHT_GREEN}✓{RESET} {BRIGHT_BLACK}done ({duration:.1f}s){RESET}")
            if result and len(result) < 200:
                for line in result.split('\n')[:3]:
                    if line.strip():
                        print(f"  {BRIGHT_BLACK}│{RESET}        {line[:80]}")
        elif event_type == "complete":
            content = data.get("content", "")
            self.timer.stop()
            print(f"  {BRIGHT_BLACK}│{RESET}")
            print(f"  {BRIGHT_BLACK}└─{RESET}")
            if not self.has_printed:
                print_assistant(content)
                self.has_printed = True
    
    def start_loop(self):
        self.has_printed = False
        self.timer.start()
        print(f"  {BRIGHT_BLACK}│{RESET}")
        print(f"  {BRIGHT_BLACK}│{RESET}  {BRIGHT_YELLOW}▶{RESET} 编写代码")


def print_header(title):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def test_project_info():
    """测试 project_info 工具"""
    print_header("测试 1: project_info - 查看项目结构")
    
    query = "查看当前项目的目录结构"
    print(f"\n  {BRIGHT_MAGENTA}> {RESET}{BRIGHT_WHITE}{query}{RESET}")
    print_separator()
    
    llm = create_llm_caller(API_KEY, API_BASE_URL, API_MODEL_NAME, TOOLS_SCHEMA)
    ui = ThinkingUI()
    engine = Engine(llm, execute_tool, callback=ui.on_engine_event)
    
    ui.start_loop()
    engine.run(query)
    
    print_separator()
    print()


def test_file_operation():
    """测试 file_operation 工具"""
    print_header("测试 2: file_operation - 读写文件")
    
    query = "在 /tmp 目录创建一个 test_hello.py 文件，内容是 print('Hello Bobo')"
    print(f"\n  {BRIGHT_MAGENTA}> {RESET}{BRIGHT_WHITE}{query}{RESET}")
    print_separator()
    
    llm = create_llm_caller(API_KEY, API_BASE_URL, API_MODEL_NAME, TOOLS_SCHEMA)
    ui = ThinkingUI()
    engine = Engine(llm, execute_tool, callback=ui.on_engine_event)
    
    ui.start_loop()
    engine.run(query)
    
    print_separator()
    print()


def test_code_execution():
    """测试 code_execution 工具"""
    print_header("测试 3: code_execution - 执行代码")
    
    query = "写一个 Python 函数计算 1+2，然后运行它"
    print(f"\n  {BRIGHT_MAGENTA}> {RESET}{BRIGHT_WHITE}{query}{RESET}")
    print_separator()
    
    llm = create_llm_caller(API_KEY, API_BASE_URL, API_MODEL_NAME, TOOLS_SCHEMA)
    ui = ThinkingUI()
    engine = Engine(llm, execute_tool, callback=ui.on_engine_event)
    
    ui.start_loop()
    engine.run(query)
    
    print_separator()
    print()


def test_full_code_workflow():
    """测试完整代码工作流"""
    print_header("测试 4: 完整代码工作流")
    
    query = """请帮我完成以下任务：
1. 查看当前项目结构
2. 创建一个 hello.py 文件，内容是 print('Hello World')
3. 运行这个 Python 文件"""
    print(f"\n  {BRIGHT_MAGENTA}> {RESET}{BRIGHT_WHITE}{query}{RESET}")
    print_separator()
    
    llm = create_llm_caller(API_KEY, API_BASE_URL, API_MODEL_NAME, TOOLS_SCHEMA)
    ui = ThinkingUI()
    engine = Engine(llm, execute_tool, callback=ui.on_engine_event)
    
    ui.start_loop()
    engine.run(query)
    
    print_separator()
    print()


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("  🧪 代码编写技能测试")
    print("=" * 70)
    
    test_project_info()
    print("\n" + "=" * 70)
    input("  👆 按回车继续下一个测试")
    
    test_file_operation()
    print("\n" + "=" * 70)
    input("  👆 按回车继续下一个测试")
    
    test_code_execution()
    print("\n" + "=" * 70)
    input("  👆 按回车继续下一个测试")
    
    test_full_code_workflow()
    print("\n" + "=" * 70)
    print("  ✅ 所有测试完成")
    print("=" * 70)
