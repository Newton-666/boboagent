"""用户确认模块 - 高风险操作交互式确认"""

import json
import sys
from ui.utils import BRIGHT_YELLOW, BRIGHT_BLACK, RESET


def user_confirm(tool_name: str, tool_args: dict, reason: str) -> bool:
    """真正的交互式确认"""
    print(f"\n  {BRIGHT_YELLOW}⚠️ 高风险操作{RESET}")
    print(f"  {BRIGHT_BLACK}工具: {tool_name}{RESET}")
    print(f"  {BRIGHT_BLACK}原因: {reason}{RESET}")

    args_str = json.dumps(tool_args, ensure_ascii=False)[:100]
    print(f"  {BRIGHT_BLACK}参数: {args_str}{RESET}")

    while True:
        try:
            response = input(f"  {BRIGHT_YELLOW}是否允许？(y/n): {RESET}").strip().lower()
            if response in ['y', 'yes']:
                return True
            elif response in ['n', 'no']:
                print(f"  {BRIGHT_BLACK}操作已取消{RESET}")
                return False
        except (KeyboardInterrupt, EOFError):
            print()
            return False
