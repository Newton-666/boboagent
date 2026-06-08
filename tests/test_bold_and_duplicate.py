#!/usr/bin/env python3
"""
1:1 测试粗体渲染和重复打印问题
"""

import sys
import os
import re
import time


from core.llm_caller import create_llm_caller
from config import API_KEY, API_BASE_URL, API_MODEL_NAME
from tools import TOOLS_SCHEMA

# 颜色
RESET = '\033[0m'
BOLD = '\033[1m'
BRIGHT_GREEN = '\033[92m'
BRIGHT_WHITE = '\033[97m'


def render_markdown(text):
    """渲染 Markdown - 与 main.py 保持一致"""
    if not text:
        return text
    text = re.sub(r'\*\*([^*]+)\*\*', f'{BOLD}{BRIGHT_WHITE}\\1{RESET}', text)
    text = re.sub(r'`([^`]+)`', f'{BRIGHT_GREEN}{BOLD}\\1{RESET}', text)
    return text


def test_bold_rendering():
    """测试粗体渲染"""
    print("\n" + "=" * 70)
    print("测试 1: 粗体渲染")
    print("=" * 70)
    
    test_cases = [
        ("**粗体文字**", "粗体文字"),
        ("普通文字 **粗体** 普通", "普通文字 粗体 普通"),
        ("`代码块` 测试", "代码块 测试"),
        ("**粗体** 和 `代码` 混合", "粗体 和 代码 混合"),
    ]
    
    for original, expected_clean in test_cases:
        rendered = render_markdown(original)
        print(f"\n  原文: {original}")
        print(f"  渲染: {rendered}")
        if BOLD in rendered or BRIGHT_GREEN in rendered:
            print(f"  ✅ 包含颜色转义码")
        else:
            print(f"  ❌ 没有颜色转义码")


def test_llm_response():
    """测试 LLM 返回内容并渲染"""
    print("\n" + "=" * 70)
    print("测试 2: LLM 返回内容（渲染后）")
    print("=" * 70)
    
    llm = create_llm_caller(API_KEY, API_BASE_URL, API_MODEL_NAME, TOOLS_SCHEMA)
    
    messages = [
        {"role": "system", "content": "你是 Bobo。回答要简洁。"},
        {"role": "user", "content": "用一句话介绍什么是 Agent"}
    ]
    
    print("\n  调用 LLM...")
    response = llm(messages)
    
    if isinstance(response, dict):
        content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
    else:
        content = str(response)
    
    print(f"\n  原始内容长度: {len(content)} 字符")
    print(f"\n  渲染后内容:")
    print(f"  {render_markdown(content)}")
    
    # 检查是否有重复
    lines = content.split('\n')
    seen = set()
    duplicates = []
    for line in lines:
        line_stripped = line.strip()
        if line_stripped and line_stripped in seen:
            duplicates.append(line_stripped[:50])
        seen.add(line_stripped)
    
    if duplicates:
        print(f"\n  ❌ 发现重复段落: {duplicates[:3]}")
    else:
        print(f"\n  ✅ 没有发现重复内容")
    
    return content


def test_tool_call_response():
    """测试工具调用后的 LLM 响应"""
    print("\n" + "=" * 70)
    print("测试 3: 工具调用后 LLM 响应")
    print("=" * 70)
    
    from core.tool_executor import execute_tool
    
    print("\n  执行 web_search...")
    result = execute_tool("web_search", {"query": "AI agent"})
    print(f"  搜索结果: {len(result)} 字符")
    
    llm = create_llm_caller(API_KEY, API_BASE_URL, API_MODEL_NAME, TOOLS_SCHEMA)
    
    # 正确的消息格式
    messages = [
        {"role": "system", "content": "你是 Bobo，根据搜索结果回答用户问题。"},
        {"role": "user", "content": "搜索 AI agent 相关信息，然后总结"},
        {"role": "assistant", "content": "我来搜索一下", "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "web_search", "arguments": "{\"query\": \"AI agent\"}"}}]},
        {"role": "tool", "tool_call_id": "call_1", "content": result}
    ]
    
    print("\n  调用 LLM 生成最终回答...")
    response = llm(messages)
    
    if isinstance(response, dict):
        content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
    else:
        content = str(response)
    
    print(f"\n  最终回答长度: {len(content)} 字符")
    if content:
        print(f"\n  渲染后回答:")
        print(f"  {render_markdown(content[:500])}")
    else:
        print(f"\n  ❌ 回答为空！")
    
    return content


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("粗体与重复问题诊断测试")
    print("=" * 70)
    
    test_bold_rendering()
    test_llm_response()
    test_tool_call_response()
    
    print("\n" + "=" * 70)
    print("诊断完成")
    print("=" * 70)
