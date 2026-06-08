#!/usr/bin/env python3
"""带性能追踪的测试"""

import sys
import time

from core.engine import Engine
from core.tool_executor import execute_tool
from core.llm_caller import create_llm_caller
from core.tracer import get_tracer
from config import API_KEY, API_BASE_URL, API_MODEL_NAME
from tools import TOOLS_SCHEMA
from display import Display

Display.start_thinking_animation = lambda self: None
Display.stop_thinking_animation = lambda self: None

print("=" * 60)
print("带性能追踪的测试")
print("=" * 60)

tracer = get_tracer()
tracer.clear()
tracer.enabled = True

tracer.start("初始化引擎")
llm_caller = create_llm_caller(API_KEY, API_BASE_URL, API_MODEL_NAME, TOOLS_SCHEMA)
engine = Engine(llm_caller, execute_tool)
tracer.end("初始化引擎")

tracer.start("总执行")
print("\n📝 用户: Python调研")
result = engine.run("Python调研")
tracer.end("总执行")

print(f"\n📄 回复: {result[:200]}...")
print(tracer.report())
