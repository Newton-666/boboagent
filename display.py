#!/usr/bin/env python3
"""
display.py - UI 显示模块
"""

import sys
import re
import time
import json
from rich.console import Console
from rich.table import Table
from rich.text import Text

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

_console = Console()


def render_markdown(text):
    if not text:
        return text
    text = re.sub(r'\*\*([^*]+)\*\*', f'{BOLD}{BRIGHT_WHITE}\\1{RESET}', text)
    text = re.sub(r'`([^`]+)`', f'{BRIGHT_GREEN}{BOLD}\\1{RESET}', text)
    return text


def render_markdown_to_rich(text):
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
    lines = content.strip().split('\n')
    if len(lines) < 3:
        return None
    
    header_line = None
    align_line = None
    data_lines = []
    
    for line in lines:
        if line.strip().startswith('|'):
            if header_line is None:
                header_line = line
            elif align_line is None and '---' in line:
                align_line = line
            else:
                data_lines.append(line)
    
    if not header_line:
        return None
    
    headers = [h.strip() for h in header_line.split('|')[1:-1]]
    
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
    
    table = Table(show_header=True, header_style="bold cyan", border_style="blue")
    for i, header in enumerate(headers):
        justify = aligns[i] if i < len(aligns) else "left"
        table.add_column(render_markdown_to_rich(header), justify=justify)
    
    for line in data_lines:
        cells = [c.strip() for c in line.split('|')[1:-1]]
        if len(cells) == len(headers):
            rich_cells = [render_markdown_to_rich(cell) for cell in cells]
            table.add_row(*rich_cells)
    
    return table


def print_separator():
    print(f"  {BRIGHT_BLACK}{'─' * 70}{RESET}")


def print_logo():
    width = 70
    for line in PIXEL_BOBO:
        padding = (width - len(line)) // 2
        if padding < 0:
            padding = 0
        print(f"  {' ' * padding}{BRIGHT_CYAN}{line}{RESET}")
    print()


def print_thinking_line(seconds):
    print(f"  {BRIGHT_YELLOW}├─ thinking ({seconds}s){RESET}")


def print_step(title):
    print(f"  {BRIGHT_BLACK}│{RESET}")
    print(f"  {BRIGHT_BLACK}│{RESET}  {BRIGHT_YELLOW}▶{RESET} {title}")


def print_tool(name, query, status="running", duration=None, output=None):
    if status == "running":
        print(f"  {BRIGHT_BLACK}│{RESET}    {BRIGHT_CYAN}⚙ {name}{RESET} {BRIGHT_BLACK}({query}){RESET}")
    elif status == "success":
        if duration:
            print(f"  {BRIGHT_BLACK}│{RESET}      {BRIGHT_GREEN}✓{RESET} {BRIGHT_BLACK}done ({duration:.1f}s){RESET}")
        else:
            print(f"  {BRIGHT_BLACK}│{RESET}      {BRIGHT_GREEN}✓{RESET} {BRIGHT_BLACK}done{RESET}")
        if output:
            print(f"  {BRIGHT_BLACK}│{RESET}        {output[:100]}")
    elif status == "error":
        print(f"  {BRIGHT_BLACK}│{RESET}      {BRIGHT_RED}✗{RESET} {BRIGHT_BLACK}{query}{RESET}")


def print_step_done(title):
    print(f"  {BRIGHT_BLACK}│{RESET}    {BRIGHT_GREEN}✓{RESET} {BRIGHT_BLACK}{title}{RESET}")


def print_tree_end():
    print(f"  {BRIGHT_BLACK}│{RESET}")
    print(f"  {BRIGHT_BLACK}└─{RESET}")


def print_code_block(code):
    print()
    for line in code.split('\n')[:20]:
        print(f"  {BRIGHT_GREEN}{BOLD}{line}{RESET}")
    if len(code.split('\n')) > 20:
        print(f"  {BRIGHT_BLACK}... (共 {len(code.split(chr(10)))} 行){RESET}")
    print()


def print_simple_text(content, delay=0.02):
    lines = content.split('\n')
    first = True
    for line in lines:
        if not line.strip():
            print()
            continue
        rendered = render_markdown(line)
        if first:
            print(f"  {BRIGHT_GREEN}{BOLD}●{RESET} {rendered}", flush=True)
            first = False
        else:
            print(f"     {rendered}", flush=True)
        time.sleep(delay)


