#!/usr/bin/env python3
"""
测试新工具：终端执行 + 目录浏览
"""

import sys
import os


from tools.execute_terminal import execute as run_terminal
from tools.list_directory import execute as list_dir

# 颜色
RESET = '\033[0m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
CYAN = '\033[96m'
GRAY = '\033[90m'
RED = '\033[91m'


def print_test(title):
    print(f"\n{YELLOW}{'='*70}{RESET}")
    print(f"  {title}")
    print(f"{YELLOW}{'='*70}{RESET}")


def test_list_directory():
    """测试目录列出工具"""
    print_test("测试 1: 列出目录内容")
    
    print(f"\n{GREEN}1. 列出当前目录:{RESET}")
    result = list_dir(".", show_hidden=False, max_items=20)
    print(result)
    
    print(f"\n{GREEN}2. 列出用户目录（限制5项）:{RESET}")
    result = list_dir("~", show_hidden=False, max_items=5)
    print(result)
    
    print(f"\n{GREEN}3. 列出不存在的目录:{RESET}")
    result = list_dir("/nonexistent_path_12345")
    print(result)


def test_terminal_safe():
    """测试安全终端命令"""
    print_test("测试 2: 执行安全终端命令")
    
    print(f"\n{GREEN}1. 执行 'echo Hello Bobo':{RESET}")
    result = run_terminal("echo Hello Bobo")
    print(result)
    
    print(f"\n{GREEN}2. 执行 'pwd' (当前路径):{RESET}")
    result = run_terminal("pwd")
    print(result)
    
    print(f"\n{GREEN}3. 执行 'ls -la | head -5':{RESET}")
    result = run_terminal("ls -la | head -5")
    print(result)


def test_terminal_with_args():
    """测试带参数的命令"""
    print_test("测试 3: 带参数的命令")
    
    print(f"\n{GREEN}1. 执行 'python3 --version':{RESET}")
    result = run_terminal("python3 --version")
    print(result)
    
    print(f"\n{GREEN}2. 执行 'which python3':{RESET}")
    result = run_terminal("which python3")
    print(result)


def test_terminal_error():
    """测试错误命令"""
    print_test("测试 4: 错误命令处理")
    
    print(f"\n{GREEN}1. 执行不存在的命令:{RESET}")
    result = run_terminal("nonexistent_command_xyz")
    print(result)
    
    print(f"\n{GREEN}2. 执行超时测试:{RESET}")
    result = run_terminal("sleep 10", timeout=2)
    print(result)


def test_terminal_with_pipe():
    """测试管道命令"""
    print_test("测试 5: 管道命令")
    
    print(f"\n{GREEN}1. 执行 'ps aux | grep python | head -3':{RESET}")
    result = run_terminal("ps aux | grep python | head -3")
    print(result)


if __name__ == "__main__":
    print(f"\n{CYAN}🧪 工具测试开始{RESET}")
    
    test_list_directory()
    test_terminal_safe()
    test_terminal_with_args()
    test_terminal_error()
    test_terminal_with_pipe()
    
    print(f"\n{CYAN}{'='*70}{RESET}")
    print(f"  ✅ 测试完成")
    print(f"  📍 终端工具可以执行: echo, ls, pwd, ps, python --version 等")
    print(f"  📍 目录工具可以列出: 当前目录、用户目录")
    print(f"  📍 错误处理: 超时、命令不存在")
    print(f"{CYAN}{'='*70}{RESET}\n")
