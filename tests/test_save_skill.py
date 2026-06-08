#!/usr/bin/env python3
"""
测试技能保存功能
模拟：执行操作 → 保存为技能
"""

import sys
import os
import time


from core.engine import Engine
from core.tool_executor import execute_tool
from core.llm_caller import create_llm_caller
from config import API_KEY, API_BASE_URL, API_MODEL_NAME
from tools import TOOLS_SCHEMA
from display import Display

Display.start_thinking_animation = lambda self: None
Display.stop_thinking_animation = lambda self: None

print("=" * 60)
print("测试技能保存功能")
print("=" * 60)

# 创建引擎
llm_caller = create_llm_caller(API_KEY, API_BASE_URL, API_MODEL_NAME, TOOLS_SCHEMA)
engine = Engine(llm_caller, execute_tool)

# 第一步：执行一系列操作
print("\n📝 第1步: 执行操作序列")
print("-" * 40)

# 模拟用户要求执行多步任务
task = "先搜索一下 Python，然后帮我写个笔记，内容是关于Python的简单介绍"
print(f"用户: {task}")

result1 = engine.run(task)
print(f"回复: {result1[:200]}...")

# 第二步：保存为技能
print("\n" + "=" * 60)
print("\n📝 第2步: 保存为技能")
print("-" * 40)

save_cmd = '把这些步骤保存成技能，名字叫"Python调研"，描述是"搜索Python并写笔记"'
print(f"用户: {save_cmd}")

result2 = engine.run(save_cmd)
print(f"回复: {result2}")

# 第三步：查看技能文件
print("\n" + "=" * 60)
print("\n📝 第3步: 查看生成的技能文件")
print("-" * 40)

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
skill_file = os.path.join(_project_root, "skills", "Python调研.md")
if os.path.exists(skill_file):
    with open(skill_file, 'r') as f:
        print(f.read())
else:
    print(f"❌ 技能文件未生成: {skill_file}")

print("\n" + "=" * 60)
print("测试完成")
print("=" * 60)
