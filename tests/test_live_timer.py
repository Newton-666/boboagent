#!/usr/bin/env python3
"""
测试 Live 计时器效果 - 每秒更新
"""

import time
import sys
import threading

# 颜色
RESET = '\033[0m'
BOLD = '\033[1m'

BRIGHT_BLACK = '\033[90m'
BRIGHT_RED = '\033[91m'
BRIGHT_GREEN = '\033[92m'
BRIGHT_YELLOW = '\033[93m'
BRIGHT_CYAN = '\033[96m'


def clear_line():
    """清除当前行"""
    sys.stdout.write('\r\033[K')
    sys.stdout.flush()


def simulate_thinking_with_timer(duration=5):
    """模拟 thinking 过程，带 live 计时器"""
    print("\n" + "=" * 70)
    print("测试: Live 计时器效果")
    print("=" * 70)
    
    print(f"\n  [YOU] 你 > 你好")
    print()
    
    # 打印 thinking 行（不换行）
    print(f"  {BRIGHT_YELLOW}├─ thinking (0s){RESET}", end="", flush=True)
    
    for i in range(1, duration + 1):
        time.sleep(1)
        # 回退并覆盖
        clear_line()
        print(f"  {BRIGHT_YELLOW}├─ thinking ({i}s){RESET}", end="", flush=True)
    
    print()  # 换行
    print()
    print(f"  {BRIGHT_GREEN}{BOLD}●{RESET} 你好！今天有什么可以帮你的吗？")
    print()


def simulate_code_task():
    """模拟代码任务，带计时器和工具调用"""
    print("\n" + "=" * 70)
    print("测试: 代码任务 + Live 计时器")
    print("=" * 70)
    
    print(f"\n  [YOU] 你 > 写一个计算1+2的代码")
    print()
    
    # 第一阶段：thinking（2秒）
    print(f"  {BRIGHT_YELLOW}├─ thinking (0s){RESET}", end="", flush=True)
    time.sleep(1)
    clear_line()
    print(f"  {BRIGHT_YELLOW}├─ thinking (1s){RESET}", end="", flush=True)
    time.sleep(1)
    clear_line()
    print(f"  {BRIGHT_YELLOW}├─ thinking (2s){RESET}", end="", flush=True)
    time.sleep(0.5)
    
    print()  # 换行
    print()
    
    # 工具调用
    print(f"  {BRIGHT_CYAN}⚙ write_obsidian{RESET} {BRIGHT_BLACK}filename: sum.py{RESET}")
    print(f"    {BRIGHT_GREEN}✓{RESET} {BRIGHT_BLACK}2.1s{RESET}")
    print()
    print(f"  {BRIGHT_GREEN}{BOLD}●{RESET} 代码已保存：")
    print(f"     {BRIGHT_GREEN}{BOLD}print(1 + 2){RESET}")
    print()


def simulate_with_expand():
    """模拟展开状态 - 盒子内的思考过程"""
    print("\n" + "=" * 70)
    print("测试: 展开状态（Ctrl+T）")
    print("=" * 70)
    
    print(f"\n  [YOU] 你 > 写一个计算1+2的代码")
    print()
    
    # 打印 thinking 行
    print(f"  {BRIGHT_YELLOW}├─ thinking (0s){RESET}", end="", flush=True)
    
    # 计时 3 秒
    for i in range(1, 4):
        time.sleep(1)
        clear_line()
        print(f"  {BRIGHT_YELLOW}├─ thinking ({i}s){RESET}", end="", flush=True)
    
    print()
    
    # 打印盒子
    width = 66
    border = f"  {BRIGHT_BLACK}┌{'─' * width}┐{RESET}"
    bottom = f"  {BRIGHT_BLACK}└{'─' * width}┘{RESET}"
    
    print(border)
    print(f"  {BRIGHT_BLACK}│{RESET}   {BRIGHT_YELLOW}▶{RESET} {BRIGHT_BLACK}Attempt 1/2{RESET}                         {BRIGHT_BLACK}│{RESET}")
    print(f"  {BRIGHT_BLACK}│{RESET}      {BRIGHT_YELLOW}▶{RESET} Calling LLM...{RESET}                             {BRIGHT_BLACK}│{RESET}")
    print(f"  {BRIGHT_BLACK}│{RESET}      {BRIGHT_CYAN}⚙ extract_code{RESET} ...{RESET}                              {BRIGHT_BLACK}│{RESET}")
    print(f"  {BRIGHT_BLACK}│{RESET}        {BRIGHT_GREEN}✓{RESET} {BRIGHT_BLACK}code found{RESET}                               {BRIGHT_BLACK}│{RESET}")
    print(f"  {BRIGHT_BLACK}│{RESET}   {BRIGHT_YELLOW}▶{RESET} {BRIGHT_BLACK}Attempt 2/2{RESET}                         {BRIGHT_BLACK}│{RESET}")
    print(f"  {BRIGHT_BLACK}│{RESET}      {BRIGHT_YELLOW}▶{RESET} Running code...{RESET}                              {BRIGHT_BLACK}│{RESET}")
    print(f"  {BRIGHT_BLACK}│{RESET}        {BRIGHT_GREEN}✓{RESET} {BRIGHT_BLACK}output: 3{RESET}                                 {BRIGHT_BLACK}│{RESET}")
    print(f"  {BRIGHT_BLACK}│{RESET}   {BRIGHT_YELLOW}▶{RESET} {BRIGHT_BLACK}Result: SUCCESS{RESET}                         {BRIGHT_BLACK}│{RESET}")
    print(bottom)
    print()
    print(f"  {BRIGHT_GREEN}{BOLD}●{RESET} 代码已生成：")
    print(f"     {BRIGHT_GREEN}{BOLD}print(1 + 2){RESET}")
    print()


if __name__ == "__main__":
    simulate_thinking_with_timer(5)
    simulate_code_task()
    simulate_with_expand()
    
    print("\n" + "=" * 70)
    print("效果说明")
    print("=" * 70)
    print("""
  Live 计时器特点：
  - 从 0s 开始
  - 每秒更新一次（0s → 1s → 2s → 3s...）
  - 回复出现时停止更新
  - 不显示小数

  快捷键：
    Ctrl+T  - 展开/收起 thinking 过程
    Ctrl+L  - 清屏
    Ctrl+C  - 退出
    """)
