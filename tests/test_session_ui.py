#!/usr/bin/env python3
"""
测试初始界面 - 会话选择器 UI
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

# 像素 Logo
PIXEL_BOBO = [
    "     ██████╗  █████╗  ██████╗  █████╗",
    "     ██╔══██╗ ██╔══██╗██╔══██╗██╔══██╗",
    "     ██████╔╝ ██╔══██╗██████╔╝██╔══██║",
    "     ██╔══██╗ ██╔══██╗██╔══██╗██╔══██║",
    "     ██████╔╝ ███████╗██████╔╝ █████╔╝",
    "     ╚═════╝  ╚══════╝╚═════╝  ╚════╝",
    "",
    "                🧸  B O B O - A G E N T  🧸",
]


def print_logo():
    """打印 Logo"""
    width = 70
    for line in PIXEL_BOBO:
        padding = (width - len(line)) // 2
        print(f"  {' ' * padding}{BRIGHT_CYAN}{line}{RESET}")
    print()


def print_session_box(sessions, selected_index):
    """打印会话选择框"""
    width = 70
    border = f"  {BRIGHT_BLACK}┌{'─' * (width - 2)}┐{RESET}"
    bottom = f"  {BRIGHT_BLACK}└{'─' * (width - 2)}┘{RESET}"
    
    print(border)
    print(f"  {BRIGHT_BLACK}│{RESET} {BRIGHT_YELLOW}📋 最近会话{RESET}{' ' * (width - 12)}{BRIGHT_BLACK}│{RESET}")
    print(f"  {BRIGHT_BLACK}│{RESET}{' ' * (width - 2)}{BRIGHT_BLACK}│{RESET}")
    
    for i, session in enumerate(sessions):
        if i == selected_index:
            # 高亮选中
            prefix = f"{BRIGHT_GREEN}▶{RESET}"
            title = f"{BRIGHT_GREEN}{BRIGHT_WHITE}{session['title']}{RESET}"
            time_str = f"{BRIGHT_GREEN}{session['time']}{RESET}"
        else:
            prefix = "  "
            title = f"{BRIGHT_WHITE}{session['title']}{RESET}"
            time_str = f"{BRIGHT_BLACK}{session['time']}{RESET}"
        
        # 计算填充
        content = f"  {prefix} {title}"
        padding = width - len(content) - len(time_str) - 4
        print(f"  {BRIGHT_BLACK}│{RESET} {content}{' ' * padding}{time_str} {BRIGHT_BLACK}│{RESET}")
    
    print(f"  {BRIGHT_BLACK}│{RESET}{' ' * (width - 2)}{BRIGHT_BLACK}│{RESET}")
    print(f"  {BRIGHT_BLACK}│{RESET} {BRIGHT_BLACK}按 ↑/↓ 选择，回车加载，n 新建会话{RESET}{' ' * (width - 32)}{BRIGHT_BLACK}│{RESET}")
    print(bottom)


def simulate_session_selector():
    """模拟会话选择界面"""
    # 清屏
    os.system('clear')
    
    print()
    print_logo()
    
    sessions = [
        {"title": "帮我搜索今天的新闻", "time": "今天 10:30"},
        {"title": "分析这个 Python 文件", "time": "昨天 15:20"},
        {"title": "写一个快速排序算法", "time": "昨天 09:15"},
        {"title": "解释一下递归的概念", "time": "3月20日"},
        {"title": "帮我整理 Obsidian 笔记", "time": "3月19日"},
        {"title": "写一篇关于 AI 的文章", "time": "3月18日"},
    ]
    
    selected = 0
    
    # 这里用输入模拟，实际需要用 getch
    print_session_box(sessions, selected)
    print()
    print(f"  {BRIGHT_BLACK}💡 演示：当前选中第 {selected + 1} 项{RESET}")
    print()
    print(f"  {BRIGHT_BLACK}按回车继续...{RESET}")
    input()


if __name__ == "__main__":
    import os
    simulate_session_selector()
