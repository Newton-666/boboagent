"""Create a pull request from the current branch."""

import subprocess

TOOL_NAME = "github_create_pr"

def execute(title: str, body: str = "", base: str = "main") -> str:
    """Create a pull request."""
    try:
        cmd = ["gh", "pr", "create", "--title", title, "--base", base, "--fill"]
        if body:
            cmd = ["gh", "pr", "create", "--title", title, "--body", body, "--base", base]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return f"✅ PR 已创建: {result.stdout.strip()}"
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
        "description": "从当前分支创建一个 Pull Request。需要已安装 gh CLI 并登录。",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "PR 标题"},
                "body": {"type": "string", "description": "PR 描述"},
                "base": {"type": "string", "description": "目标分支（默认 main）"}
            },
            "required": ["title"]
        }
    }
}

def register(reg):
    reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA)
