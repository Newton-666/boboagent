# -*- coding: utf-8 -*-
"""票 P0-2 通道 B：library 主题频率信号（确定性代码，零 LLM）。

扫描 library/ 下各主题笔记，按目录/frontmatter 统计：
- 主题、近 7/30 天写入次数（文件 mtime 落窗计数）、更新时间窗；
- 排除 agent开发/ 施工报告目录（工程产物，不是用户偏好信号源）
  以及根级 index.md / MEMORY.md（导航/索引文件）；
- 输出 data/logs/signal_library_stats.json；
- 纯确定性代码，手动触发（不接 cron）。

用法：
  python -m tools.signal_library_stats            # 扫描并写 data/logs/
  python -m tools.signal_library_stats --days 30  # 自定义窗口
"""

import json
import os
import time

# library/ 根：tools/ 的上级目录
_LIB_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "library")
_LOG_DIR = os.path.join(os.path.dirname(_LIB_ROOT), "data", "logs")
_OUT = os.path.join(_LOG_DIR, "signal_library_stats.json")

# 排除目录（施工报告/工程产物）与根级非主题文件
_EXCLUDE_DIRS = {"agent开发"}
_EXCLUDE_FILES = {"index.md", "MEMORY.md"}


def _parse_frontmatter(text: str) -> dict:
    """提取 frontmatter（--- 包裹的 YAML 简化解析，拿 topic/version 即可）。"""
    meta = {}
    if not text.startswith("---"):
        return meta
    end = text.find("\n---", 3)
    if end < 0:
        return meta
    for line in text[3:end].splitlines():
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key in ("topic", "domain", "version"):
            meta[key] = val
    return meta


def compute_stats(days: int = 30, lib_root: str | None = None) -> dict:
    """扫描 library/ 统计主题频率。返回 dict 供写盘/测试断言。"""
    root = lib_root or _LIB_ROOT
    now = time.time()
    win7 = now - 7 * 86400
    win = now - days * 86400

    topics: dict[str, dict] = {}
    if not os.path.isdir(root):
        return {"scanned_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "days": days, "excluded_dirs": sorted(_EXCLUDE_DIRS),
                "topics": [], "total_files": 0}

    for dirpath, dirnames, filenames in os.walk(root):
        # 排除目录（原地修剪）
        dirnames[:] = [d for d in dirnames if d not in _EXCLUDE_DIRS]
        for fn in sorted(filenames):
            if not fn.endswith(".md") or fn in _EXCLUDE_FILES:
                continue
            path = os.path.join(dirpath, fn)
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                continue
            rel = os.path.relpath(path, root)
            domain = rel.split(os.sep)[0] if os.sep in rel else "(root)"

            try:
                with open(path, "r", encoding="utf-8") as f:
                    text = f.read(2000)
            except OSError:
                continue
            meta = _parse_frontmatter(text)
            topic = meta.get("topic") or os.path.splitext(fn)[0]

            t = topics.setdefault(topic, {
                "topic": topic, "domain": domain, "files": 0,
                "writes_7d": 0, f"writes_{days}d": 0,
                "first_write": None, "last_write": None,
                "total_versions": 0,
            })
            t["files"] += 1
            if mtime >= win7:
                t["writes_7d"] += 1
            if mtime >= win:
                t[f"writes_{days}d"] += 1
            if t["first_write"] is None or mtime < t["first_write"]:
                t["first_write"] = mtime
            if t["last_write"] is None or mtime > t["last_write"]:
                t["last_write"] = mtime
            try:
                t["total_versions"] += int(meta.get("version", 1) or 1)
            except (TypeError, ValueError):
                t["total_versions"] += 1

    # 时间戳转可读格式
    def _fmt(ts):
        return time.strftime("%Y-%m-%d", time.localtime(ts)) if ts else None

    topic_list = []
    for t in topics.values():
        t["first_write"] = _fmt(t["first_write"])
        t["last_write"] = _fmt(t["last_write"])
        topic_list.append(t)
    # 按写入次数降序
    topic_list.sort(key=lambda t: t[f"writes_{days}d"], reverse=True)

    return {
        "scanned_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "days": days,
        "excluded_dirs": sorted(_EXCLUDE_DIRS),
        "topics": topic_list,
        "total_files": sum(t["files"] for t in topic_list),
    }


def write_stats(days: int = 30) -> dict:
    """扫描 + 写 data/logs/signal_library_stats.json。"""
    stats = compute_stats(days=days)
    os.makedirs(_LOG_DIR, exist_ok=True)
    with open(_OUT, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    return stats


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="library 主题频率统计（票 P0-2 通道 B）")
    parser.add_argument("--days", type=int, default=30, help="统计窗口天数（默认 30）")
    parser.add_argument("--show", action="store_true", help="只打印不写盘")
    args = parser.parse_args()

    try:
        if args.show:
            stats = compute_stats(days=args.days)
        else:
            stats = write_stats(days=args.days)
    except Exception as exc:  # noqa: BLE001
        print(f"统计失败: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"扫描 {stats['total_files']} 个文件（排除 {stats['excluded_dirs']}），"
          f"窗口 {stats['days']} 天")
    for t in stats["topics"]:
        print(f"  {t['topic']:<14} 近7天 {t['writes_7d']:>2}  近{args.days}天 "
              f"{t[f'writes_{args.days}d']:>3}  文件 {t['files']}  "
              f"窗口 {t['first_write']}~{t['last_write']}")
    if not args.show:
        print(f"已写 {_OUT}")
