#!/usr/bin/env python3
"""
测试复杂指令：编写计算器网页程序
1:1 还原真实界面
"""

import sys
import os
import time
import json
import re
import threading


from core.engine import Engine
from core.tool_executor import execute_tool
from core.llm_caller import create_llm_caller
from config import API_KEY, API_BASE_URL, API_MODEL_NAME
from tools import TOOLS_SCHEMA

# 颜色
RESET = '\033[0m'
BOLD = '\033[1m'

BRIGHT_BLACK = '\033[90m'
BRIGHT_RED = '\033[91m'
BRIGHT_GREEN = '\033[92m'
BRIGHT_YELLOW = '\033[93m'
BRIGHT_BLUE = '\033[94m'
BRIGHT_MAGENTA = '\033[95m'
BRIGHT_CYAN = '\033[96m'
BRIGHT_WHITE = '\033[97m'


def clear_line():
    sys.stdout.write('\r\033[K')
    sys.stdout.flush()


def print_separator():
    print(f"  {BRIGHT_BLACK}{'─' * 70}{RESET}")


def print_thinking_line(content):
    print(f"  {BRIGHT_YELLOW}▶{RESET} {content}")


def print_tool(name, args, status="running", output=None, duration=None):
    args_str = json.dumps(args, ensure_ascii=False)[:50] if args else ""
    if status == "running":
        print(f"  {BRIGHT_CYAN}⚙ {name}{RESET} {BRIGHT_BLACK}{args_str}{RESET}")
    elif status == "success":
        if duration:
            print(f"    {BRIGHT_GREEN}✓{RESET} {BRIGHT_BLACK}{duration:.1f}s{RESET}")
            if output:
                print(f"      {output[:150]}")
    elif status == "error":
        print(f"    {BRIGHT_RED}✗{RESET} {BRIGHT_BLACK}{args_str}{RESET}")


def print_code(code):
    print()
    for line in code.split('\n')[:20]:
        print(f"  {BRIGHT_GREEN}{BOLD}{line}{RESET}")
    if len(code.split('\n')) > 20:
        print(f"  {BRIGHT_BLACK}... (共 {len(code.split(chr(10)))} 行){RESET}")
    print()


def print_assistant(content):
    code_pattern = r'```(html|python|javascript)\n(.*?)\n```'
    match = re.search(code_pattern, content, re.DOTALL)
    
    if match:
        lang = match.group(1)
        code = match.group(2)
        before_code = content[:match.start()].strip()
        after_code = content[match.end():].strip()
        
        if before_code:
            print(f"\n  {BRIGHT_GREEN}{BOLD}●{RESET} {before_code}")
        print_code(code)
        if after_code:
            print(f"  {after_code}")
    else:
        print(f"\n  {BRIGHT_GREEN}{BOLD}●{RESET} {content}")
    print()


class LiveTimer:
    def __init__(self):
        self.seconds = 0
        self.running = False
        self.thread = None
    
    def start(self):
        self.seconds = 0
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
    
    def _run(self):
        while self.running:
            time.sleep(1)
            if self.running:
                self.seconds += 1
                clear_line()
                print(f"  {BRIGHT_YELLOW}├─ thinking ({self.seconds}s){RESET}", end="", flush=True)
    
    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=0.5)
        clear_line()
        print(f"  {BRIGHT_YELLOW}├─ thinking ({self.seconds}s){RESET}")
        print()


class ThinkingUI:
    def __init__(self):
        self.has_printed = False
        self.timer = LiveTimer()
    
    def on_engine_event(self, event_type: str, data: dict):
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
            self.timer.stop()
            if not self.has_printed:
                print_assistant(content)
                self.has_printed = True
    
    def start_loop(self):
        self.has_printed = False
        self.timer.start()


def test_complex_task():
    """测试复杂任务：编写计算器网页程序"""
    print("\n" + "=" * 70)
    print(f"  {BOLD}🧪 测试: 编写计算器网页程序{RESET}")
    print("=" * 70)
    
    query = """请帮我写一个计算器网页程序，要求：
1. 支持加、减、乘、除基本运算
2. 界面简洁美观
3. 使用 HTML/CSS/JS
4. 代码可以直接在浏览器中运行"""
    
    print(f"\n  {BRIGHT_MAGENTA}> {RESET}{BRIGHT_WHITE}{query}{RESET}")
    print_separator()
    
    # 初始化 UI 回调
    thinking_ui = ThinkingUI()
    
    # 初始化 Engine
    llm_caller = create_llm_caller(API_KEY, API_BASE_URL, API_MODEL_NAME, TOOLS_SCHEMA)
    engine = Engine(llm_caller, execute_tool, callback=thinking_ui.on_engine_event)
    
    # 执行
    start = time.time()
    thinking_ui.start_loop()
    engine.run(query)
    elapsed = time.time() - start
    
    print_separator()
    print(f"  {BRIGHT_GREEN}🐻 Bobo · {elapsed:.1f}s{RESET}")
    print_separator()
    print()


if __name__ == "__main__":
    test_complex_task()
