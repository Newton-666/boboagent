#!/usr/bin/env python3
"""
测试 8: 记忆与上下文 - 真实 UI 模拟
- 多轮对话上下文保持
- 历史记忆
- 会话连续性
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
from display import print_separator, print_assistant, print_tool

# 颜色
BRIGHT_MAGENTA = '\033[95m'
BRIGHT_WHITE = '\033[97m'
BRIGHT_YELLOW = '\033[93m'
RESET = '\033[0m'


def clear_line():
    sys.stdout.write('\r\033[K')
    sys.stdout.flush()


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
            self.timer.stop()
            if not self.has_printed:
                print_assistant(content)
                self.has_printed = True
    
    def start_loop(self):
        self.has_printed = False
        self.timer.start()


def print_header(title):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def test_multi_turn():
    """测试多轮对话"""
    print("\n" + "=" * 70)
    print("  测试 1: 多轮对话上下文保持")
    print("=" * 70)
    
    queries = [
        "我叫小明，喜欢吃苹果",
        "你还记得我叫什么名字吗？",
        "我最喜欢的水果是什么？"
    ]
    
    # 使用同一个 engine 实例
    llm = create_llm_caller(API_KEY, API_BASE_URL, API_MODEL_NAME, TOOLS_SCHEMA)
    ui = ThinkingUI()
    engine = Engine(llm, execute_tool, callback=ui.on_engine_event)
    
    for i, query in enumerate(queries, 1):
        print(f"\n  {BRIGHT_MAGENTA}> {RESET}{BRIGHT_WHITE}{query}{RESET}")
        print_separator()
        
        ui.start_loop()
        engine.run(query)
        
        print_separator()
        print()
        time.sleep(1)


def test_context_switch():
    """测试上下文切换"""
    print("\n" + "=" * 70)
    print("  测试 2: 话题切换后上下文保持")
    print("=" * 70)
    
    llm = create_llm_caller(API_KEY, API_BASE_URL, API_MODEL_NAME, TOOLS_SCHEMA)
    ui = ThinkingUI()
    engine = Engine(llm, execute_tool, callback=ui.on_engine_event)
    
    queries = [
        "我住在北京",
        "今天天气怎么样？",
        "你还记得我住在哪里吗？"
    ]
    
    for i, query in enumerate(queries, 1):
        print(f"\n  {BRIGHT_MAGENTA}> {RESET}{BRIGHT_WHITE}{query}{RESET}")
        print_separator()
        
        ui.start_loop()
        engine.run(query)
        
        print_separator()
        print()
        time.sleep(1)


if __name__ == "__main__":
    print_header("记忆与上下文测试")
    test_multi_turn()
    test_context_switch()
    
    print("\n" + "=" * 70)
    print("  ✅ 记忆与上下文测试完成")
    print("=" * 70)
