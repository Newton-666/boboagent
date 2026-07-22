# config.py — 配置文件（从环境变量读取，无硬编码）

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# 所有 Bobo 运行时数据统一放在项目仓库的 data/ 目录下
# （之前分散在 ~/.bobo 和 ~/.bobo_v2 两个地方）
# 可通过 BOBO_DATA_DIR 环境变量覆盖
_BOBO_REPO_ROOT = Path(__file__).resolve().parent
_DEFAULT_DATA_DIR = _BOBO_REPO_ROOT / "data"
BOBO_DATA_DIR = Path(os.environ.get("BOBO_DATA_DIR", str(_DEFAULT_DATA_DIR)))
BOBO_DATA_DIR.mkdir(parents=True, exist_ok=True)

# .env 文件路径
BOBO_ENV_FILE = BOBO_DATA_DIR / ".env"

if BOBO_ENV_FILE.exists():
    load_dotenv(BOBO_ENV_FILE)
    print(f" 已加载配置: {BOBO_ENV_FILE}", file=sys.stderr)
else:
    print(f" 配置文件不存在: {BOBO_ENV_FILE}", file=sys.stderr)

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
    print(" 请设置环境变量 OBSIDIAN_VAULT 指向你的 Obsidian 仓库路径", file=sys.stderr)

BOBO_FOLDER = os.environ.get("BOBO_FOLDER", "Bobo数据库")

# 模型配置
MODEL_TYPE = os.environ.get("MODEL_TYPE", "api")

# 从 provider 配置解析 API 设置（向后兼容已有的 DEEPSEEK_API_KEY 等环境变量）
# 延迟到首次使用时才调用 resolve_provider()，避免 import-time 循环依赖
# （config.py 未加载完 → tools 发现 → obsidian_tools 回 import config → BLOCKED_FOLDERS 未定义）
_provider_cache = None

def _get_provider():
    global _provider_cache
    if _provider_cache is None:
        from core.provider import resolve_provider
        _provider_cache = resolve_provider()
    return _provider_cache

def _lazy(key: str, default: str = "") -> str:
    return os.environ.get(key) or _get_provider().get(key, default)

def _lazy_provider_attr(key: str, env_override: str = "", fallback: str = "") -> str:
    """惰性获取 provider 配置——使用方调用时才 resolve，避免 import-time 循环链。"""
    val = os.environ.get(env_override) if env_override else ""
    if not val:
        val = _get_provider().get(key, fallback)
    return val

API_KEY = os.environ.get("DEEPSEEK_API_KEY") or _get_provider().get("api_key", "")
API_BASE_URL = os.environ.get("API_BASE_URL") or _get_provider().get("base_url", "")
API_MODEL_NAME = os.environ.get("API_MODEL_NAME") or _get_provider().get("model", "")
ACTIVE_PROVIDER = _get_provider().get("name", "deepseek")

# 其他配置
TOOL_TIMEOUT = int(os.environ.get("TOOL_TIMEOUT", "20"))
MAX_LOOPS = int(os.environ.get("MAX_LOOPS", "4"))

# 隐私配置（strip 防止 "Private, Archive" 带空格导致匹配失效）
BLOCKED_FOLDERS = [f.strip() for f in os.environ.get("BLOCKED_FOLDERS", "Private,Archive,日记").split(",") if f.strip()]
EMAIL_PRIVACY_MODE = os.environ.get("EMAIL_PRIVACY_MODE", "ask")

# Context Engineering — Result Marking System（产品级配置）
BOBO_CONTEXT_MARKING = os.environ.get("BOBO_CONTEXT_MARKING", "true").lower() in ("true", "1", "yes")
BOBO_CONTEXT_MARKING_MIN_CHARS = int(os.environ.get("BOBO_CONTEXT_MARKING_MIN_CHARS", "2000"))

# 主动模式：off = 纯响应, subtle = 静默注入不给用户看, full = LLM 可主动提议
BOBO_PROACTIVE_MODE = os.environ.get("BOBO_PROACTIVE_MODE", "off")
assert BOBO_PROACTIVE_MODE in ("off", "subtle", "full"), f"BOBO_PROACTIVE_MODE 必须是 off/subtle/full，当前: {BOBO_PROACTIVE_MODE}"

# 会话目录配置
_DEFAULT_SESSION_DIR = str(BOBO_DATA_DIR / "sessions")
SESSION_DIR = os.environ.get("BOBO_SESSION_DIR", str(_DEFAULT_SESSION_DIR))

# 项目代码保存目录
_DEFAULT_PROJECTS_DIR = Path(__file__).parent / "projects"
PROJECTS_DIR = os.environ.get("BOBO_PROJECTS_DIR", str(_DEFAULT_PROJECTS_DIR))

# 用户昵称（显示在消息前面，默认使用系统用户名）
import getpass
BOBO_AUTHOR = os.environ.get("BOBO_AUTHOR", getpass.getuser())

if __name__ == "__main__":
    print(f" Obsidian 仓库: {OBSIDIAN_VAULT}")
    print(f" API Key: {'已配置' if API_KEY else '未配置'}")
    print(f" 会话目录: {SESSION_DIR}")
    print(f" 项目目录: {PROJECTS_DIR}")
    print(f" 用户昵称: {BOBO_AUTHOR}")
