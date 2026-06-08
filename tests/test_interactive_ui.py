#!/usr/bin/env python3
"""
交互式测试 - 简化版
按 1 确认，按 2 跳过
"""

import sys
import os

RESET = '\033[0m'
BOLD = '\033[1m'
BRIGHT_BLACK = '\033[90m'
BRIGHT_GREEN = '\033[92m'
BRIGHT_YELLOW = '\033[93m'
BRIGHT_CYAN = '\033[96m'
BRIGHT_MAGENTA = '\033[95m'
BRIGHT_WHITE = '\033[97m'


def clear_screen():
    os.system('clear')


def print_foldable():
    """可折叠 thinking 演示"""
    print("\n" + "=" * 70)
    print("  1. 可折叠 Thinking 演示")
    print("=" * 70)
    
    print(f"\n  {BRIGHT_YELLOW}├─ thinking (3s) [按 1 展开]{RESET}")
    print(f"\n  {BRIGHT_GREEN}{BOLD}●{RESET} 你好！有什么可以帮你的吗？")
    
    choice = input(f"\n  {BRIGHT_BLACK}👉 按 1 展开查看思考过程 (其他键跳过): {RESET}")
    
    if choice == '1':
        clear_screen()
        print("\n" + "=" * 70)
        print("  展开状态")
        print("=" * 70)
        print(f"\n  {BRIGHT_YELLOW}├─ thinking (3s){RESET}")
        print(f"  {BRIGHT_BLACK}│{RESET}  {BRIGHT_YELLOW}▶{RESET} 分析用户意图...")
        print(f"  {BRIGHT_BLACK}│{RESET}  {BRIGHT_YELLOW}▶{RESET} 准备回复")
        print(f"  {BRIGHT_BLACK}│{RESET}  {BRIGHT_GREEN}✓{RESET} 生成回复")
        print(f"  {BRIGHT_BLACK}└─{RESET}")
        print(f"\n  {BRIGHT_GREEN}{BOLD}●{RESET} 你好！有什么可以帮你的吗？")
        input(f"\n  {BRIGHT_BLACK}按回车继续...{RESET}")


def print_progress(statuses):
    """打印进度"""
    print(f"  {BRIGHT_YELLOW}├─ thinking (5s){RESET}")
    for s in statuses:
        if s['status'] == 'done':
            print(f"  {BRIGHT_BLACK}│{RESET}  {BRIGHT_GREEN}✓{RESET} {s['text']}")
        elif s['status'] == 'running':
            print(f"  {BRIGHT_BLACK}│{RESET}  {BRIGHT_YELLOW}✻{RESET} {s['text']}")
        elif s['status'] == 'waiting':
            print(f"  {BRIGHT_BLACK}│{RESET}    {BRIGHT_YELLOW}◼{RESET} {s['text']}")
        else:
            print(f"  {BRIGHT_BLACK}│{RESET}    {BRIGHT_BLACK}◻{RESET} {s['text']}")
    print(f"  {BRIGHT_BLACK}│{RESET}")
    print(f"  {BRIGHT_BLACK}└─{RESET} {BRIGHT_BLACK}等待确认...{RESET}")


def interactive_progress():
    """交互式进度演示"""
    print("\n" + "=" * 70)
    print("  2. 动态进度演示")
    print("=" * 70)
    
    tasks = [
        {"text": "起草讨论页面...", "status": "running"},
        {"text": "生成草稿，请人类确认", "status": "pending"},
        {"text": "更新 index.md 分类", "status": "pending"}
    ]
    
    print("\n")
    print_progress(tasks)
    
    # 第1步确认
    print(f"\n  {BRIGHT_MAGENTA}❯{RESET} {BRIGHT_WHITE}是否确认完成第1步？ [1=确认, 2=跳过]{RESET}")
    choice = input(f"  {BRIGHT_BLACK}👉 选择: {RESET}")
    
    if choice == '1':
        tasks[0]['status'] = 'done'
        tasks[1]['status'] = 'running'
        clear_screen()
        print("\n" + "=" * 70)
        print("  2. 动态进度演示")
        print("=" * 70)
        print("\n")
        print_progress(tasks)
        
        input(f"\n  {BRIGHT_BLACK}按回车继续...{RESET}")
        
        tasks[1]['status'] = 'waiting'
        clear_screen()
        print("\n" + "=" * 70)
        print("  2. 动态进度演示")
        print("=" * 70)
        print("\n")
        print_progress(tasks)
        
        print(f"\n  {BRIGHT_MAGENTA}❯{RESET} {BRIGHT_WHITE}草稿已生成，确认满意？ [1=确认, 2=跳过]{RESET}")
        choice2 = input(f"  {BRIGHT_BLACK}👉 选择: {RESET}")
        
        if choice2 == '1':
            tasks[1]['status'] = 'done'
            tasks[2]['status'] = 'running'
            clear_screen()
            print("\n" + "=" * 70)
            print("  2. 动态进度演示")
            print("=" * 70)
            print("\n")
            print_progress(tasks)
            
            input(f"\n  {BRIGHT_BLACK}按回车继续...{RESET}")
            
            tasks[2]['status'] = 'done'
            clear_screen()
            print("\n" + "=" * 70)
            print("  2. 动态进度演示")
            print("=" * 70)
            print("\n")
            print(f"  {BRIGHT_YELLOW}├─ thinking (5s){RESET}")
            print(f"  {BRIGHT_BLACK}│{RESET}  {BRIGHT_GREEN}✓{RESET} 起草讨论页面...")
            print(f"  {BRIGHT_BLACK}│{RESET}  {BRIGHT_GREEN}✓{RESET} 生成草稿")
            print(f"  {BRIGHT_BLACK}│{RESET}  {BRIGHT_GREEN}✓{RESET} 更新 index.md")
            print(f"  {BRIGHT_BLACK}│{RESET}")
            print(f"  {BRIGHT_BLACK}└─{RESET} {BRIGHT_GREEN}✓ 全部完成{RESET}")
            
            print(f"\n  {BRIGHT_GREEN}{BOLD}●{RESET} 已完成 3 个讨论页面的起草和索引更新")
            print(f"\n  {BRIGHT_BLACK}✓ 完成 · 耗时 8.2s · ↓ 2345 tokens{RESET}")
        else:
            print(f"\n  {BRIGHT_YELLOW}⚠️ 已取消{RESET}")
    else:
        print(f"\n  {BRIGHT_YELLOW}⚠️ 已跳过{RESET}")
    
    input(f"\n  {BRIGHT_BLACK}按回车结束...{RESET}")


if __name__ == "__main__":
    clear_screen()
    print("\n" + "=" * 70)
    print("  🎮 Claude 风格 UI 交互演示")
    print("=" * 70)
    print("\n  按数字键选择: 1=确认, 2=跳过")
    
    print_foldable()
    clear_screen()
    interactive_progress()
    
    print("\n" + "=" * 70)
    print("  ✅ 演示完成")
    print("=" * 70)
