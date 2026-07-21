"""Configure GitHub CLI with a Personal Access Token."""

import os
from config import BOBO_DATA_DIR
import subprocess

TOOL_NAME = "github_setup"

def execute(token: str) -> str:
    """Configure GitHub CLI with a PAT."""
    if not token or len(token) < 10:
        return "❌ 请输入有效的 GitHub Personal Access Token"
    
    # Save to .env
    env_path = str(BOBO_DATA_DIR / ".env")
    try:
        os.makedirs(os.path.dirname(env_path), exist_ok=True)
    except Exception:
        pass
    
    try:
        # Check if GITHUB_TOKEN already in .env
        if os.path.exists(env_path):
            with open(env_path, "r") as f:
                content = f.read()
            if "GITHUB_TOKEN=" in content:
                # Replace existing line
                import re
                content = re.sub(r"^GITHUB_TOKEN=.*", f"GITHUB_TOKEN={token}", content, flags=re.MULTILINE)
            else:
                content += f"\nGITHUB_TOKEN={token}\n"
            with open(env_path, "w") as f:
                f.write(content)
        else:
            with open(env_path, "w") as f:
                f.write(f"GITHUB_TOKEN={token}\n")
    except Exception as e:
        return f"❌ 保存 Token 失败: {str(e)}"
    
    # Try gh auth login
    try:
        result = subprocess.run(
            ["gh", "auth", "login", "--with-token"],
            input=token, text=True, capture_output=True, timeout=10
        )
        if result.returncode == 0:
            return "✅ GitHub CLI 已配置成功。现在可以创建仓库、推送代码和审查 PR。"
        # gh might not be installed
        return (
            f"✅ Token 已保存到 {BOBO_DATA_DIR}/.env\n"
            f"⚠️ 但 gh auth login 执行失败: {result.stderr.strip()}\n"
            f"请安装 GitHub CLI: brew install gh"
        )
    except FileNotFoundError:
        return (
            f"✅ Token 已保存到 {BOBO_DATA_DIR}/.env\n"
            f"⚠️ GitHub CLI 未安装。请运行: brew install gh"
        )
    except Exception as e:
        return f"❌ 配置失败: {str(e)}"


TOOL_FUNC = execute
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": "配置 GitHub CLI。提供一个 Personal Access Token，Bobo 会将其保存并自动登录。Token 需要 repo、workflow 权限。",
        "parameters": {
            "type": "object",
            "properties": {
                "token": {
                    "type": "string",
                    "description": "GitHub Personal Access Token（需要 repo、workflow 权限）"
                }
            },
            "required": ["token"]
        }
    }
}

def register(reg):
    reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA)
