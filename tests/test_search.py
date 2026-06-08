#!/usr/bin/env python3
"""
测试搜索功能 + thinking 渲染
"""

import sys
import os
import time
import json
import re


from core.llm_caller import create_llm_caller
from core.tool_executor import execute_tool
from config import API_KEY, API_BASE_URL, API_MODEL_NAME
from tools import TOOLS_SCHEMA

# 颜色
RESET = '\033[0m'
BOLD = '\033[1m'

BRIGHT_BLACK = '\033[90m'
BRIGHT_RED = '\033[91m'
BRIGHT_GREEN = '\033[92m'
BRIGHT_YELLOW = '\033[93m'
BRIGHT_BLUE = '\033[94m'
BRIGHT_MAGENTA = '\033[95m'
BRIGHT_CYAN = '\033[96m'
BRIGHT_WHITE = '\033[97m'


def print_thinking_line(content):
    print(f"  {BRIGHT_YELLOW}▶{RESET} {content}")


def print_tool(name, args, status="running", output=None, duration=None):
    args_str = json.dumps(args, ensure_ascii=False)[:50] if args else ""
    if status == "running":
        print(f"  {BRIGHT_CYAN}⚙ {name}{RESET} {BRIGHT_BLACK}{args_str}{RESET}")
    elif status == "success":
        if duration:
            print(f"    {BRIGHT_GREEN}✓{RESET} {BRIGHT_BLACK}{duration:.1f}s{RESET}")
            if output and len(output) < 200:
                for line in output.split('\n')[:3]:
                    print(f"      {line[:80]}")
    elif status == "error":
        print(f"    {BRIGHT_RED}✗{RESET} {BRIGHT_BLACK}{args_str}{RESET}")


def print_assistant(content):
    print(f"\n  {BRIGHT_GREEN}{BOLD}●{RESET} {content}")
    print()


def print_separator():
    print(f"  {BRIGHT_BLACK}{'─' * 70}{RESET}")


def test_search_with_llm():
    """完整测试：LLM 决策 + 搜索 + 回答"""
    print("\n" + "=" * 70)
    print("  测试: LLM 驱动的搜索")
    print("=" * 70)
    
    llm = create_llm_caller(API_KEY, API_BASE_URL, API_MODEL_NAME, TOOLS_SCHEMA)
    
    messages = [
        {"role": "system", "content": "你是 Bobo。当用户要求搜索时，使用 web_search 工具。回答要简洁。"},
        {"role": "user", "content": "搜索一下 agent 智能体最新的行业动态，只需要给我摘要"}
    ]
    
    print(f"\n  {BRIGHT_MAGENTA}> {RESET}搜索 agent 智能体行业动态")
    print_separator()
    
    print_thinking_line("Calling LLM...")
    response = llm(messages)
    
    # 解析响应
    if isinstance(response, dict):
        choice = response.get("choices", [{}])[0]
        message = choice.get("message", {})
        content = message.get("content", "")
        tool_calls = message.get("tool_calls", [])
        
        print_thinking_line(f"LLM 响应: {content[:100] if content else '无'}")
        
        if tool_calls:
            print_thinking_line("检测到工具调用")
            for tc in tool_calls:
                tool_name = tc.get("function", {}).get("name", "")
                args_str = tc.get("function", {}).get("arguments", "{}")
                try:
                    tool_args = json.loads(args_str)
                except:
                    tool_args = {}
                
                print_tool(tool_name, tool_args, "running")
                
                start = time.time()
                result = execute_tool(tool_name, tool_args)
                duration = time.time() - start
                
                print_tool(tool_name, "", "success", duration=duration, output=result[:300])
                
                # 将结果加入消息
                messages.append({"role": "assistant", "content": content, "tool_calls": tool_calls})
                messages.append({"role": "tool", "content": result, "tool_call_id": tc.get("id", "")})
                
                # 再次调用 LLM
                print_thinking_line("再次调用 LLM 生成最终回答...")
                final_response = llm(messages)
                final_content = final_response.get("choices", [{}])[0].get("message", {}).get("content", "")
                print_assistant(final_content[:500])
        else:
            print_assistant(content[:500])
    
    print_separator()
    print()


if __name__ == "__main__":
    test_search_with_llm()
    print("测试完成")
