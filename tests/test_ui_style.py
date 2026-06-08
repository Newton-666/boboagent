#!/usr/bin/env python3
"""
测试 UI 风格 - 模拟 Loop 过程的显示效果
"""

import time
import sys

# 颜色
RESET = '\033[0m'
BOLD = '\033[1m'
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
CYAN = '\033[96m'
MAGENTA = '\033[95m'
GRAY = '\033[90m'


def test_normal_chat():
    """测试普通聊天（无 Loop）"""
    print("\n" + "=" * 70)
    print("测试 1: 普通聊天")
    print("=" * 70)
    
    print(f"\n  {MAGENTA}[YOU] 你 >{RESET} 你好")
    print()
    print("  ● 你好！今天有什么可以帮你的吗？")
    print(f"\n  {GREEN}🐻 Bobo · 1.2s{RESET}")


def test_tool_call():
    """测试工具调用（写代码）"""
    print("\n" + "=" * 70)
    print("测试 2: 工具调用 - 写代码")
    print("=" * 70)
    
    print(f"\n  {MAGENTA}[YOU] 你 >{RESET} 写一个计算1+2的代码")
    print()
    
    # 思考过程
    print(f"  {YELLOW}🤔{RESET} 分析需求...")
    time.sleep(0.3)
    
    # 工具调用
    print(f"  {CYAN}⚙ write_obsidian{RESET} {GRAY}filename: sum.py{RESET}")
    time.sleep(0.5)
    print(f"    {GREEN}✓{RESET} {GRAY}2.3s{RESET}")
    
    # 最终回复
    print("\n  ● 代码已保存：")
    print("\n    print(1 + 2)")
    print(f"\n  {GREEN}🐻 Bobo · 3.5s{RESET}")


def test_loop_with_retry():
    """测试 Loop 带重试"""
    print("\n" + "=" * 70)
    print("测试 3: Loop 带重试 - 写复杂代码")
    print("=" * 70)
    
    print(f"\n  {MAGENTA}[YOU] 你 >{RESET} 写一个计算1到100的和")
    print()
    
    # Attempt 1
    print(f"  {YELLOW}🤔{RESET} {GRAY}Attempt 1/3{RESET}")
    print(f"  {CYAN}⚙ extract_code{RESET} {GRAY}...{RESET}")
    print(f"    {RED}✗{RESET} {GRAY}未找到代码{RESET}")
    time.sleep(0.5)
    
    # Attempt 2
    print(f"\n  {YELLOW}🤔{RESET} {GRAY}Attempt 2/3{RESET}")
    print(f"  {CYAN}⚙ extract_code{RESET} {GRAY}...{RESET}")
    print(f"    {GREEN}✓{RESET} {GRAY}找到代码{RESET}")
    print(f"  {CYAN}⚙ run_code{RESET} {GRAY}...{RESET}")
    print(f"    {RED}✗{RESET} {GRAY}输出格式错误{RESET}")
    time.sleep(0.5)
    
    # Attempt 3
    print(f"\n  {YELLOW}🤔{RESET} {GRAY}Attempt 3/3{RESET}")
    print(f"  {CYAN}⚙ run_code{RESET} {GRAY}...{RESET}")
    print(f"    {GREEN}✓{RESET} {GRAY}输出正确{RESET}")
    time.sleep(0.5)
    
    # 最终回复
    print("\n  ● 代码已生成：")
    print("\n    print(sum(range(1, 101)))")
    print(f"\n  {GREEN}🐻 Bobo · 8.2s{RESET}")


def test_multiple_tools():
    """测试多个工具调用"""
    print("\n" + "=" * 70)
    print("测试 4: 多个工具调用 - 搜索+保存")
    print("=" * 70)
    
    print(f"\n  {MAGENTA}[YOU] 你 >{RESET} 搜索今天的新闻并保存")
    print()
    
    print(f"  {YELLOW}🤔{RESET} 分析需求...")
    time.sleep(0.3)
    
    print(f"  {CYAN}⚙ web_search{RESET} {GRAY}query: 今天新闻{RESET}")
    time.sleep(0.5)
    print(f"    {GREEN}✓{RESET} {GRAY}2.1s{RESET}")
    
    print(f"  {CYAN}⚙ write_obsidian{RESET} {GRAY}title: 新闻摘要{RESET}")
    time.sleep(0.5)
    print(f"    {GREEN}✓{RESET} {GRAY}1.2s{RESET}")
    
    print("\n  ● 已完成搜索并保存到笔记")
    print(f"\n  {GREEN}🐻 Bobo · 4.5s{RESET}")


if __name__ == "__main__":
    test_normal_chat()
    test_tool_call()
    test_loop_with_retry()
    test_multiple_tools()
    
    print("\n" + "=" * 70)
    print("UI 风格预览完成")
    print("=" * 70)
