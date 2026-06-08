import sys
import os

from core.engine import Engine
from core.tool_executor import execute_tool
from core.llm_caller import create_llm_caller
from config import API_KEY, API_BASE_URL, API_MODEL_NAME
from tools import TOOLS_SCHEMA

def debug_callback(event_type, data):
    print(f"[DEBUG] event: {event_type}")

llm = create_llm_caller(API_KEY, API_BASE_URL, API_MODEL_NAME, TOOLS_SCHEMA)
engine = Engine(llm, execute_tool, callback=debug_callback)

print("测试简单问题...")
engine.run("你好")
print("测试复杂问题...")
engine.run("帮我搜索 Python")
