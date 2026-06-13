"""Create a GitHub repository and push the current branch."""

import subprocess
import os

TOOL_NAME = "github_create_repo"

def execute(name: str, description: str = "", public: bool = True) -> str:
    """Create a GitHub repo and push the current branch."""
    visibility = "--public" if public else "--private"
    try:
        result = subprocess.run(
            ["gh", "repo", "create", name, visibility, "--source=.", "--push"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            return f"✅ 已创建仓库: {name}\n{result.stdout.strip()}"
        return f"❌ 创建失败: {result.stderr.strip()}"
    except FileNotFoundError:
        return "❌ 需要安装 GitHub CLI (gh)"
    except subprocess.TimeoutExpired:
        return "❌ 操作超时"
    except Exception as e:
        return f"❌ 错误: {str(e)}"


TOOL_FUNC = execute
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": "在 GitHub 上创建仓库并推送当前代码。需要已安装 gh CLI 并登录。",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "仓库名称，如 'bobo-agent'"},
                "description": {"type": "string", "description": "可选描述"},
                "public": {"type": "boolean", "description": "是否公开（默认是）"}
            },
            "required": ["name"]
        }
    }
}

def register(reg):
    reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA)
