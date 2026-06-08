#!/usr/bin/env python3
"""
Bobo 独立配置工具 - 不依赖任何项目文件
直接修改 ~/.bobo/.env 配置文件
"""

import os
import sys
from pathlib import Path

# 颜色
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'
BOLD = '\033[1m'

def get_env_file():
    """获取配置文件路径"""
    home_env = Path.home() / ".bobo" / ".env"
    home_env.parent.mkdir(parents=True, exist_ok=True)
    return home_env

def load_env():
    """加载配置"""
    env_file = get_env_file()
    env_vars = {}
    if env_file.exists():
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    if '=' in line:
                        key, value = line.split('=', 1)
                        env_vars[key] = value
    return env_file, env_vars

def save_env(env_file, env_vars):
    """保存配置"""
    with open(env_file, 'w') as f:
        f.write("# Bobo 配置文件\n")
        f.write(f"# 最后修改: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        for key, value in env_vars.items():
            f.write(f"{key}={value}\n")

def show_config(env_vars):
    """显示配置"""
    print(f"\n{BOLD}{BLUE}当前配置:{RESET}")
    print(f"  {BOLD}API Key:{RESET} {env_vars.get('DEEPSEEK_API_KEY', '未设置')[:10]}..." if env_vars.get('DEEPSEEK_API_KEY') else "  API Key: 未设置")
    print(f"  {BOLD}Obsidian 路径:{RESET} {env_vars.get('OBSIDIAN_VAULT', '未设置')}")
    print(f"  {BOLD}模型:{RESET} {env_vars.get('API_MODEL_NAME', 'deepseek-chat')}")
    print(f"  {BOLD}Bobo 文件夹:{RESET} {env_vars.get('BOBO_FOLDER', 'Bobo数据库')}")

def set_api_key():
    """只设置 API Key"""
    env_file, env_vars = load_env()
    print(f"\n{BOLD}🔑 设置 API Key{RESET}")
    print(f"{YELLOW}获取 API Key: https://platform.deepseek.com/api_keys{RESET}\n")
    api_key = input("请输入 DeepSeek API Key: ").strip()
    if api_key:
        env_vars['DEEPSEEK_API_KEY'] = api_key
        save_env(env_file, env_vars)
        print(f"\n{GREEN}✅ API Key 已保存{RESET}")
    else:
        print(f"\n{RED}❌ 未输入，取消设置{RESET}")

def set_obsidian_path():
    """只设置 Obsidian 路径"""
    env_file, env_vars = load_env()
    print(f"\n{BOLD}📁 设置 Obsidian 路径{RESET}")
    print(f"{YELLOW}示例: /Users/你的用户名/Desktop/Obsidian note{RESET}\n")
    path = input("请输入 Obsidian 仓库路径: ").strip()
    if path and os.path.exists(path):
        env_vars['OBSIDIAN_VAULT'] = path
        save_env(env_file, env_vars)
        print(f"\n{GREEN}✅ Obsidian 路径已保存{RESET}")
    elif path:
        print(f"\n{RED}❌ 路径不存在: {path}{RESET}")
    else:
        print(f"\n{RED}❌ 未输入，取消设置{RESET}")

def edit_all():
    """编辑全部配置"""
    env_file, env_vars = load_env()
    
    print(f"\n{BOLD}{BLUE}编辑全部配置{RESET}")
    print(f"{YELLOW}直接回车保留当前值{RESET}\n")
    
    # API Key
    current = env_vars.get('DEEPSEEK_API_KEY', '')
    masked = current[:10] + "..." if current else "空"
    new = input(f"API Key [{masked}]: ").strip()
    if new:
        env_vars['DEEPSEEK_API_KEY'] = new
    
    # Obsidian 路径
    current = env_vars.get('OBSIDIAN_VAULT', '')
    new = input(f"Obsidian 路径 [{current}]: ").strip()
    if new:
        env_vars['OBSIDIAN_VAULT'] = new
    
    # 模型
    current = env_vars.get('API_MODEL_NAME', 'deepseek-chat')
    new = input(f"模型名称 [{current}]: ").strip()
    if new:
        env_vars['API_MODEL_NAME'] = new
    
    # Bobo 文件夹
    current = env_vars.get('BOBO_FOLDER', 'Bobo数据库')
    new = input(f"Bobo 文件夹 [{current}]: ").strip()
    if new:
        env_vars['BOBO_FOLDER'] = new
    
    save_env(env_file, env_vars)
    print(f"\n{GREEN}✅ 配置已保存{RESET}")

def main():
    print(f"\n{BOLD}{BLUE}{'='*50}{RESET}")
    print(f"{BOLD}{BLUE}Bobo 独立配置工具{RESET}")
    print(f"{BOLD}{BLUE}{'='*50}{RESET}")
    
    _, env_vars = load_env()
    show_config(env_vars)
    
    print(f"\n{YELLOW}请选择操作:{RESET}")
    print(f"  1. 设置 API Key")
    print(f"  2. 设置 Obsidian 路径")
    print(f"  3. 编辑全部配置")
    print(f"  4. 退出")
    
    choice = input(f"\n请输入选项 [1-4]: ").strip()
    
    if choice == '1':
        set_api_key()
    elif choice == '2':
        set_obsidian_path()
    elif choice == '3':
        edit_all()
    else:
        print(f"\n{GREEN}再见！{RESET}")

if __name__ == "__main__":
    main()
