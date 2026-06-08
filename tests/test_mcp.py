#!/usr/bin/env python3
"""
MCP 完整功能测试
"""

import sys
import os

print("=" * 60)
print("MCP 功能测试")
print("=" * 60)

# 1. 测试 MCP 客户端
print("\n1. 测试 MCP 客户端:")
from core.mcp_client import get_mcp_client
client = get_mcp_client()

# 2. 测试连接 filesystem
print("\n2. 连接 filesystem 服务器:")
result = client.connect_server("filesystem")
print(f"   结果: {result}")

# 3. 测试连接 puppeteer
print("\n3. 连接 puppeteer 服务器:")
result = client.connect_server("puppeteer")
print(f"   结果: {result}")

# 4. 测试 MCP 工具注册
print("\n4. 测试 MCP 工具:")
from tools.mcp import execute as mcp_execute

desktop_path = os.path.expanduser("~/Desktop")
result = mcp_execute("filesystem", "list_directory", {"path": desktop_path})
print(f"   调用结果: {result[:100]}...")

# 5. 测试完整 Bobo 调用
print("\n5. 测试 Bobo 调用 MCP 工具:")
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

print("\n   测试: 列出桌面文件")
result = engine.run("用 MCP 列出我桌面上的文件")
print(f"   回复: {result[:200]}...")

print("\n" + "=" * 60)
print("MCP 测试完成")
print("=" * 60)
