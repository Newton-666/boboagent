#!/usr/bin/env python3
"""
测试浏览器工具
"""

import sys

from tools.browser import open_url, get_page_title, open_url_with_chrome

print("=" * 60)
print("浏览器工具测试")
print("=" * 60)

# 1. 测试打开网址
print("\n1. 测试打开网址:")
result = open_url("https://www.python.org")
print(f"   {result}")

# 2. 测试获取网页标题
print("\n2. 测试获取网页标题:")
title = get_page_title("https://www.python.org")
print(f"   标题: {title}")

# 3. 测试用 Chrome 打开
print("\n3. 测试用 Chrome 打开:")
result = open_url_with_chrome("https://www.python.org", headless=False)
print(f"   {result}")

# 4. 测试通过 Bobo 调用
print("\n4. 测试 Bobo 调用:")
from core.engine import Engine
from core.tool_executor import execute_tool
from core.llm_caller import create_llm_caller
from config import API_KEY, API_BASE_URL, API_MODEL_NAME
from tools import TOOLS_SCHEMA
from display import Display

Display.start_thinking_animation = lambda self: None
Display.stop_thinking_animation = lambda self: None

llm_caller = create_llm_caller(API_KEY, API_BASE_URL, API_MODEL_NAME, TOOLS_SCHEMA)
engine = Engine(llm_caller, execute_tool)

result = engine.run("打开 python.org 网站")
print(f"   回复: {result[:200]}...")

print("\n" + "=" * 60)
print("测试完成")
print("=" * 60)
