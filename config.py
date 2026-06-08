# config.py — 配置文件（从环境变量读取，无硬编码）

import os
from pathlib import Path
from dotenv import load_dotenv

# 加载 ~/.bobo/.env 文件
BOBO_CONFIG_DIR = Path.home() / ".bobo"
BOBO_ENV_FILE = BOBO_CONFIG_DIR / ".env"

if BOBO_ENV_FILE.exists():
    load_dotenv(BOBO_ENV_FILE)
    print(f"✅ 已加载配置: {BOBO_ENV_FILE}")
else:
    print(f"⚠️ 配置文件不存在: {BOBO_ENV_FILE}")

# Obsidian 库路径
OBSIDIAN_VAULT = os.environ.get("OBSIDIAN_VAULT", "")
if not OBSIDIAN_VAULT:
    home = os.path.expanduser("~")
    common_paths = [
        os.path.join(home, "Desktop/Obsidian note"),
        os.path.join(home, "Documents/Obsidian"),
        os.path.join(home, "Obsidian"),
    ]
    for path in common_paths:
        if os.path.exists(path):
            OBSIDIAN_VAULT = path
            break

if not OBSIDIAN_VAULT:
    print("⚠️ 请设置环境变量 OBSIDIAN_VAULT 指向你的 Obsidian 仓库路径")

BOBO_FOLDER = os.environ.get("BOBO_FOLDER", "Bobo数据库")

# 模型配置
MODEL_TYPE = os.environ.get("MODEL_TYPE", "api")
API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
API_BASE_URL = os.environ.get("API_BASE_URL", "https://api.deepseek.com/v1/chat/completions")
API_MODEL_NAME = os.environ.get("API_MODEL_NAME", "deepseek-chat")

# 其他配置
TOOL_TIMEOUT = int(os.environ.get("TOOL_TIMEOUT", "20"))
MAX_LOOPS = int(os.environ.get("MAX_LOOPS", "4"))

# 隐私配置
BLOCKED_FOLDERS = os.environ.get("BLOCKED_FOLDERS", "Private,Archive,日记").split(",")
EMAIL_PRIVACY_MODE = os.environ.get("EMAIL_PRIVACY_MODE", "ask")

if __name__ == "__main__":
    print(f"📁 Obsidian 仓库: {OBSIDIAN_VAULT}")
    print(f"🔑 API Key: {'已配置' if API_KEY else '未配置'}")
