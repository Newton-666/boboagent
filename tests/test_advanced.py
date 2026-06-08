#!/usr/bin/env python3
"""
高级功能测试 - 技能自创 + MCP 集成
"""

import sys

from core.skill_manager import get_skill_manager
from core.mcp_client import get_mcp_client, MCP_SERVERS
from tools.mcp_tools import execute_connect, execute_list

print("=" * 70)
print("Bobo 高级功能测试")
print("=" * 70)

# 1. 测试技能管理
print("\n1. 技能管理器测试:")
sm = get_skill_manager()
skills = sm.list_skills()
print(f"   当前技能数: {len(skills)}")
for s in skills:
    print(f"     - {s['name']}")

# 2. 测试从历史提取步骤
print("\n2. 从对话历史提取步骤:")
mock_history = [
    {"role": "user", "content": "帮我搜索 Python"},
    {"role": "assistant", "content": "好的", "tool_calls": [{"function": {"name": "web_search"}}]},
    {"role": "tool", "content": "搜索结果"},
    {"role": "assistant", "content": "总结", "tool_calls": [{"function": {"name": "write_obsidian"}}]},
]
steps = sm.extract_steps_from_history(mock_history)
print(f"   提取到 {len(steps)} 个步骤: {steps}")

# 3. 测试创建新技能
print("\n3. 创建新技能:")
result = sm.create_skill_from_history("快速搜索", "搜索并保存", steps)
print(f"   {result}")

# 4. 测试 MCP
print("\n4. MCP 客户端测试:")
print(f"   可用 MCP 服务器: {list(MCP_SERVERS.keys())}")

# 5. 测试 MCP 工具注册
print("\n5. MCP 工具测试:")
print(f"   连接 filesystem: {execute_connect('filesystem')}")
print(f"   列出服务器: {execute_list()[:200]}")

print("\n" + "=" * 70)
print("测试完成")
print("=" * 70)
