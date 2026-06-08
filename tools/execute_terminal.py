"""执行终端命令（高风险操作，需要用户确认）"""

import subprocess
import shlex
import re

TOOL_NAME = "execute_terminal"

# 真正危险的命令模式
DANGEROUS_PATTERNS = [
    r'rm\s+(-rf?|--recursive)\s+',      # rm -rf /path
    r'sudo\s+',                          # sudo 命令
    r'chmod\s+777\s+',                   # chmod 777
    r'chown\s+',                         # chown
    r'dd\s+of=',                         # dd 写入
    r'>\s*/dev/',                        # 写入设备
    r':\s*\(\s*\)\s*:\s*',               # fork bomb
    r'\|\s*sh\s*',                       # pipe to sh
    r'\|\s*bash\s*',                     # pipe to bash
]

def is_dangerous(command: str) -> bool:
    """检查命令是否危险"""
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, command):
            return True
    return False

def execute(command: str, timeout: int = 30) -> str:
    """执行终端命令并返回输出"""
    try:
        # 检查是否危险命令
        if is_dangerous(command):
            return f"⚠️ 危险命令: {command}\n此命令需要用户明确确认。"
        
        # 使用 shell 执行（支持管道、重定向）
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            executable='/bin/bash'
        )
        
        output = ""
        if result.stdout:
            output = result.stdout
        if result.stderr:
            if output:
                output += "\n[stderr]\n"
            output += result.stderr
        
        if not output:
            output = "(命令执行成功，无输出)"
        
        if len(output) > 8000:
            output = output[:8000] + "\n... (输出被截断)"
        
        return output.strip()
        
    except subprocess.TimeoutExpired:
        return f"命令执行超时（{timeout}秒）"
    except Exception as e:
        return f"执行失败: {str(e)}"


TOOL_FUNC = execute
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": """【用途】在终端中执行命令。
【适用场景】用户要求"运行XX命令"、"执行XX"、"查看系统信息"等。
【支持】管道(|)、重定向(>)、变量($) 等 shell 特性。
【注意】rm -rf, sudo, chmod 777 等危险命令会被拦截。""",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "要执行的命令，例如 'ls -la' 或 'ps aux | grep python'"
                },
                "timeout": {
                    "type": "integer",
                    "description": "超时时间（秒），默认30秒"
                }
            },
            "required": ["command"]
        }
    }
}


def register(reg):
    reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA)
