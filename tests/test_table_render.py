#!/usr/bin/env python3
"""
测试表格渲染 - 使用 rich 库
"""

from rich.console import Console
from rich.table import Table
from rich.text import Text
import re

console = Console()


def render_markdown_to_rich(text):
    """将 Markdown 转换为 Rich Text 对象"""
    # 处理粗体 **text**
    parts = re.split(r'(\*\*[^*]+\*\*)', text)
    rich_text = Text()
    for part in parts:
        if part.startswith('**') and part.endswith('**'):
            rich_text.append(part[2:-2], style="bold white")
        else:
            rich_text.append(part)
    return rich_text


def parse_markdown_table(content):
    """解析 Markdown 表格，返回 Rich Table 对象"""
    lines = content.strip().split('\n')
    if len(lines) < 3:
        return None
    
    # 解析表头
    header_line = lines[0].strip()
    if not header_line.startswith('|'):
        return None
    
    headers = [h.strip() for h in header_line.split('|')[1:-1]]
    
    # 解析对齐行
    align_line = lines[1].strip()
    aligns = []
    if align_line.startswith('|'):
        for cell in align_line.split('|')[1:-1]:
            cell = cell.strip()
            if cell.startswith(':') and cell.endswith(':'):
                aligns.append("center")
            elif cell.endswith(':'):
                aligns.append("right")
            else:
                aligns.append("left")
    
    # 创建 Rich Table
    table = Table(show_header=True, header_style="bold cyan", border_style="blue")
    for i, header in enumerate(headers):
        align = aligns[i] if i < len(aligns) else "left"
        table.add_column(render_markdown_to_rich(header), justify=align)
    
    # 添加数据行
    for line in lines[2:]:
        if not line.strip().startswith('|'):
            continue
        cells = [c.strip() for c in line.split('|')[1:-1]]
        if len(cells) == len(headers):
            rich_cells = [render_markdown_to_rich(cell) for cell in cells]
            table.add_row(*rich_cells)
    
    return table


def test_table():
    """测试表格渲染"""
    print("\n" + "=" * 70)
    print("测试: Claude 风格表格渲染")
    print("=" * 70)
    
    table_md = """
| 指标 | 压缩前 | 压缩后 |
|------|--------|--------|
| 行数 | 278 行 | 40 行 |
| 内容 | 逐文件记录每次 ingest | 按主题分组，保留里程碑和关键决策 |
"""
    
    print("\n原始 Markdown:")
    print(table_md)
    
    print("\nRich 渲染:")
    table = parse_markdown_table(table_md)
    if table:
        console.print(table)
    else:
        print("解析失败")


def test_claude_style():
    """测试 Claude 风格的表格"""
    print("\n" + "=" * 70)
    print("测试: Claude 风格完整表格")
    print("=" * 70)
    
    table_md = """
| 指标 | 压缩前 | 压缩后 |
|:-----|:------:|-------:|
| 行数 | 278 行 | 40 行 |
| 内容 | 逐文件记录每次 ingest | 按主题分组，保留里程碑和关键决策 |
| 状态 | **进行中** | `已完成` |
"""
    
    table = parse_markdown_table(table_md)
    if table:
        console.print(table)
    else:
        print("解析失败")


if __name__ == "__main__":
    test_table()
    test_claude_style()
