#!/usr/bin/env python3
"""测试动态进度条"""

import sys
import time

from display import Display

print("=" * 60)
print("测试动态进度条")
print("=" * 60)

display = Display()

# 模拟工具调用
tools = ["search_obsidian", "read_obsidian", "classify_note", "write_obsidian"]

display.start_tools(len(tools))

for i, tool in enumerate(tools):
    # 显示工具开始（会启动动画）
    display.show_tool(tool, "running")
    
    # 模拟工具执行时间
    time.sleep(2)
    
    # 显示工具完成
    display.show_tool(tool, "done")

print("\n" + "=" * 60)
print("测试完成")
