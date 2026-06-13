"""Get git status, diff, and branch info for the current project."""

import subprocess
import os

TOOL_NAME = "git_status"

def execute(path: str = "") -> str:
    """返回当前 git 仓库的状态摘要"""
    cwd = path or os.getcwd()
    parts = []
    
    # 当前分支
    try:
        branch = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True, text=True, cwd=cwd, timeout=5
        )
        if branch.returncode == 0 and branch.stdout.strip():
            parts.append(f"分支: {branch.stdout.strip()}")
    except Exception:
        pass
    
    # git status --short
    try:
        status = subprocess.run(
            ["git", "status", "--short"],
            capture_output=True, text=True, cwd=cwd, timeout=5
        )
        if status.returncode == 0 and status.stdout.strip():
            lines = status.stdout.strip().split("\n")
            parts.append(f"变更: {len(lines)} 个文件")
            for line in lines[:20]:
                parts.append(f"  {line}")
    except Exception:
        pass
    
    # git diff --stat
    try:
        diff_stat = subprocess.run(
            ["git", "diff", "--stat"],
            capture_output=True, text=True, cwd=cwd, timeout=5
        )
        if diff_stat.returncode == 0 and diff_stat.stdout.strip():
            parts.append(f"\n未暂存的变更:\n{diff_stat.stdout.strip()}")
    except Exception:
        pass
    
    return "\n".join(parts) if parts else "（不是 git 仓库或无变更）"


TOOL_FUNC = execute
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": "获取当前 git 仓库的分支、变更文件和未暂存的改动摘要。在一轮编程任务开始时调用。",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "仓库路径，默认当前目录"}
            },
            "required": []
        }
    }
}

def register(reg):
    reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA)
