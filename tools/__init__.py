"""工具目录 - 自动发现所有工具"""

import sys
import importlib.util
import re
from pathlib import Path

TOOL_FUNCTIONS = {}
TOOLS_SCHEMA = []
TOOL_CHECKS = {}  # tool_name -> callable returning bool

def register_tool(name, func, schema, check_fn=None):
    TOOL_FUNCTIONS[name] = func
    TOOLS_SCHEMA.append(schema)
    if check_fn is not None:
        TOOL_CHECKS[name] = check_fn

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

# 过滤 + 按名称去重（DeepSeek API 要求工具名称唯一）
seen_names = set()
unique_schemas = []
for tool in TOOLS_SCHEMA:
    if tool and isinstance(tool, dict):
        if 'function' in tool and tool['function']:
            schema = tool
        elif 'name' in tool:
            schema = {"type": "function", "function": tool}
        else:
            continue
        
        name = schema.get("function", {}).get("name", "")
        if not name:
            continue  # 跳过空 schema
        if name and name in seen_names:
            continue  # 跳过重复的工具名
        if name:
            seen_names.add(name)
        unique_schemas.append(schema)

# 根据 check_fn 过滤不可用的工具
before_gate = len(unique_schemas)
gated_schemas = []
for tool in unique_schemas:
    name = tool.get("function", {}).get("name", "")
    check = TOOL_CHECKS.get(name)
    if check is not None:
        try:
            if not check():
                continue  # 跳过不可用的工具
        except Exception:
            continue  # check 异常时保守跳过
    gated_schemas.append(tool)

TOOLS_SCHEMA[:] = gated_schemas

gated_count = before_gate - len(gated_schemas)
if gated_count > 0:
    print(f" 已过滤 {gated_count} 个不可用工具，可用 {len(gated_schemas)} 个", file=sys.stderr)
else:
    print(f" 已加载 {len(TOOLS_SCHEMA)} 个有效工具（去重后）", file=sys.stderr)

# ── 技能作为动态工具注册 ──
from core.skill_manager import get_skill_manager
_skill_mgr = get_skill_manager()
TOOLS_SCHEMA[:] = gated_schemas
print(f" 含技能工具: 共 {len(TOOLS_SCHEMA)} 个工具", file=sys.stderr)
