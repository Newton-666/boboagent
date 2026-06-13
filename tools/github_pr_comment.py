"""Post a review comment on a Pull Request."""

import subprocess
import json

TOOL_NAME = "github_pr_comment"

def execute(pr_number: int, body: str, commit_id: str = "", path: str = "", line: int = 0) -> str:
    """Post a comment or review on a PR."""
    try:
        if path and line:
            # Inline review comment on a specific line
            cmd = [
                "gh", "pr", "review", str(pr_number),
                "--comment", "--body", body,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        else:
            # General PR comment
            cmd = ["gh", "pr", "comment", str(pr_number), "--body", body]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return f"✅ 评论已发布: {result.stdout.strip()}"
        return f"❌ 评论失败: {result.stderr.strip()}"
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
        "description": "在 Pull Request 上发布评论。如果指定 path 和 line，可以针对特定代码行发表评论。需要已安装 gh CLI 并登录。",
        "parameters": {
            "type": "object",
            "properties": {
                "pr_number": {"type": "integer", "description": "PR 编号"},
                "body": {"type": "string", "description": "评论内容"},
                "commit_id": {"type": "string", "description": "提交 SHA（可选，内联评论时需要）"},
                "path": {"type": "string", "description": "文件路径（可选，指定后为内联评论）"},
                "line": {"type": "integer", "description": "行号（可选）"}
            },
            "required": ["pr_number", "body"]
        }
    }
}

def register(reg):
    reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA)
