"""Schema quality regression tests — 持续验证，防止工具说明书质量滑坡。

Hermes 提出的 CI 检查：每次新增工具或修改 schema 时自动验证：
1. 每个工具 schema 的 description 非空
2. 每个参数的 description 非空
3. 拒绝已知的撒谎模式（schema 声称实现里不存在的功能）
"""

import importlib.util
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_TOOLS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")


def _load_tool_schemas():
    schemas = []
    for fname in sorted(os.listdir(_TOOLS_DIR)):
        if not fname.endswith(".py") or fname == "__init__.py":
            continue
        fpath = os.path.join(_TOOLS_DIR, fname)
        try:
            spec = importlib.util.spec_from_file_location(f"tq.{fname[:-3]}", fpath)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                s = getattr(mod, "TOOL_SCHEMA", None)
                # Empty dict = legacy obsidian-tools-style wrapper (schema lives in the individual tool files)
                if not s or s == {}:
                    continue
                fn = s.get("function", s)
                schemas.append((fname, fn))
        except Exception:
            pass
    return schemas


# ── 1. 每个工具必须有非空 description ──────────────────────────────

@pytest.mark.parametrize("fname,fn", _load_tool_schemas())
def test_schema_has_description(fname, fn):
    desc = fn.get("description", "")
    assert desc.strip(), f"{fname}: schema description 为空"

# ── 2. 每个参数必须有非空 description ──────────────────────────────

@pytest.mark.parametrize("fname,fn", _load_tool_schemas())
def test_params_have_description(fname, fn):
    params = fn.get("parameters", {})
    if not isinstance(params, dict):
        return  # 无参数工具，通过
    props = params.get("properties", {})
    for pname, pinfo in props.items():
        if not isinstance(pinfo, dict):
            continue
        desc = pinfo.get("description", "")
        assert desc.strip(), f"{fname}: 参数 '{pname}' 的 description 为空"

# ── 3. 拒绝已知的撒谎模式 ──────────────────────────────────────────

# 描述中声称的功能必须在实现里存在，否则就是撒谎 schema。
# 每个模式 = (pattern, 出现则该工具必须有对应实现)
LYING_PATTERNS = [
    (r"自动修复", "code_execution",
     "若宣称自动修复，则必须调用 llm_caller 且实现 _call_llm_for_fix"),
    (r"内联评论|针对特定代码行", "github_pr_comment",
     "若宣称内联评论，则 gh pr review 命令必须包含 --path/--line/--position"),
    (r"系统敏感目录.*确认", "list_directory",
     "若宣称敏感目录检查，则实现中必须调用 is_sensitive_path"),
    (r"Notion.*邮箱.*也[会能].*搜索", "wiki_rebuild",
     "若宣称搜索 Notion/邮箱，则实现必须有对应的 search 分支"),
    (r"链接到项目知识图谱", "review_to_obsidian",
     "若宣称知识图谱链接，则实现中必须有对应的 linking 逻辑"),
]


@pytest.mark.parametrize("fname,fn", _load_tool_schemas())
def test_no_lying_patterns(fname, fn):
    desc = fn.get("description", "")
    for pattern, tool_file, explanation in LYING_PATTERNS:
        if fname == tool_file + ".py":
            import re
            assert not re.search(pattern, desc), (
                f"{fname}: schema 声称了已不存在的功能（{explanation}）\n"
                f"  匹配模式: '{pattern}'\n"
                f"  当前描述: {desc[:120]}..."
            )

# ── 4. 参数类型声明必须合法 ────────────────────────────────────────

VALID_TYPES = {"string", "integer", "number", "boolean", "array", "object"}


@pytest.mark.parametrize("fname,fn", _load_tool_schemas())
def test_valid_param_types(fname, fn):
    params = fn.get("parameters", {})
    if not isinstance(params, dict):
        return
    props = params.get("properties", {})
    for pname, pinfo in props.items():
        if not isinstance(pinfo, dict):
            continue
        ptype = pinfo.get("type", "")
        assert ptype in VALID_TYPES, f"{fname}: 参数 '{pname}' 的类型 '{ptype}' 不合法。允许: {VALID_TYPES}"
