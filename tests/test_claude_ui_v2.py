#!/usr/bin/env python3
"""
测试 Claude 风格 UI - 动态进度
"""

import time
import sys

RESET = '\033[0m'
BOLD = '\033[1m'
BRIGHT_BLACK = '\033[90m'
BRIGHT_GREEN = '\033[92m'
BRIGHT_YELLOW = '\033[93m'
BRIGHT_CYAN = '\033[96m'
BRIGHT_MAGENTA = '\033[95m'
BRIGHT_WHITE = '\033[97m'


def clear_line():
    sys.stdout.write('\r\033[K')
    sys.stdout.flush()


def print_progress_animation():
    """演示动态进度 - 模拟 Claude 的确认过程"""
    print("\n" + "=" * 70)
    print("  动态进度演示 (模拟 Claude 确认过程)")
    print("=" * 70)
    
    # 初始状态
    steps = [
        {"icon": "✻", "text": "起草讨论页面...", "status": "running"},
        {"icon": "◻", "text": "生成首批讨论页面草稿，请人类确认", "status": "waiting"},
        {"icon": "◻", "text": "更新 index.md ## 讨论分类", "status": "pending"}
    ]
    
    print(f"\n  {BRIGHT_YELLOW}├─ thinking (5s){RESET}")
    
    # 显示初始状态
    for step in steps:
        if step["status"] == "running":
            print(f"  {BRIGHT_BLACK}│{RESET}  {BRIGHT_YELLOW}{step['icon']}{RESET} {step['text']}")
        elif step["status"] == "waiting":
            print(f"  {BRIGHT_BLACK}│{RESET}    {BRIGHT_BLACK}{step['icon']}{RESET} {step['text']}")
        else:
            print(f"  {BRIGHT_BLACK}│{RESET}    {BRIGHT_BLACK}{step['icon']}{RESET} {step['text']}")
    
    print(f"  {BRIGHT_BLACK}│{RESET}")
    print(f"  {BRIGHT_BLACK}└─{RESET} {BRIGHT_BLACK}等待用户确认...{RESET}")
    
    # 模拟用户确认
    print(f"\n  {BRIGHT_MAGENTA}❯{RESET} {BRIGHT_WHITE}确认{RESET}")
    time.sleep(1)
    
    # 动态更新 - 第一项完成
    print("\n  " + " " * 70)
    sys.stdout.write(f'\033[5A')  # 向上移动5行
    
    # 重新渲染更新后的状态
    steps2 = [
        {"icon": "✓", "text": "起草讨论页面...", "status": "done"},
        {"icon": "✻", "text": "生成首批讨论页面草稿，请人类确认", "status": "running"},
        {"icon": "◻", "text": "更新 index.md ## 讨论分类", "status": "pending"}
    ]
    
    print(f"  {BRIGHT_YELLOW}├─ thinking (5s){RESET}")
    for step in steps2:
        if step["status"] == "done":
            print(f"  {BRIGHT_BLACK}│{RESET}  {BRIGHT_GREEN}{step['icon']}{RESET} {step['text']}")
        elif step["status"] == "running":
            print(f"  {BRIGHT_BLACK}│{RESET}  {BRIGHT_YELLOW}{step['icon']}{RESET} {step['text']}")
        else:
            print(f"  {BRIGHT_BLACK}│{RESET}    {BRIGHT_BLACK}{step['icon']}{RESET} {step['text']}")
    
    print(f"  {BRIGHT_BLACK}│{RESET}")
    print(f"  {BRIGHT_BLACK}└─{RESET} {BRIGHT_BLACK}等待用户确认...{RESET}")
    
    time.sleep(1)
    
    # 再次确认
    print(f"\n  {BRIGHT_MAGENTA}❯{RESET} {BRIGHT_WHITE}确认{RESET}")
    time.sleep(1)
    
    # 全部完成
    sys.stdout.write(f'\033[5A')
    
    steps3 = [
        {"icon": "✓", "text": "起草讨论页面...", "status": "done"},
        {"icon": "✓", "text": "生成首批讨论页面草稿，请人类确认", "status": "done"},
        {"icon": "✓", "text": "更新 index.md ## 讨论分类", "status": "running"}
    ]
    
    print(f"  {BRIGHT_YELLOW}├─ thinking (5s){RESET}")
    for step in steps3:
        if step["status"] == "done":
            print(f"  {BRIGHT_BLACK}│{RESET}  {BRIGHT_GREEN}{step['icon']}{RESET} {step['text']}")
        else:
            print(f"  {BRIGHT_BLACK}│{RESET}  {BRIGHT_YELLOW}{step['icon']}{RESET} {step['text']}")
    
    print(f"  {BRIGHT_BLACK}│{RESET}")
    print(f"  {BRIGHT_BLACK}└─{RESET} {BRIGHT_GREEN}✓ 完成{RESET}")
    
    time.sleep(1)
    
    # 最终完成
    sys.stdout.write(f'\033[6A')
    print(f"  {BRIGHT_YELLOW}├─ thinking (5s){RESET}")
    print(f"  {BRIGHT_BLACK}│{RESET}  {BRIGHT_GREEN}✓{RESET} 起草讨论页面...")
    print(f"  {BRIGHT_BLACK}│{RESET}  {BRIGHT_GREEN}✓{RESET} 生成首批讨论页面草稿，请人类确认")
    print(f"  {BRIGHT_BLACK}│{RESET}  {BRIGHT_GREEN}✓{RESET} 更新 index.md ## 讨论分类")
    print(f"  {BRIGHT_BLACK}│{RESET}")
    print(f"  {BRIGHT_BLACK}└─{RESET} {BRIGHT_GREEN}✓ 全部完成{RESET}")
    
    print(f"\n  {BRIGHT_GREEN}{BOLD}●{RESET} 已完成 3 个讨论页面的起草和索引更新")
    print(f"\n  {BRIGHT_BLACK}✓ 完成 · 耗时 8.2s · ↓ 2345 tokens{RESET}")


