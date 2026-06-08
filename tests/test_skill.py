#!/usr/bin/env python3
"""
测试 coding_master Skill
"""

import sys
import os


from core.tool_executor import execute_tool

GREEN = '\033[92m'
CYAN = '\033[96m'
YELLOW = '\033[93m'
RESET = '\033[0m'


def load_skill(skill_name):
    import yaml
    skill_path = f"skills/{skill_name}.yaml"
    if not os.path.exists(skill_path):
        return None
    with open(skill_path, 'r') as f:
        return yaml.safe_load(f)


def resolve_vars(value, context):
    if isinstance(value, str):
        for k, v in context.items():
            value = value.replace(f'{{{k}}}', str(v))
        return value
    elif isinstance(value, dict):
        return {k: resolve_vars(v, context) for k, v in value.items()}
    return value


def execute_skill(skill, context):
    print(f"\n  {CYAN}▶ 执行 Skill: {skill['name']}{RESET}")
    
    steps = skill.get('steps', [])
    for i, step in enumerate(steps, 1):
        print(f"\n  {YELLOW}步骤 {i}: {step['name']}{RESET}")
        
        if 'tool' in step:
            args = resolve_vars(step['args'].copy(), context)
            print(f"    ⚙ {step['tool']}")
            result = execute_tool(step['tool'], args)
            if result:
                preview = result.split('\n')[0][:80]
                print(f"    ✓ {preview}")
            else:
                print(f"    ✓ 完成")
    
    return True


def test_coding_master():
    print("\n" + "=" * 70)
    print("  🧪 测试: coding_master Skill")
    print("=" * 70)
    
    skill = load_skill("coding_master")
    if not skill:
        print("❌ Skill 未找到")
        return
    
    # 使用当前目录的完整路径
    current_dir = os.getcwd()
    context = {
        "file_path": os.path.join(current_dir, "test_calc.py"),
        "code_content": '''def add(a, b):
    return a + b

print("5 + 3 =", add(5, 3))
'''
    }
    
    print(f"\n  用户: 写一个计算器程序")
    print(f"  文件: {context['file_path']}\n")
    
    execute_skill(skill, context)
    
    # 验证文件是否创建
    if os.path.exists(context['file_path']):
        print(f"\n  {GREEN}✅ 文件已创建: {context['file_path']}{RESET}")
        # 清理
        os.remove(context['file_path'])
    
    print(f"\n  {GREEN}✅ Skill 测试完成{RESET}")


if __name__ == "__main__":
    import yaml
    test_coding_master()
