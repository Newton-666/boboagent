#!/usr/bin/env python3
"""
测试会话选择器 - 支持 ↑/↓ 键选择
"""

import sys
import os
import termios
import tty

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


def get_key():
    """获取单个按键（不按回车）"""
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch == '\x1b':
            ch2 = sys.stdin.read(1)
            if ch2 == '[':
                ch3 = sys.stdin.read(1)
                if ch3 == 'A':
                    return 'UP'
                elif ch3 == 'B':
                    return 'DOWN'
                elif ch3 == 'C':
                    return 'RIGHT'
                elif ch3 == 'D':
                    return 'LEFT'
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def clear_screen():
    os.system('clear')


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
        if padding < 0:
            padding = 0
        print(f"  {BRIGHT_BLACK}│{RESET} {content}{' ' * padding}{time_str} {BRIGHT_BLACK}│{RESET}")
    
    print(f"  {BRIGHT_BLACK}│{RESET}{' ' * (width - 2)}{BRIGHT_BLACK}│{RESET}")
    print(f"  {BRIGHT_BLACK}│{RESET} {BRIGHT_BLACK}↑/↓ 选择，回车加载，n 新建会话，q 退出{RESET}{' ' * (width - 36)}{BRIGHT_BLACK}│{RESET}")
    print(bottom)


def show_session_selector(sessions):
    """显示会话选择器，返回选中的会话索引或 'new' 或 None"""
    selected = 0
    clear_screen()
    
    while True:
        print()
        print_logo()
        print_session_box(sessions, selected)
        print()
        print(f"  {BRIGHT_BLACK}当前选中: {selected + 1}/{len(sessions)}{RESET}")
        print()
        
        key = get_key()
        
        if key == 'UP' and selected > 0:
            selected -= 1
            clear_screen()
        elif key == 'DOWN' and selected < len(sessions) - 1:
            selected += 1
            clear_screen()
        elif key == '\r' or key == '\n':
            return selected
        elif key == 'n' or key == 'N':
            return 'new'
        elif key == 'q' or key == 'Q':
            return None


def main():
    sessions = [
        {"title": "帮我搜索今天的新闻", "time": "今天 10:30"},
        {"title": "分析这个 Python 文件", "time": "昨天 15:20"},
        {"title": "写一个快速排序算法", "time": "昨天 09:15"},
        {"title": "解释一下递归的概念", "time": "3月20日"},
        {"title": "帮我整理 Obsidian 笔记", "time": "3月19日"},
        {"title": "写一篇关于 AI 的文章", "time": "3月18日"},
    ]
    
    print("\n" + "=" * 70)
    print("  测试会话选择器 - 使用 ↑/↓ 键选择")
    print("=" * 70)
    print("\n  按 n 新建会话，按 q 退出\n")
    
    result = show_session_selector(sessions)
    
    if result is None:
        print("\n  👋 再见！")
    elif result == 'new':
        print("\n  ✨ 新建会话")
    else:
        print(f"\n  ✅ 选中: {sessions[result]['title']}")


if __name__ == "__main__":
    main()
