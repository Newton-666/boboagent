#!/usr/bin/env python3
"""
测试 9: 工具发现与可用性 - 真实 UI 模拟
- 检查所有工具是否可发现
- 检查工具描述是否完整
- 检查工具函数是否可调用
"""

import sys
import os
import time
import json


from tools import TOOLS_SCHEMA, TOOL_FUNCTIONS
from display import print_separator

# 颜色
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
CYAN = '\033[96m'
RESET = '\033[0m'
BOLD = '\033[1m'


def print_test(name):
    print(f"\n  {CYAN}▶ 测试: {name}{RESET}")


def print_ok(msg=""):
    print(f"    {GREEN}✓{RESET} {msg}")


def print_fail(msg=""):
    print(f"    {RED}✗{RESET} {msg}")


def print_warn(msg=""):
    print(f"    {YELLOW}⚠️{RESET} {msg}")


def test_tools_count():
    """测试工具数量"""
    print_test("工具数量")
    
    count = len(TOOLS_SCHEMA)
    if count >= 5:
        print_ok(f"发现 {count} 个工具")
        return True
    else:
        print_fail(f"只有 {count} 个工具，预期至少 5 个")
        return False


def test_tools_schema():
    """测试工具 schema 格式"""
    print_test("工具 Schema 格式")
    
    issues = []
    for i, tool in enumerate(TOOLS_SCHEMA):
        name = tool.get('function', {}).get('name', 'unknown')
        
        # 检查 type 字段
        if tool.get('type') != 'function':
            issues.append(f"{name}: 缺少 type='function'")
        
        # 检查 function 字段
        if 'function' not in tool:
            issues.append(f"{name}: 缺少 function 字段")
        else:
            func = tool['function']
            if 'name' not in func:
                issues.append(f"{name}: 缺少 function.name")
            if 'description' not in func:
                issues.append(f"{name}: 缺少 function.description")
            if 'parameters' not in func:
                issues.append(f"{name}: 缺少 function.parameters")
    
    if issues:
        for issue in issues[:5]:
            print_warn(issue)
        if len(issues) > 5:
            print_warn(f"... 还有 {len(issues)-5} 个问题")
        return False
    else:
        print_ok("所有工具 schema 格式正确")
        return True


def test_tools_executable():
    """测试工具是否可执行"""
    print_test("工具可执行性")
    
    # 测试安全工具列表
    safe_tools = ['get_current_time', 'list_directory']
    
    passed = 0
    for tool_name in safe_tools:
        if tool_name in TOOL_FUNCTIONS:
            try:
                result = TOOL_FUNCTIONS[tool_name]()
                if result:
                    print_ok(f"{tool_name} 执行成功")
                    passed += 1
                else:
                    print_warn(f"{tool_name} 返回空结果")
            except Exception as e:
                print_fail(f"{tool_name} 执行失败: {e}")
        else:
            print_warn(f"{tool_name} 未注册")
    
    return passed == len(safe_tools)


def test_tools_descriptions():
    """测试工具描述是否合理"""
    print_test("工具描述")
    
    issues = []
    for tool in TOOLS_SCHEMA:
        name = tool.get('function', {}).get('name', 'unknown')
        desc = tool.get('function', {}).get('description', '')
        
        if len(desc) < 20:
            issues.append(f"{name}: 描述过短 ({len(desc)} 字符)")
        if 'emoji' in desc or '😊' in desc:
            issues.append(f"{name}: 描述包含 emoji")
    
    if issues:
        for issue in issues[:3]:
            print_warn(issue)
        return False
    else:
        print_ok("所有工具描述合理")
        return True


def main():
    print("\n" + "=" * 70)
    print(f"  {BOLD}工具发现与可用性测试{RESET}")
    print("=" * 70)
    
    results = []
    
    results.append(("工具数量", test_tools_count()))
    results.append(("Schema 格式", test_tools_schema()))
    results.append(("可执行性", test_tools_executable()))
    results.append(("描述质量", test_tools_descriptions()))
    
    print("\n" + "=" * 70)
    print(f"  {BOLD}测试结果{RESET}")
    print("=" * 70)
    
    passed = 0
    for name, ok in results:
        status = f"{GREEN}✓{RESET}" if ok else f"{RED}✗{RESET}"
        print(f"  {status} {name}")
        if ok:
            passed += 1
    
    print(f"\n  {BOLD}通过率: {passed}/{len(results)} ({passed*100//len(results)}%){RESET}")
    
    if passed == len(results):
        print(f"\n  {GREEN}{BOLD}✅ 工具发现测试通过{RESET}")
    else:
        print(f"\n  {RED}{BOLD}❌ 部分测试失败{RESET}")
    
    print("=" * 70)


if __name__ == "__main__":
    main()