def test_foldable_thinking():
    """测试可折叠 thinking"""
    print("\n" + "=" * 70)
    print("  可折叠 Thinking 演示")
    print("=" * 70)
    
    print(f"\n  {BRIGHT_YELLOW}├─ thinking (3s) {BRIGHT_BLACK}[ctrl+o to expand]{RESET}")
    print()
    print(f"  {BRIGHT_GREEN}{BOLD}●{RESET} 你好！有什么可以帮你的吗？")
    
    print("\n  💡 按 Ctrl+O 后展开显示:")
    print(f"  {BRIGHT_YELLOW}├─ thinking (3s){RESET}")
    print(f"  {BRIGHT_BLACK}│{RESET}  {BRIGHT_YELLOW}▶{RESET} 分析用户意图...")
    print(f"  {BRIGHT_BLACK}│{RESET}  {BRIGHT_YELLOW}▶{RESET} 准备回复")
    print(f"  {BRIGHT_BLACK}│{RESET}  {BRIGHT_GREEN}✓{RESET} 生成回复")
    print(f"  {BRIGHT_BLACK}└─{RESET}")
    print(f"  {BRIGHT_GREEN}{BOLD}●{RESET} 你好！有什么可以帮你的吗？")


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("  Claude 风格 UI v2 - 动态进度")
    print("=" * 70)
    
    test_foldable_thinking()
    print()
    print_progress_animation()
    
    print("\n" + "=" * 70)
    print("  设计要点")
    print("=" * 70)
    print("""
  📌 动态图标变化:
     ✻ (进行中) → ✓ (已完成)
     ◻ (待确认) → ◼ (确认中) → ✓ (已确认)
  
  📌 用户确认交互:
     ❯ 确认 (用户输入高亮)
     确认后图标立即变化
  
  📌 可折叠 thinking:
     ├─ thinking (3s) [ctrl+o to expand] (收起)
     ├─ thinking (3s) (展开后显示详细步骤)
  
  📌 状态层次:
     ├─ 主分支
     │  ├─ 子步骤
     │  └─ 子步骤
     └─ 最终结果
    """)
