#!/usr/bin/env python3
"""测试 LLM 返回内容是否重复"""

import sys
import os

from core.llm_caller import create_llm_caller
from config import API_KEY, API_BASE_URL, API_MODEL_NAME
from tools import TOOLS_SCHEMA

llm = create_llm_caller(API_KEY, API_BASE_URL, API_MODEL_NAME, TOOLS_SCHEMA)

# 模拟复杂查询
messages = [
    {"role": "system", "content": "你是Bobo，专业的旅行规划助手"},
    {"role": "user", "content": "从上海到北京的出行计划，需要详细的时间安排"}
]

print("调用 LLM...")
response = llm(messages, use_tools=True)

if "error" in response:
    print(f"错误: {response}")
else:
    content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
    print(f"\n内容长度: {len(content)} 字符")
    print(f"\n前500字符:\n{content[:500]}")
    
    # 检查是否有重复段落
    lines = content.split('\n')
    seen = set()
    duplicates = []
    for i, line in enumerate(lines):
        line_stripped = line.strip()
        if line_stripped and line_stripped in seen:
            duplicates.append((i, line_stripped[:50]))
        seen.add(line_stripped)
    
    if duplicates:
        print(f"\n发现重复段落 {len(duplicates)} 处:")
        for idx, line in duplicates[:5]:
            print(f"  行 {idx}: {line}...")
    else:
        print("\n✅ 没有发现重复段落")
