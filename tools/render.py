"""渲染工具 - 简化版"""

import sys
import time
import re

TOOL_NAME = "render"

# LaTeX 转换（简化）
LATEX_TO_UNICODE = {
    r'\pi': 'π', r'\alpha': 'α', r'\beta': 'β', r'\gamma': 'γ',
    r'\sum': '∑', r'\int': '∫', r'\infty': '∞', r'\sqrt': '√',
    r'\rightarrow': '→', r'\leftarrow': '←', r'\approx': '≈', r'\neq': '≠',
}

SUP_MAP = {'0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴',
           '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹',
           'i': 'ⁱ', 'e': 'ᵉ', 'n': 'ⁿ'}

def latex_to_unicode(text: str) -> str:
    result = text
    for latex, uni in LATEX_TO_UNICODE.items():
        result = result.replace(latex, uni)
    result = re.sub(r'\^\{([^}]+)\}', lambda m: ''.join(SUP_MAP.get(ch, ch) for ch in m.group(1)), result)
    result = re.sub(r'\^([a-z0-9])', lambda m: SUP_MAP.get(m.group(1), m.group(1)), result)
    result = re.sub(r'\$([^$]+)\$', r'\1', result)
    return result


def render_markdown(content: str) -> str:
    """渲染 Markdown（不渲染表格）"""
    content = latex_to_unicode(content)
    content = re.sub(r'\*\*([^*]+)\*\*', r'\033[1m\1\033[0m', content)
    content = re.sub(r'\*([^*]+)\*', r'\033[3m\1\033[0m', content)
    content = re.sub(r'`([^`]+)`', r'\033[36m\1\033[0m', content)
    return content


def execute(data: dict) -> str:
    content = data.get("content", "")
    data_type = data.get("type", "text")
    stream = data.get("stream", False)
    
    if data_type == "markdown":
        rendered = render_markdown(content)
    elif data_type == "error":
        rendered = f"\033[91m❌ {content}\033[0m"
    else:
        rendered = content
    
    if stream:
        print(f"\n  🐻 Bobo · ", end="")
        sys.stdout.flush()
        for ch in rendered:
            sys.stdout.write(ch)
            sys.stdout.flush()
            time.sleep(0.005)
        print()
        return ""
    else:
        return rendered


def register(reg):
    reg("render", execute, {
        "type": "function",
        "function": {
            "name": "render",
            "description": "渲染内容为可见格式",
            "parameters": {"type": "object", "properties": {"data": {"type": "object"}}, "required": ["data"]}
        }
    })

def remove_tables(text: str) -> str:
    """移除 Markdown 表格"""
    lines = text.split('\n')
    result = []
    in_table = False
    for line in lines:
        if line.strip().startswith('|') and '|' in line:
            in_table = True
            continue
        if in_table and line.strip() == '':
            in_table = False
            continue
        if not in_table:
            result.append(line)
    return '\n'.join(result)

# 修改 render_markdown，先移除表格
original_render_markdown = render_markdown
def render_markdown(content: str) -> str:
    content = remove_tables(content)
    return original_render_markdown(content)