def print_assistant(content):
    if not content:
        return
    
    code_pattern = r'```(html|python|javascript)\n(.*?)\n```'
    code_match = re.search(code_pattern, content, re.DOTALL)
    
    if code_match:
        code = code_match.group(2)
        before_code = content[:code_match.start()].strip()
        after_code = content[code_match.end():].strip()
        
        if before_code:
            print_assistant(before_code)
        print_code_block(code)
        if after_code:
            print_assistant(after_code)
        return
    
    if '|' in content and '---' in content:
        lines = content.split('\n')
        in_table = False
        table_lines = []
        other_lines = []
        current = other_lines
        
        for line in lines:
            if line.strip().startswith('|') and not in_table:
                if current:
                    other_lines.extend(current)
                current = table_lines
                in_table = True
                current.append(line)
            elif in_table and line.strip() and not line.strip().startswith('|'):
                in_table = False
                current = other_lines
                current.append(line)
            else:
                current.append(line)
        
        if other_lines:
            other_text = '\n'.join(other_lines).strip()
            if other_text:
                print_simple_text(other_text)
        
        if table_lines:
            table_text = '\n'.join(table_lines)
            table = parse_markdown_table(table_text)
            if table:
                print(f"  {BRIGHT_GREEN}{BOLD}●{RESET} ", end="")
                _console.print(table)
                print()
            else:
                print_simple_text(table_text)
    else:
        print_simple_text(content)


def print_session_box(sessions, selected_index):
    width = 70
    border = f"  {BRIGHT_BLACK}┌{'─' * (width - 2)}┐{RESET}"
    bottom = f"  {BRIGHT_BLACK}└{'─' * (width - 2)}┘{RESET}"
    
    print(border)
    print(f"  {BRIGHT_BLACK}│{RESET} {BRIGHT_YELLOW}📋 最近会话{RESET}{' ' * (width - 12)}{BRIGHT_BLACK}│{RESET}")
    print(f"  {BRIGHT_BLACK}│{RESET}{' ' * (width - 2)}{BRIGHT_BLACK}│{RESET}")
    
    for i, session in enumerate(sessions):
        if i == selected_index:
            prefix = f"{BRIGHT_GREEN}▶{RESET}"
            title = f"{BRIGHT_GREEN}{BRIGHT_WHITE}{session['title']}{RESET}"
            time_str = f"{BRIGHT_GREEN}{session['time']}{RESET}"
        else:
            prefix = "  "
            title = f"{BRIGHT_WHITE}{session['title']}{RESET}"
            time_str = f"{BRIGHT_BLACK}{session['time']}{RESET}"
        
        content = f"  {prefix} {title}"
        padding = width - len(content) - len(time_str) - 4
        if padding < 0:
            padding = 0
        print(f"  {BRIGHT_BLACK}│{RESET} {content}{' ' * padding}{time_str} {BRIGHT_BLACK}│{RESET}")
    
    print(f"  {BRIGHT_BLACK}│{RESET}{' ' * (width - 2)}{BRIGHT_BLACK}│{RESET}")
    print(f"  {BRIGHT_BLACK}│{RESET} {BRIGHT_BLACK}↑/↓ 选择，回车加载，n 新建会话，q 退出{RESET}{' ' * (width - 36)}{BRIGHT_BLACK}│{RESET}")
    print(bottom)


def print_help():
    help_text = f"""
{BRIGHT_CYAN}╔══════════════════════════════════════════════════════════════════╗
║                      🧸 Bobo 帮助中心 🧸                        ║
╚══════════════════════════════════════════════════════════════════╝{RESET}

{BRIGHT_YELLOW}📋 会话管理{RESET}
─────────────────────────────────────────────────────────────────
  /new                    新建会话
  /list                   列出所有历史会话
  /resume <id>            恢复指定会话

{BRIGHT_YELLOW}✏️ 消息编辑{RESET}
─────────────────────────────────────────────────────────────────
  /undo                   撤销最后一条消息
  ↑ 键                    查看历史输入

{BRIGHT_YELLOW}⚡ 执行控制{RESET}
─────────────────────────────────────────────────────────────────
  Ctrl+C                  打断当前操作
  Ctrl+T                  切换思考过程显示（展开/收起）

{BRIGHT_YELLOW}🔧 工具{RESET}
─────────────────────────────────────────────────────────────────
  /tools                  列出所有可用工具

{BRIGHT_YELLOW}ℹ️ 其他{RESET}
─────────────────────────────────────────────────────────────────
  /help                   显示此帮助
  /exit                   退出 Bobo
"""
    print(help_text)


def print_tools_list():
    from tools import TOOLS_SCHEMA
    print(f"\n{BRIGHT_CYAN}🔧 可用工具列表:{RESET}")
    for tool in TOOLS_SCHEMA:
        name = tool['function']['name']
        desc = tool['function']['description'][:50]
        print(f"   • {name}: {desc}...")
