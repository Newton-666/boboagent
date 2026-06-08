#!/usr/bin/env python3
"""
1:1 测试 - 动态打钩效果（独立一行显示钩）
"""

import time
import sys

RESET = '\033[0m'
BOLD = '\033[1m'
BRIGHT_BLACK = '\033[90m'
BRIGHT_GREEN = '\033[92m'
BRIGHT_YELLOW = '\033[93m'
BRIGHT_CYAN = '\033[96m'
BRIGHT_MAGENTA = '\033[95m'
BRIGHT_WHITE = '\033[97m'


def clear_line():
    sys.stdout.write('\r\033[K')
    sys.stdout.flush()


def print_separator():
    print(f"  {BRIGHT_BLACK}{'─' * 70}{RESET}")


def simulate_travel_plan():
    print("\n" + "=" * 70)
    print("  场景: 出行计划")
    print("=" * 70)
    
    query = "明天去北京，列出出行计划"
    print(f"\n  {BRIGHT_MAGENTA}> {RESET}{BRIGHT_WHITE}{query}{RESET}")
    print_separator()
    
    # 主 thinking 计时
    print(f"  {BRIGHT_YELLOW}├─ thinking (0s){RESET}", end="")
    for s in range(1, 3):
        time.sleep(1)
        clear_line()
        print(f"  {BRIGHT_YELLOW}├─ thinking ({s}s){RESET}", end="")
    print()
    
    print(f"  {BRIGHT_BLACK}│{RESET}")
    print(f"  {BRIGHT_BLACK}│{RESET}  {BRIGHT_YELLOW}▶{RESET} 规划出行计划")
    
    # 工具 1
    print(f"  {BRIGHT_BLACK}│{RESET}    {BRIGHT_CYAN}⚙ web_search{RESET} {BRIGHT_BLACK}query: G532 上海到北京 时刻表{RESET}")
    time.sleep(0.8)
    print(f"  {BRIGHT_BLACK}│{RESET}      {BRIGHT_GREEN}✓{RESET} {BRIGHT_BLACK}done (2.3s){RESET}")
    
    # 工具 2
    print(f"  {BRIGHT_BLACK}│{RESET}    {BRIGHT_CYAN}⚙ web_search{RESET} {BRIGHT_BLACK}query: MUJI HOTEL 北京 电话 地址{RESET}")
    time.sleep(0.6)
    print(f"  {BRIGHT_BLACK}│{RESET}      {BRIGHT_GREEN}✓{RESET} {BRIGHT_BLACK}done (1.8s){RESET}")
    
    # 工具 3
    print(f"  {BRIGHT_BLACK}│{RESET}    {BRIGHT_CYAN}⚙ web_search{RESET} {BRIGHT_BLACK}query: 北京南站 到 前门 地铁{RESET}")
    time.sleep(0.5)
    print(f"  {BRIGHT_BLACK}│{RESET}      {BRIGHT_GREEN}✓{RESET} {BRIGHT_BLACK}done (1.2s){RESET}")
    
    # 步骤 2
    print(f"  {BRIGHT_BLACK}│{RESET}")
    print(f"  {BRIGHT_BLACK}│{RESET}  {BRIGHT_YELLOW}▶{RESET} 整理结果")
    print(f"  {BRIGHT_BLACK}│{RESET}    {BRIGHT_GREEN}✓{RESET} {BRIGHT_BLACK}生成出行计划{RESET}")
    
    print(f"  {BRIGHT_BLACK}│{RESET}")
    print(f"  {BRIGHT_BLACK}└─{RESET}")
    
    # 最终回复
    print(f"\n  {BRIGHT_GREEN}{BOLD}●{RESET} 以下是出行计划：\n")
    print(f"     🚆 G532 上海虹桥 → 北京南 09:00-13:30")
    print(f"     🏨 MUJI HOTEL 北京坊店")
    print(f"     📞 电话: 010-63169199")
    print(f"     🚇 北京南站 → 4号线 → 宣武门 → 2号线 → 前门 (约25分钟)")
    
    print_separator()
    print(f"  {BRIGHT_BLACK}● 完成 · 耗时 5.2s{RESET}")


if __name__ == "__main__":
    simulate_travel_plan()
    print("\n" + "=" * 70)
    print("  ✅ 效果：一行工具调用，一行 done")
    print("=" * 70)
