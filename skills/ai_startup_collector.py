#!/usr/bin/env python3
"""
AI 创业经历收集器 — Skill 脚本
每周一自动执行：搜索 AI 创业经历 → 提取结构化信息 → 去重追加到 Obsidian 笔记
"""

import json
import os
import re
import hashlib
from datetime import datetime

# ============ 配置 ============
NOTE_PATH = "/Users/niuqingwei/Desktop/Obsidian note/02_Areas/人工智能/Agentic AI/AI_Business.md"
SEARCH_KEYWORDS = [
    "AI startup founder experience",
    "AI创业 经历 切入点",
    "AI business idea validation",
    "AI创业者 踩坑 经验",
    "AI startup pivot story",
    "AI 创业 从0到1",
    "AI founder story how I started",
    "AI SaaS founder interview",
    "YC AI startup founder journey",
    "AI 独立开发者 创业",
]

# ============ 工具函数 ============

def read_existing_entries():
    """读取已有笔记，返回已有的 URL 集合（用于去重）"""
    if not os.path.exists(NOTE_PATH):
        return set()
    with open(NOTE_PATH, "r", encoding="utf-8") as f:
        content = f.read()
    # 提取所有已有的链接
    urls = set(re.findall(r"🔗 来源链接: (https?://[^\s\n]+)", content))
    return urls


def format_entry(data: dict) -> str:
    """将一条创业经历格式化为笔记条目"""
    lines = []
    lines.append("---")
    lines.append(f"### {data.get('founder', '未知创业者')} — {data.get('product', '未知产品')}")
    lines.append("")
    lines.append(f"**创业方向**: {data.get('direction', '未知')}")
    lines.append(f"**切入点**: {data.get('entry_point', '未知')}")
    lines.append(f"**技术栈**: {data.get('tech_stack', '未知')}")
    lines.append(f"**商业模式**: {data.get('business_model', '未知')}")
    lines.append(f"**关键教训**: {data.get('lessons', '未知')}")
    lines.append(f"**时间线**: {data.get('timeline', '未知')}")
    lines.append(f"🔗 来源链接: {data.get('url', '未知')}")
    lines.append("")
    return "\n".join(lines)


def append_to_note(new_entries: list):
    """将新条目追加到笔记末尾"""
    if not new_entries:
        print("✅ 没有新的创业经历需要添加")
        return

    # 构建追加内容
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    header = f"\n\n## 🆕 自动收集 — {now}\n\n"
    body = "\n".join([format_entry(e) for e in new_entries])

    with open(NOTE_PATH, "a", encoding="utf-8") as f:
        f.write(header + body)

    print(f"✅ 已追加 {len(new_entries)} 条新创业经历到笔记")


def extract_structured(text: str, url: str) -> dict:
    """
    从网页文本中提取结构化信息。
    实际运行时由 LLM 处理，这里作为占位逻辑。
    返回格式：
    {
        "founder": "...",
        "product": "...",
        "direction": "...",
        "entry_point": "...",
        "tech_stack": "...",
        "business_model": "...",
        "lessons": "...",
        "timeline": "...",
        "url": "..."
    }
    """
    # 这个函数会在 Skill 运行时由 Bobo 的 LLM 能力填充
    # 返回一个包含所有字段的 dict
    return {
        "founder": "待提取",
        "product": "待提取",
        "direction": "待提取",
        "entry_point": "待提取",
        "tech_stack": "待提取",
        "business_model": "待提取",
        "lessons": "待提取",
        "timeline": "待提取",
        "url": url,
    }


def main():
    print("🚀 AI 创业经历收集器启动")
    print(f"📝 目标笔记: {NOTE_PATH}")
    
    # 1. 读取已有记录（去重用）
    existing_urls = read_existing_entries()
    print(f"📊 已有记录数: {len(existing_urls)}")
    
    # 2. 搜索（由 Bobo 引擎执行 web_search）
    print("🔍 开始搜索...")
    # 搜索逻辑在 Skill 工作流中由 Bobo 的 web_search 工具完成
    
    # 3. 提取 & 去重 & 写入
    # 这部分在 Skill 工作流中由 Bobo 的 LLM 能力完成
    
    print("✅ 收集完成")


if __name__ == "__main__":
    main()
