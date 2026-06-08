"""工具目录 - 自动发现所有工具"""

import sys
import importlib.util
from pathlib import Path

TOOL_FUNCTIONS = {}
TOOLS_SCHEMA = []

def register_tool(name, func, schema):
    TOOL_FUNCTIONS[name] = func
    TOOLS_SCHEMA.append(schema)

def discover_tools():
    current_dir = Path(__file__).parent
    
    for py_file in current_dir.glob("*.py"):
        if py_file.name == "__init__.py":
            continue
        if py_file.name == "execute_skill.py":
            continue  # 跳过有问题的工具
        
        try:
            spec = importlib.util.spec_from_file_location(f"tools.{py_file.stem}", py_file)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                if hasattr(module, 'register'):
                    module.register(register_tool)
        except Exception as e:
            pass

discover_tools()

# 过滤掉空的或有问题的工具
valid_schemas = []
for tool in TOOLS_SCHEMA:
    if tool and isinstance(tool, dict):
        if 'function' in tool and tool['function']:
            valid_schemas.append(tool)
        elif 'name' in tool:
            valid_schemas.append({"type": "function", "function": tool})
TOOLS_SCHEMA[:] = valid_schemas

print(f"✅ 已加载 {len(TOOLS_SCHEMA)} 个有效工具", file=sys.stderr)
