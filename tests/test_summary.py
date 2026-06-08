#!/usr/bin/env python3
"""
测试会话总结 - 渐进式显示
"""

import sys
import os
import time
import threading


from core.llm_caller import create_llm_caller
from config import API_KEY, API_BASE_URL, API_MODEL_NAME

# 颜色
YELLOW = '\033[93m'
BRIGHT_BLACK = '\033[90m'
BRIGHT_GREEN = '\033[92m'
RESET = '\033[0m'
BOLD = '\033[1m'


def print_box(title, lines, progress=None):
    """打印边框盒子，支持进度条"""
    width = 68
    border = f"  {BRIGHT_BLACK}┌{'─' * width}┐{RESET}"
    bottom = f"  {BRIGHT_BLACK}└{'─' * width}┘{RESET}"
    
    # 清空当前行
    sys.stdout.write('\r\033[K')
    
    print(border)
    print(f"  {BRIGHT_BLACK}│{RESET} {YELLOW}{title}{RESET}{' ' * (width - len(title) - 2)}{BRIGHT_BLACK}│{RESET}")
    
    if progress:
        # 显示进度条
        bar = '█' * progress + '░' * (10 - progress)
        print(f"  {BRIGHT_BLACK}│{RESET}   {BRIGHT_BLACK}{bar} 正在分析历史记录...{RESET}{' ' * (width - 28)}{BRIGHT_BLACK}│{RESET}")
    else:
        for line in lines:
            display_line = line[:width-4] if len(line) > width-4 else line
            print(f"  {BRIGHT_BLACK}│{RESET}   {display_line:<{width-4}}{BRIGHT_BLACK}│{RESET}")
    
    print(bottom)
    # 回到顶部覆盖
    sys.stdout.write(f'\033[{len(lines)+4}F')
    sys.stdout.flush()


def animate_summary(lines):
    """动画显示摘要，逐行出现"""
    width = 68
    border = f"  {BRIGHT_BLACK}┌{'─' * width}┐{RESET}"
    bottom = f"  {BRIGHT_BLACK}└{'─' * width}┘{RESET}"
    
    # 打印空盒子
    print(border)
    print(f"  {BRIGHT_BLACK}│{RESET} {YELLOW}📋 上次会话总结{RESET}{' ' * (width - 14)}{BRIGHT_BLACK}│{RESET}")
    
    # 预留行空间
    for _ in range(len(lines)):
        print(f"  {BRIGHT_BLACK}│{RESET}{' ' * width}{BRIGHT_BLACK}│{RESET}")
    
    print(bottom)
    
    # 逐行覆盖写入
    for i, line in enumerate(lines):
        display_line = line[:width-4] if len(line) > width-4 else line
        # 移动到对应行
        sys.stdout.write(f'\033[{i+3};0H')
        sys.stdout.write(f"  {BRIGHT_BLACK}│{RESET}   {display_line:<{width-4}}{BRIGHT_BLACK}│{RESET}")
        sys.stdout.flush()
        time.sleep(0.15)
    
    # 移动回底部
    sys.stdout.write(f'\033[{len(lines)+4};0H')
    sys.stdout.flush()


def summarize_history(messages, callback=None):
    """调用 LLM 生成摘要"""
    llm = create_llm_caller(API_KEY, API_BASE_URL, API_MODEL_NAME, tools_schema=None)
    
    history_str = ""
    for msg in messages[-12:]:
        role = "用户" if msg['role'] == 'user' else "Bobo"
        content = msg['content'][:100].replace('\n', ' ')
        history_str += f"{role}: {content}\n"
    
    prompt = f"""根据以下对话，用3-5个要点总结。

对话：
{history_str}

要求：每个要点用 - 开头，每条不超过30字，只输出要点。"""

    response = llm([{"role": "user", "content": prompt}], use_tools=False)
    
    if isinstance(response, dict) and 'error' not in response:
        content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
        return content
    return ""


def main():
    # 模拟历史消息
    mock_messages = [
        {"role": "user", "content": "帮我测试终端命令 echo Hello"},
        {"role": "assistant", "content": "执行成功: Hello"},
        {"role": "user", "content": "写一个计算器网页"},
        {"role": "assistant", "content": "已生成 HTML/CSS/JS 代码"},
        {"role": "user", "content": "搜索 Python 教程"},
        {"role": "assistant", "content": "找到 5 个相关结果"},
        {"role": "user", "content": "修复重复打印问题"},
        {"role": "assistant", "content": "已添加防重复逻辑，问题解决"},
        {"role": "user", "content": "添加表格渲染"},
        {"role": "assistant", "content": "已集成 rich 表格渲染"},
    ]
    
    # 模拟进度条
    print()
    for i in range(1, 11):
        print_box("📋 上次会话总结", [], progress=i)
        time.sleep(0.08)
    
    # 清除进度条行
    sys.stdout.write('\033[K')
    
    # 生成摘要
    summary = summarize_history(mock_messages)
    lines = [line.strip() for line in summary.strip().split('\n') if line.strip()]
    
    if lines:
        animate_summary(lines)
    else:
        print(f"  {BRIGHT_BLACK}无历史记录{RESET}")


if __name__ == "__main__":
    main()
