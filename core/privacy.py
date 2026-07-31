"""Privacy tag engine — 用户通过自然语言在 privacy.toml 中标记敏感目录，
Bobo 读取这些目录下的文件时自动标注标签到审计日志中。

格式（BOBO_DATA_DIR/privacy.toml）：
    [tags]
    专案 = ["~/Desktop/专案/"]
    日记 = ["~/Obsidian/日记/", "~/Documents/私人/"]
"""

import os
import sys
from pathlib import Path

try:
    import tomllib
except ImportError:
    import tomli as tomllib

from config import BOBO_DATA_DIR

_PRIVACY_FILE = BOBO_DATA_DIR / "privacy.toml"
_tags_cache: None | dict[str, list[str]] = None  # tag_name → [patterns]
_cache_mtime: float = 0


def _load_tags() -> dict[str, list[str]]:
    """加载 privacy.toml 的 [tags] 段。无文件时返回空 dict。"""
    global _tags_cache, _cache_mtime
    if not _PRIVACY_FILE.exists():
        _tags_cache = {}
        _cache_mtime = 0
        return {}
    try:
        mtime = _PRIVACY_FILE.stat().st_mtime
        if _tags_cache is not None and mtime == _cache_mtime:
            return _tags_cache
        with open(_PRIVACY_FILE, "rb") as f:
            data = tomllib.load(f)
        tags = data.get("tags", {})
        if not isinstance(tags, dict):
            tags = {}
        _tags_cache = {k: v if isinstance(v, list) else [v] for k, v in tags.items()}
        _cache_mtime = mtime
        return _tags_cache
    except Exception:
        return _tags_cache if _tags_cache is not None else {}


def match_tags(filepath: str) -> list[str]:
    """返回 filepath 命中的隐私标签列表。没有命中返回空列表。"""
    tags = _load_tags()
    if not tags:
        return []
    path = os.path.expanduser(filepath)
    matched = []
    for tag_name, patterns in tags.items():
        for pattern in patterns:
            pattern = os.path.expanduser(pattern.strip())
            # 前缀匹配（目录）：/Users/.../专案/xxx.md 匹配 "~/Desktop/专案/"
            if pattern.endswith(os.sep) or pattern.endswith("/"):
                if path.startswith(pattern.rstrip("/") + os.sep) or path == pattern.rstrip("/"):
                    matched.append(tag_name)
                    break
            # 精确文件匹配
            elif path == pattern:
                matched.append(tag_name)
                break
            # Glob 匹配
            elif Path(path).match(pattern):
                matched.append(tag_name)
                break
    return matched
