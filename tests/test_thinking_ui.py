#!/usr/bin/env python3
"""
测试 Thinking UI - 盒子风格
"""

import time
import sys

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


def print_box(content_lines, title=None):
    """打印边框盒子"""
    width = 66
    border = f"  {BRIGHT_BLACK}┌{'─' * width}┐{RESET}"
    bottom = f"  {BRIGHT_BLACK}└{'─' * width}┘{RESET}"
    
    print(border)
    for line in content_lines:
        print(f"  {BRIGHT_BLACK}│{RESET} {line:<{width}} {BRIGHT_BLACK}│{RESET}")
    print(bottom)


def test_normal_chat():
    """普通聊天 - 收起状态"""
    print("\n" + "=" * 70)
    print("测试 1: 普通聊天（收起）")
    print("=" * 70)
    
    print(f"\n  [YOU] 你 > 你好")
    print()
    print(f"  {BRIGHT_YELLOW}├─ thinking (0.3s){RESET}")
    print()
    print(f"  {BRIGHT_GREEN}{BOLD}●{RESET} 你好！今天有什么可以帮你的吗？")
    print()


def test_normal_chat_expanded():
    """普通聊天 - 展开状态"""
    print("\n" + "=" * 70)
    print("测试 2: 普通聊天（展开 Ctrl+T）")
    print("=" * 70)
    
    print(f"\n  [YOU] 你 > 你好")
    print()
    print(f"  {BRIGHT_YELLOW}├─ thinking (0.3s){RESET}")
    
    box_lines = [
        f"  {BRIGHT_YELLOW}▶{RESET} Calling LLM...",
        f"  {BRIGHT_BLACK}I need to respond to user's greeting{RESET}",
        f"  {BRIGHT_GREEN}✓{RESET} {BRIGHT_BLACK}Response generated{RESET}"
    ]
    print_box(box_lines)
    
    print(f"  {BRIGHT_GREEN}{BOLD}●{RESET} 你好！今天有什么可以帮你的吗？")
    print()


def test_code_task_collapsed():
    """代码任务 - 收起状态"""
    print("\n" + "=" * 70)
    print("测试 3: 代码任务（收起）")
    print("=" * 70)
    
    print(f"\n  [YOU] 你 > 写一个计算1+2的代码")
    print()
    print(f"  {BRIGHT_YELLOW}├─ thinking (2.3s){RESET}")
    print()
    print(f"  {BRIGHT_CYAN}⚙ write_obsidian{RESET} {BRIGHT_BLACK}filename: sum.py{RESET}")
    print(f"    {BRIGHT_GREEN}✓{RESET} {BRIGHT_BLACK}2.1s{RESET}")
    print()
    print(f"  {BRIGHT_GREEN}{BOLD}●{RESET} 代码已保存：")
    print(f"     {BRIGHT_GREEN}{BOLD}print(1 + 2){RESET}")
    print()


def test_code_task_expanded():
    """代码任务 - 展开状态"""
    print("\n" + "=" * 70)
    print("测试 4: 代码任务（展开 Ctrl+T）")
    print("=" * 70)
    
    print(f"\n  [YOU] 你 > 写一个计算1+2的代码")
    print()
    print(f"  {BRIGHT_YELLOW}├─ thinking (2.3s){RESET}")
    
    box_lines = [
        f"  {BRIGHT_YELLOW}▶{RESET} {BRIGHT_BLACK}Attempt 1/3{RESET}",
        f"     {BRIGHT_YELLOW}▶{RESET} Calling LLM...",
        f"     {BRIGHT_CYAN}⚙ extract_code{RESET} {BRIGHT_BLACK}...{RESET}",
        f"       {BRIGHT_RED}✗{RESET} {BRIGHT_BLACK}no code found{RESET}",
        f"  {BRIGHT_YELLOW}▶{RESET} {BRIGHT_BLACK}Attempt 2/3{RESET}",
        f"     {BRIGHT_YELLOW}▶{RESET} Calling LLM...",
        f"     {BRIGHT_CYAN}⚙ extract_code{RESET} {BRIGHT_BLACK}...{RESET}",
        f"       {BRIGHT_GREEN}✓{RESET} {BRIGHT_BLACK}code found{RESET}",
        f"     {BRIGHT_CYAN}⚙ write_obsidian{RESET} {BRIGHT_BLACK}...{RESET}",
        f"       {BRIGHT_GREEN}✓{RESET} {BRIGHT_BLACK}2.1s{RESET}",
        f"  {BRIGHT_YELLOW}▶{RESET} {BRIGHT_BLACK}Result: SUCCESS{RESET}"
    ]
    print_box(box_lines)
    
    print(f"  {BRIGHT_GREEN}{BOLD}●{RESET} 代码已保存：")
    print(f"     {BRIGHT_GREEN}{BOLD}print(1 + 2){RESET}")
    print()


def test_multiple_tools():
    """多工具调用"""
    print("\n" + "=" * 70)
    print("测试 5: 多工具调用（搜索+保存）")
    print("=" * 70)
    
    print(f"\n  [YOU] 你 > 搜索今天的新闻并保存")
    print()
    print(f"  {BRIGHT_YELLOW}├─ thinking (4.2s){RESET}")
    
    box_lines = [
        f"  {BRIGHT_YELLOW}▶{RESET} {BRIGHT_BLACK}Searching...{RESET}",
        f"     {BRIGHT_CYAN}⚙ web_search{RESET} {BRIGHT_BLACK}query: 今天新闻{RESET}",
        f"       {BRIGHT_GREEN}✓{RESET} {BRIGHT_BLACK}2.1s{RESET}",
        f"     {BRIGHT_YELLOW}▶{RESET} Found 5 results{RESET}",
        f"  {BRIGHT_YELLOW}▶{RESET} {BRIGHT_BLACK}Saving...{RESET}",
        f"     {BRIGHT_CYAN}⚙ write_obsidian{RESET} {BRIGHT_BLACK}title: 新闻摘要{RESET}",
        f"       {BRIGHT_GREEN}✓{RESET} {BRIGHT_BLACK}1.2s{RESET}",
        f"  {BRIGHT_YELLOW}▶{RESET} {BRIGHT_BLACK}Result: COMPLETE{RESET}"
    ]
    print_box(box_lines)
    
    print(f"  {BRIGHT_GREEN}{BOLD}●{RESET} 已完成搜索并保存到笔记")
    print()


if __name__ == "__main__":
    test_normal_chat()
    test_normal_chat_expanded()
    test_code_task_collapsed()
    test_code_task_expanded()
    test_multiple_tools()
    
    print("\n" + "=" * 70)
    print("UI 风格预览完成")
    print("=" * 70)
    print("\n快捷键说明：")
    print("  Ctrl+T  - 展开/收起 thinking 过程")
    print("  Ctrl+L  - 清屏")
    print("  Ctrl+C  - 退出")
