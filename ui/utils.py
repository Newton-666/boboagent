"""UI 工具函数：终端操作、颜色常量、按键读取"""

import sys
import os
import termios
import tty

# 颜色常量
BRIGHT_YELLOW = '\033[93m'
BRIGHT_GREEN = '\033[92m'
BRIGHT_BLACK = '\033[90m'
BRIGHT_MAGENTA = '\033[95m'
BRIGHT_CYAN = '\033[96m'
BRIGHT_WHITE = '\033[97m'
RESET = '\033[0m'
BOLD = '\033[1m'


def get_key():
    """读取单个按键，支持方向键"""
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
    except:
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def clear_line():
    """清除当前行"""
    sys.stdout.write('\r\033[K')
    sys.stdout.flush()


def clear_screen():
    """清屏"""
    os.system('clear')


def get_terminal_width():
    """获取终端宽度"""
    try:
        return os.get_terminal_size().columns
    except:
        return 80
