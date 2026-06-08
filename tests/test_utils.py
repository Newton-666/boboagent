"""测试工具 - 带分支显示"""

import sys
import time

from display import Display
from core.llm_caller import create_llm_caller
from core.engine import Engine
from core.tool_executor import execute_tool
from config import API_KEY, API_BASE_URL, API_MODEL_NAME
from tools import TOOLS_SCHEMA

# 使用原生 Display，不覆盖任何方法
_display = Display()

# 包装 execute_tool
_original_execute = execute_tool
_tool_count = 0

def execute_tool_with_display(tool_name, arguments):
    global _tool_count
    _tool_count += 1
    # 显示工具调用开始
    _display.show_tool(tool_name, "running")
    start = time.time()
    result = _original_execute(tool_name, arguments)
    elapsed = time.time() - start
    # 显示工具调用结束
    status = "done" if "✅" in result or "成功" in result else "error"
    _display.show_tool(tool_name, status)
    return result

def create_test_engine():
    """创建带分支显示的引擎"""
    llm_caller = create_llm_caller(API_KEY, API_BASE_URL, API_MODEL_NAME, TOOLS_SCHEMA)
    return Engine(llm_caller, execute_tool_with_display)

def run_test(user_input: str):
    """运行单个测试，显示分支"""
    print(f"\n📝 用户: {user_input}")
    print("-" * 40)
    engine = create_test_engine()
    result = engine.run(user_input)
    print(f"\n回复: {result[:200]}...")
    return result
