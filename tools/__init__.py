"""工具目录 - 自动发现所有工具"""

import sys
import logging
import importlib.util
import json
import re
from pathlib import Path

logger = logging.getLogger(__name__)

TOOL_FUNCTIONS = {}
TOOLS_SCHEMA = []
ALL_TOOLS_SCHEMA = []  # 全量快照（含外挂仓内工具），describe_tool 回退查询用（票 TOOL-PARK-1）
TOOL_CHECKS = {}  # tool_name -> callable returning bool

_LOAD_ERRORS: list[tuple[str, str]] = []  # (文件名, 错误摘要) — 加载失败的工具

# ── 票 TOOL-PARK-1：工具外挂仓 ──
_PARK_FILE = Path(__file__).resolve().parent.parent / "data" / "tool_park.json"


def load_tool_park(park_path=None) -> set[str]:
    """读外挂仓单（data/tool_park.json）：{"parked": [工具名...]}。

    仓单缺失/损坏 → 返回空集（兜底：全部工具照常上线，宁多勿缺，不许启动失败）。
    """
    path = Path(park_path) if park_path else _PARK_FILE
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        parked = data.get("parked", [])
        if not isinstance(parked, list):
            return set()
        return {str(n).strip() for n in parked if str(n).strip()}
    except Exception:
        return set()


def _park_filter(schemas, parked: set[str]) -> list[dict]:
    """剔除仓内工具的 schema（保持顺序）。

    仓内工具只是不 advertised（不进 prompt schema），函数照常注册可执行。
    """
    if not parked:
        return list(schemas)
    return [t for t in schemas
            if t.get("function", {}).get("name", "") not in parked]

def report_load_errors() -> str:
    """返回工具加载失败的启动警告文本；无失败时返回空串。"""
    if not _LOAD_ERRORS:
        return ""
    details = "；".join(f"{fname} ({summary})" for fname, summary in _LOAD_ERRORS)
    return f"⚠️ {len(_LOAD_ERRORS)} 个工具加载失败：{details}"

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
        
        try:
            spec = importlib.util.spec_from_file_location(f"tools.{py_file.stem}", py_file)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                if hasattr(module, 'register'):
                    module.register(register_tool)
        except Exception as e:
            summary = f"{type(e).__name__}: {e}"
            _LOAD_ERRORS.append((py_file.name, summary))
            logger.exception("工具加载失败: %s", py_file.name)

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

TOOLS_SCHEMA[:] = gated_schemas

# ── 票 TOOL-PARK-1：外挂仓装配（在 check_fn 过滤后执行） ──
# 1. 全量快照先留——describe_tool 对仓内工具仍返回完整 schema（验收③）
ALL_TOOLS_SCHEMA[:] = list(gated_schemas)
# 2. 仓内工具 schema 不进 prompt（每轮省 ≈4,279 tokens），函数照常可执行（外挂不是禁用）
PARKED_TOOLS = load_tool_park()
TOOLS_SCHEMA[:] = _park_filter(gated_schemas, PARKED_TOOLS)
if PARKED_TOOLS:
    print(f" 外挂仓 {len(PARKED_TOOLS)} 个工具已打包（不进 prompt，仍可执行），"
          f"上线 {len(TOOLS_SCHEMA)} 个", file=sys.stderr)
