"""Fetch the diff of a pull request for code review."""

import subprocess

TOOL_NAME = "github_pr_diff"

def execute(pr_number: int = 0, repo: str = "") -> str:
    """Fetch the diff of a pull request."""
    try:
        cmd = ["gh", "pr", "diff", str(pr_number)] if pr_number else ["gh", "pr", "diff"]
        if repo:
            cmd = ["gh", "pr", "diff", "-R", repo, str(pr_number)] if pr_number else ["gh", "pr", "diff", "-R", repo]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            diff = result.stdout.strip()
            if not diff:
                return "ℹ️ PR 没有差异内容"
            if len(diff) > 8000:
                diff = diff[:8000] + "\n... (差异内容过长，已截断)"
            return diff
        return f"❌ 获取失败: {result.stderr.strip()}"
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
        "description": "获取当前仓库一个 Pull Request 的代码差异，用于代码审查。需要已安装 gh CLI 并登录。",
        "parameters": {
            "type": "object",
            "properties": {
                "pr_number": {"type": "integer", "description": "PR 编号，默认为当前分支的 PR"},
                "repo": {"type": "string", "description": "仓库（如 'owner/repo'），默认当前仓库"}
            },
            "required": []
        }
    }
}

def register(reg):
    reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA)
