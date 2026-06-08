#!/usr/bin/env python3
"""
测试意图检测 - 验证硬拦截规则的准确性
"""

import re

RESET = '\033[0m'
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
CYAN = '\033[96m'


def hard_intercept(user_input: str) -> tuple:
    text = user_input.lower().strip()
    
    # 明确执行请求（放行）
    execute_patterns = [
        r'^执行\s+',
        r'^运行\s+',
        r'^帮我\s+',
        r'^请\s+.*(执行|运行)',
        r'写一个.*代码',
        r'生成.*脚本',
    ]
    
    for pattern in execute_patterns:
        if re.search(pattern, text):
            return False, "明确执行请求"
    
    # 带"测试"但有明确执行意图（放行）
    test_execute_patterns = [
        r'重新测试',
        r'再测试一下',
        r'测试.*代码',
        r'测试.*脚本',
        r'运行测试',
        r'测试执行',
    ]
    
    for pattern in test_execute_patterns:
        if re.search(pattern, text):
            return False, f"有执行意图的测试: {pattern}"
    
    # 讨论/测试关键词（拦截）
    discuss_patterns = [
        '测试', '试试', '看一看', '检查一下', '验证',
        '能不能', '是否支持', '可以吗', '怎么', '如何',
        '我只是', '我在测试', '支持', '吗',
    ]
    
    for pattern in discuss_patterns:
        if pattern in text:
            return True, f"检测到讨论性关键词: {pattern}"
    
    # 问句（拦截）
    if text.endswith('？') or text.endswith('?'):
        return True, "这是一个问句，不是执行请求"
    
    return False, "无特殊模式"


def print_test(test_name, user_input, expected_action):
    print(f"\n  {CYAN}📋 {test_name}{RESET}")
    print(f"    输入: {user_input}")
    print(f"    期望: {expected_action}")
    
    should_intercept, reason = hard_intercept(user_input)
    actual = "拦截(不执行)" if should_intercept else "放行(执行)"
    
    if (should_intercept and expected_action == "拦截") or (not should_intercept and expected_action == "放行"):
        print(f"    结果: {GREEN}✅ {actual}{RESET} - {reason}")
    else:
        print(f"    结果: {RED}❌ {actual}{RESET} - {reason}")


def main():
    print("\n" + "=" * 70)
    print("  意图检测测试")
    print("=" * 70)
    
    tests = [
        ("执行1", "执行 ls -la", "放行"),
        ("执行2", "运行 python test.py", "放行"),
        ("执行3", "帮我列出桌面文件", "放行"),
        ("执行4", "写一个计算1+2的代码", "放行"),
        ("执行5", "生成一个Python脚本", "放行"),
        ("测试执行1", "重新测试刚才的代码", "放行"),
        ("测试执行2", "再测试一下那个脚本", "放行"),
        ("测试执行3", "测试一下写好的代码", "放行"),
        ("测试执行4", "运行测试用例", "放行"),
        ("讨论1", "测试一下", "拦截"),
        ("讨论2", "试试命令行", "拦截"),
        ("讨论3", "能不能读取文件", "拦截"),
        ("讨论4", "你支持Python吗", "拦截"),
        ("讨论5", "怎么用这个工具", "拦截"),
        ("讨论6", "我只是在测试功能", "拦截"),
        ("讨论7", "检查一下终端", "拦截"),
        ("讨论8", "验证一下这个", "拦截"),
        ("问句1", "你能做什么？", "拦截"),
        ("问句2", "这个怎么用？", "拦截"),
        ("边界1", "测试我写的代码", "放行"),
        ("边界2", "测试这个脚本", "放行"),
        ("边界3", "我想测试一下", "拦截"),
    ]
    
    for test_name, user_input, expected in tests:
        print_test(test_name, user_input, expected)
    
    print("\n" + "=" * 70)
    print("  测试完成")
    print("=" * 70)


if __name__ == "__main__":
    main()
