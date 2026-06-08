#!/usr/bin/env python3
"""
简单测试 - 直接调用 BoboCore 而不是 main.py
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

# 禁用动画
Display.start_thinking_animation = lambda self: None
Display.stop_thinking_animation = lambda self: None

print("=" * 60)
print("Bobo 真实能力测试")
print("=" * 60)

# 创建引擎
llm_caller = create_llm_caller(API_KEY, API_BASE_URL, API_MODEL_NAME, TOOLS_SCHEMA)
engine = Engine(llm_caller, execute_tool)

test_cases = [
    ("问候", "你好"),
    ("时间", "现在几点？"),
    ("搜索", "搜索一下 Python"),
    ("写笔记", '帮我写个笔记，内容是"测试新架构"'),
    ("搜索笔记", "找一下测试笔记"),
    ("邮件", "看看有没有新邮件"),
    ("日历", "明天下午3点开会，帮我记一下"),
]

for name, inp in test_cases:
    print(f"\n📝 {name}: {inp}")
    print("-" * 40)
    try:
        result = engine.run(inp)
        print(f"回复: {result[:300]}..." if len(result) > 300 else f"回复: {result}")
    except Exception as e:
        print(f"❌ 错误: {e}")
    time.sleep(1)

print("\n" + "=" * 60)
print("测试完成")
print("=" * 60)

