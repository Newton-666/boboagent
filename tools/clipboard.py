"""剪贴板工具"""

import subprocess

TOOL_NAME = "clipboard"

def read() -> str:
    """读取剪贴板内容"""
    try:
        result = subprocess.run(['pbpaste'], capture_output=True, text=True)
        return result.stdout if result.stdout else "剪贴板为空"
    except:
        return "❌ 读取剪贴板失败"

def write(content: str) -> str:
    """写入剪贴板"""
    try:
        process = subprocess.Popen(['pbcopy'], stdin=subprocess.PIPE)
        process.communicate(content.encode())
        return f"✅ 已写入剪贴板: {content[:50]}..."
    except:
        return "❌ 写入剪贴板失败"

_check = lambda: __import__('sys').platform == 'darwin'

def register(reg):
    reg("read_clipboard", read, {
        "type": "function",
        "function": {
            "name": "read_clipboard",
            "description": "读取系统剪贴板内容。适用场景：用户说'看看我复制了什么'、'读取剪贴板'。",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    }, check_fn=_check)
    reg("write_clipboard", write, {
        "type": "function",
        "function": {
            "name": "write_clipboard",
            "description": "写入内容到系统剪贴板。适用场景：用户要求'复制这段内容'、'把这个放到剪贴板'。",
            "parameters": {"type": "object", "properties": {"content": {"type": "string"}}, "required": ["content"]}
        }
    }, check_fn=_check)
