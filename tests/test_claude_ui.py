#!/usr/bin/env python3
"""
测试 Claude 风格 UI 改进
- 折叠 thinking
- 显示 token 数
- 树形结构
"""

import time
import sys

# 颜色
RESET = '\033[0m'
BOLD = '\033[1m'
BRIGHT_BLACK = '\033[90m'
BRIGHT_GREEN = '\033[92m'
BRIGHT_YELLOW = '\033[93m'
BRIGHT_CYAN = '\033[96m'
BRIGHT_MAGENTA = '\033[95m'
BRIGHT_WHITE = '\033[97m'


def print_separator():
    print(f"  {BRIGHT_BLACK}{'─' * 70}{RESET}")


def print_folded_thinking(seconds, hint="ctrl+o to expand"):
    """折叠状态的 thinking"""
    print(f"  {BRIGHT_YELLOW}├─ thinking ({seconds}s) {BRIGHT_BLACK}({hint}){RESET}")


def print_expanded_thinking(seconds, steps, tokens=None):
    """展开状态的 thinking"""
    print(f"  {BRIGHT_YELLOW}├─ thinking ({seconds}s){RESET}")
    for step in steps:
        print(f"  {BRIGHT_BLACK}│{RESET}  {step}")
    if tokens:
        print(f"  {BRIGHT_BLACK}│{RESET}  {BRIGHT_BLACK}↓ {tokens} tokens{RESET}")


def print_tool_with_tokens(name, args, duration, tokens=None):
    """工具调用带 token 数"""
    args_str = args[:40] if len(args) > 40 else args
    if tokens:
        print(f"  {BRIGHT_CYAN}⚙ {name}{RESET} {BRIGHT_BLACK}{args_str}{RESET} {BRIGHT_BLACK}({duration}s · ↓ {tokens} tokens){RESET}")
    else:
        print(f"  {BRIGHT_CYAN}⚙ {name}{RESET} {BRIGHT_BLACK}{args_str}{RESET} {BRIGHT_BLACK}({duration}s){RESET}")
    print(f"  {BRIGHT_BLACK}  ⎿{RESET}  {BRIGHT_GREEN}✓{RESET} {BRIGHT_BLACK}完成{RESET}")


def print_user_confirm(text):
    """用户确认高亮"""
    print(f"  {BRIGHT_MAGENTA}❯{RESET} {BRIGHT_WHITE}{text}{RESET}")


def print_tree_structure():
    """树形结构示例"""
    print("\n" + "=" * 70)
    print("  Claude 风格 UI 预览")
    print("=" * 70)
    
    # 1. 用户输入高亮
    print_user_confirm("确认执行整理笔记操作")
    print_separator()
    
    # 2. 折叠状态的 thinking
    print_folded_thinking(5)
    print()
    
    # 3. 工具调用带 token 数
    print_tool_with_tokens("write_obsidian", '{"filename": "讨论_经方_20260607.md"}', 2.3, 1245)
    
    # 4. 第二个工具
    print_tool_with_tokens("write_obsidian", '{"filename": "讨论_经方_20260607_2.md"}', 1.8, 892)
    
    # 5. 展开状态的 thinking (按 Ctrl+O 后)
    print("\n" + "=" * 70)
    print("  展开状态 (按 Ctrl+O)")
    print("=" * 70)
    
    steps = [
        "✻ 起草讨论页面...",
        "  ⎿ ✓ 读取协作模式病历，提取可Wiki化片段",
        "  ◼ 生成首批讨论页面草稿，请人类确认",
        "  ◻ 更新 index.md ## 讨论分类"
    ]
    print_expanded_thinking(13, steps, 436)
    
    # 6. 最终回复
    print(f"\n  {BRIGHT_GREEN}{BOLD}●{RESET} 已完成 3 个讨论页面的起草，请确认后我将更新 index.md")
    
    print_separator()
    print(f"  {BRIGHT_BLACK}快捷键: Ctrl+O 展开/收起 thinking{RESET}")
    print()


def test_interactive():
    """交互式演示"""
    print("\n" + "=" * 70)
    print("  交互式演示 (模拟实际使用)")
    print("=" * 70)
    
    print_user_confirm("帮我整理经方讨论笔记")
    print_separator()
    
    # 开始折叠
    print_folded_thinking(0)
    
    # 模拟计时
    for i in range(1, 4):
        time.sleep(1)
        # 这里简化，实际会用覆盖写
        print(f"\r  {BRIGHT_YELLOW}├─ thinking ({i}s) (ctrl+o to expand){RESET}", end="")
    
    print()  # 换行
    
    # 显示工具调用
    print_tool_with_tokens("read_obsidian", '{"path": "协作模式病历.md"}', 1.2, 345)
    print_tool_with_tokens("write_obsidian", '{"filename": "讨论_经方.md"}', 2.5, 1256)
    
    # 展开状态
    print("\n  💡 按 Ctrl+O 展开详细过程...")
    time.sleep(1)
    
    steps = [
        "✻ 分析用户要求...",
        "  ⎿ ✓ 识别需要整理经方讨论笔记",
        "✻ 读取原始内容...",
        "  ⎿ ✓ 读取 协作模式病历.md",
        "✻ 提取可Wiki化片段...",
        "  ⎿ ✓ 提取 3 个核心讨论点",
        "✻ 生成草稿...",
        "  ◼ 生成 3 个讨论页面",
        "  ◻ 等待用户确认"
    ]
    print_expanded_thinking(8, steps, 2345)
    
    # 最终回复
    print(f"\n  {BRIGHT_GREEN}{BOLD}●{RESET} 已完成 3 个讨论页面的起草：\n")
    print(f"    1. 讨论_经方_温度辨证框架.md")
    print(f"    2. 讨论_经方_黄连桂枝杠杆比.md")
    print(f"    3. 讨论_经方_黏膜温度假说.md")
    print(f"\n    请确认后我将更新 index.md")
    
    print_separator()
    print(f"  {BRIGHT_BLACK}✓ 完成 · 耗时 8.2s · ↓ 2345 tokens{RESET}")
    print()


if __name__ == "__main__":
    print_tree_structure()
    test_interactive()
    
    print("\n" + "=" * 70)
    print("  改进点总结")
    print("=" * 70)
    print("""
  ✅ 1. 折叠 thinking: ├─ thinking (5s) (ctrl+o to expand)
  ✅ 2. 显示 token 数: ↓ 436 tokens
  ✅ 3. 用户确认高亮: ❯ 确认
  ✅ 4. 树形缩进: │ 符号
  ✅ 5. 工具调用耗时: (2.3s · ↓ 1245 tokens)
  ✅ 6. 状态图标: ✻ (进行中)、◼ (待确认)、◻ (待执行)
    """)
