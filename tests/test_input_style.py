#!/usr/bin/env python3
"""
测试用户输入行的不同样式 - 只高亮输入内容
"""

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

# 背景色
BG_BRIGHT_BLACK = '\033[100m'


def print_separator():
    print(f"  {BRIGHT_BLACK}{'─' * 70}{RESET}")


def test_style_a():
    """方案 A：灰色箭头 + 白色文字"""
    print("\n" + "=" * 70)
    print("方案 A：灰色箭头 + 白色文字")
    print("=" * 70)
    print()
    print(f"  {BRIGHT_BLACK}>{RESET} {BRIGHT_WHITE}In which aspect do you think you are better than claude code{RESET}")
    print()


def test_style_b():
    """方案 B：只高亮输入的文字部分"""
    print("\n" + "=" * 70)
    print("方案 B：只高亮输入的文字部分（灰色背景）")
    print("=" * 70)
    print()
    text = "In which aspect do you think you are better than claude code"
    print(f"  {BRIGHT_BLACK}>{RESET} {BG_BRIGHT_BLACK}{text}{RESET}")
    print()


def test_style_c():
    """方案 C：只高亮输入的文字部分 + 灰色箭头"""
    print("\n" + "=" * 70)
    print("方案 C：灰色箭头 + 高亮文字")
    print("=" * 70)
    print()
    text = "In which aspect do you think you are better than claude code"
    print(f"  {BRIGHT_BLACK}>{RESET} {BG_BRIGHT_BLACK}{text}{RESET}")
    print()


def test_in_context():
    """在完整上下文中展示"""
    print("\n" + "=" * 70)
    print("在完整上下文中（方案 C）")
    print("=" * 70)
    print()
    print(f"  {BRIGHT_BLACK}{'─' * 70}{RESET}")
    text = "In which aspect do you think you are better than claude code"
    print(f"  {BRIGHT_BLACK}>{RESET} {BG_BRIGHT_BLACK}{text}{RESET}")
    print(f"  {BRIGHT_BLACK}{'─' * 70}{RESET}")
    print(f"  {BRIGHT_YELLOW}├─ thinking (5s){RESET}")
    print()
    print(f"  {BRIGHT_GREEN}{BOLD}●{RESET} Good question. Here's where I think I have advantages...")
    print()


if __name__ == "__main__":
    test_style_a()
    test_style_b()
    test_style_c()
    test_in_context()
    
    print("\n" + "=" * 70)
    print("推荐：方案 C")
    print("=" * 70)
    print("""
  效果：
    > 灰色箭头 + 高亮文字
    > 背景只覆盖输入内容，不覆盖整行
    > 与整体风格一致
    """)
