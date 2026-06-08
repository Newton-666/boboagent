#!/usr/bin/env python3
"""测试出行计划回复是否重复"""

import sys
import os

from core.llm_caller import create_llm_caller
from config import API_KEY, API_BASE_URL, API_MODEL_NAME
from tools import TOOLS_SCHEMA

llm = create_llm_caller(API_KEY, API_BASE_URL, API_MODEL_NAME, TOOLS_SCHEMA)

# 复杂出行计划查询
messages = [
    {"role": "system", "content": "你是Bobo，专业的旅行规划助手。需要时调用工具搜索信息。"},
    {"role": "user", "content": "明天早晨我们乘坐G532前往北京，计划入住muji酒店，现在我们在上海莘庄地区，列出出行计划与时间表"}
]

print("调用 LLM (use_tools=True)...")
response = llm(messages, use_tools=True)

if "error" in response:
    print(f"错误: {response}")
else:
    content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
    print(f"\n内容长度: {len(content)} 字符")
    
    # 检查是否有重复段落
    lines = content.split('\n')
    seen = set()
    duplicates = []
    for i, line in enumerate(lines):
        line_stripped = line.strip()
        if line_stripped and line_stripped in seen:
            duplicates.append((i, line_stripped[:60]))
        seen.add(line_stripped)
    
    if duplicates:
        print(f"\n❌ 发现重复段落 {len(duplicates)} 处:")
        for idx, line in duplicates[:10]:
            print(f"  行 {idx}: {line}...")
    else:
        print("\n✅ 没有发现重复段落")
    
    # 打印内容看看
    print(f"\n完整内容:\n{content}")
