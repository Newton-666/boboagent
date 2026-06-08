#!/usr/bin/env python3
"""
1:1 真实测试 - 粗体渲染（不处理表格，保持原样）
"""

import sys
import os
import re
import time


from core.llm_caller import create_llm_caller
from config import API_KEY, API_BASE_URL, API_MODEL_NAME
from tools import TOOLS_SCHEMA

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


def render_markdown(text):
    """渲染粗体和代码"""
    if not text:
        return text
    text = re.sub(r'\*\*([^*]+)\*\*', f'{BOLD}{BRIGHT_WHITE}\\1{RESET}', text)
    text = re.sub(r'`([^`]+)`', f'{BRIGHT_GREEN}{BOLD}\\1{RESET}', text)
    return text


def print_code(code):
    """打印代码块"""
    print()
    for line in code.split('\n')[:20]:
        print(f"  {BRIGHT_GREEN}{BOLD}{line}{RESET}")
    if len(code.split('\n')) > 20:
        print(f"  {BRIGHT_BLACK}... (共 {len(code.split(chr(10)))} 行){RESET}")
    print()


def print_assistant_line_by_line(content, delay=0.02):
    """按行打印，每行渲染粗体和代码"""
    lines = content.split('\n')
    
    for i, line in enumerate(lines):
        rendered = render_markdown(line)
        if i == 0:
            print(f"  {BRIGHT_GREEN}{BOLD}●{RESET} {rendered}", flush=True)
        else:
            print(f"     {rendered}", flush=True)
        time.sleep(delay)
    
    print()


def print_assistant(content, success=True):
    """完整打印助手消息"""
    code_pattern = r'```(html|python|javascript)\n(.*?)\n```'
    match = re.search(code_pattern, content, re.DOTALL)
    
    if match:
        lang = match.group(1)
        code = match.group(2)
        before_code = content[:match.start()].strip()
        after_code = content[match.end():].strip()
        
        if before_code:
            print_assistant_line_by_line(before_code)
        print_code(code)
        if after_code:
            print_assistant_line_by_line(after_code)
    else:
        print_assistant_line_by_line(content)


def print_separator():
    print(f"  {BRIGHT_BLACK}{'─' * 70}{RESET}")


def test_bold_rendering():
    """测试粗体渲染"""
    print("\n" + "=" * 70)
    print("测试 1: 粗体渲染")
    print("=" * 70)
    
    test_content = "这是 **粗体文字** 测试，还有 `代码块` 测试。"
    print(f"\n  原文: {test_content}")
    print(f"\n  渲染后:")
    print_assistant_line_by_line(test_content)


def test_table_preserve():
    """测试表格保持原样"""
    print("\n" + "=" * 70)
    print("测试 2: 表格保持原样（不做转换）")
    print("=" * 70)
    
    table = """| 语言 | 特点 | 状态 |
|------|------|------|
| Python | **简单** | 活跃 |
| JavaScript | `灵活` | 流行 |
| Rust | **高性能** | 新兴 |"""
    
    print(f"\n  表格内容:")
    print_assistant_line_by_line(table)


def test_real_llm():
    """测试真实 LLM 响应"""
    print("\n" + "=" * 70)
    print("测试 3: 真实 LLM 响应")
    print("=" * 70)
    
    llm = create_llm_caller(API_KEY, API_BASE_URL, API_MODEL_NAME, TOOLS_SCHEMA)
    
    prompt = "用中文介绍 3 种编程语言，用 **粗体** 标记重点。"
    messages = [{"role": "user", "content": prompt}]
    
    print("\n  调用 LLM...")
    response = llm(messages)
    
    if isinstance(response, dict):
        content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
    else:
        content = str(response)
    
    print(f"\n  渲染输出:")
    print_separator()
    print_assistant(content)
    print_separator()


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("1:1 真实测试 - 粗体渲染")
    print("=" * 70)
    
    test_bold_rendering()
    test_table_preserve()
    test_real_llm()
    
    print("\n" + "=" * 70)
    print("测试完成")
    print("=" * 70)
