#!/usr/bin/env python3
"""
真实测试：表格渲染
模拟 Bobo 实际使用场景
"""

import sys
import os
import re
import time


from rich.console import Console
from rich.table import Table
from rich.text import Text
from rich import print as rprint
from core.llm_caller import create_llm_caller
from config import API_KEY, API_BASE_URL, API_MODEL_NAME
from tools import TOOLS_SCHEMA

# 颜色 (用于非表格内容)
RESET = '\033[0m'
BOLD = '\033[1m'
BRIGHT_GREEN = '\033[92m'
BRIGHT_WHITE = '\033[97m'
BRIGHT_BLACK = '\033[90m'

console = Console()


def render_markdown_to_rich(text):
    """将 Markdown 转换为 Rich Text"""
    parts = re.split(r'(\*\*[^*]+\*\*|`[^`]+`)', text)
    rich_text = Text()
    for part in parts:
        if part.startswith('**') and part.endswith('**'):
            rich_text.append(part[2:-2], style="bold white")
        elif part.startswith('`') and part.endswith('`'):
            rich_text.append(part[1:-1], style="green bold")
        else:
            rich_text.append(part)
    return rich_text


def parse_markdown_table(content):
    """解析 Markdown 表格为 Rich Table"""
    lines = content.strip().split('\n')
    if len(lines) < 3:
        return None
    
    # 找表头行
    header_line = None
    align_line = None
    data_lines = []
    
    for i, line in enumerate(lines):
        if line.strip().startswith('|'):
            if header_line is None:
                header_line = line
            elif align_line is None and '---' in line:
                align_line = line
            else:
                data_lines.append(line)
    
    if not header_line:
        return None
    
    # 解析表头
    headers = [h.strip() for h in header_line.split('|')[1:-1]]
    
    # 解析对齐
    aligns = []
    if align_line:
        for cell in align_line.split('|')[1:-1]:
            cell = cell.strip()
            if cell.startswith(':') and cell.endswith(':'):
                aligns.append("center")
            elif cell.endswith(':'):
                aligns.append("right")
            else:
                aligns.append("left")
    else:
        aligns = ["left"] * len(headers)
    
    # 创建表格
    table = Table(show_header=True, header_style="bold cyan", border_style="blue")
    for i, header in enumerate(headers):
        justify = aligns[i] if i < len(aligns) else "left"
        table.add_column(render_markdown_to_rich(header), justify=justify)
    
    # 添加数据
    for line in data_lines:
        cells = [c.strip() for c in line.split('|')[1:-1]]
        if len(cells) == len(headers):
            rich_cells = [render_markdown_to_rich(cell) for cell in cells]
            table.add_row(*rich_cells)
    
    return table


def print_assistant_with_table(content):
    """智能打印：检测表格用 rich，其他用普通打印"""
    # 检测是否包含表格
    if '|' in content and '---' in content:
        # 提取表格部分
        lines = content.split('\n')
        in_table = False
        table_lines = []
        other_lines = []
        current_lines = other_lines
        
        for line in lines:
            if line.strip().startswith('|') and not in_table:
                # 开始表格
                if current_lines:
                    other_lines.extend(current_lines)
                current_lines = table_lines
                in_table = True
                current_lines.append(line)
            elif in_table and line.strip() and not line.strip().startswith('|'):
                # 表格结束
                in_table = False
                current_lines = other_lines
                current_lines.append(line)
            else:
                current_lines.append(line)
        
        # 打印非表格内容
        if other_lines:
            non_table = '\n'.join(other_lines).strip()
            if non_table:
                print_assistant_text(non_table)
        
        # 打印表格
        if table_lines:
            table_text = '\n'.join(table_lines)
            table = parse_markdown_table(table_text)
            if table:
                console.print(table)
            else:
                print_assistant_text(table_text)
    else:
        print_assistant_text(content)


def print_assistant_text(content, delay=0.02):
    """普通文本打印（逐行，带粗体）"""
    def render_simple(text):
        text = re.sub(r'\*\*([^*]+)\*\*', f'{BOLD}{BRIGHT_WHITE}\\1{RESET}', text)
        text = re.sub(r'`([^`]+)`', f'{BRIGHT_GREEN}{BOLD}\\1{RESET}', text)
        return text
    
    lines = content.split('\n')
    for i, line in enumerate(lines):
        rendered = render_simple(line)
        if i == 0:
            print(f"  {BRIGHT_GREEN}{BOLD}●{RESET} {rendered}", flush=True)
        else:
            print(f"     {rendered}", flush=True)
        time.sleep(delay)
    print()


def print_separator():
    print(f"  {BRIGHT_BLACK}{'─' * 70}{RESET}")


def test_with_llm():
    """真实测试：让 LLM 返回包含表格的响应"""
    print("\n" + "=" * 70)
    print("真实测试：LLM 返回表格")
    print("=" * 70)
    
    llm = create_llm_caller(API_KEY, API_BASE_URL, API_MODEL_NAME, TOOLS_SCHEMA)
    
    prompt = """请用表格形式对比 Python、JavaScript、Rust 三种语言，格式如下：

| 语言 | 类型 | 主要用途 | 特点 |
|------|------|----------|------|
| Python | 解释型 | 数据分析 | **简单易学** |
| JavaScript | 解释型 | 网页开发 | `事件驱动` |
| Rust | 编译型 | 系统编程 | **内存安全** |

请直接返回表格，不要有其他内容。"""
    
    messages = [{"role": "user", "content": prompt}]
    
    print("\n调用 LLM...")
    response = llm(messages)
    
    if isinstance(response, dict):
        content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
    else:
        content = str(response)
    
    print(f"\n渲染结果:")
    print_separator()
    print_assistant_with_table(content)
    print_separator()


def test_static_table():
    """测试静态表格"""
    print("\n" + "=" * 70)
    print("测试：静态表格")
    print("=" * 70)
    
    table_content = """
| 指标 | 压缩前 | 压缩后 |
|------|--------|--------|
| 行数 | 278 行 | 40 行 |
| 内容 | 逐文件记录每次 ingest | 按主题分组，保留里程碑和关键决策 |
"""
    
    print("\n渲染结果:")
    print_separator()
    print_assistant_with_table(table_content)
    print_separator()


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("表格渲染真实测试")
    print("=" * 70)
    
    test_static_table()
    test_with_llm()
    
    print("\n" + "=" * 70)
    print("测试完成")
    print("=" * 70)
