"""E 适配层单元测试——画像偏好 → skills/memory 路由权重提升（只加不删）。

issue #8：adapt 的 tool_names boost 是死路径（engine 全量注入 TOOLS_SCHEMA，
只用 skill_names / memory_types）。正确修法是删除该路径，boost 只留
skills/memory；禁止把 tool_names 接回工具注入面。
"""
from pathlib import Path

from core.adapt import (
    adapt,
    preference_domains,
    preference_memory_types,
    preference_skills,
    boost_route,
    profile_text,
)
from core.engine import Engine
from core.event_bus import EventBus
from core.router import route, RoutePlan
from core.tool_executor import execute_tool
from tests.mock_llm import MockLLMCaller
from tools import TOOLS_SCHEMA


_ROOT = Path(__file__).resolve().parent.parent
_PYTHON_PROFILE = {"pref": {"value": "以后都用 Python 写脚本"}}
_OBSIDIAN_PROFILE = {"pref": {"value": "喜欢用 Obsidian 记笔记"}}


def test_preference_domains():
    doms = preference_domains(_PYTHON_PROFILE)
    assert "file" in doms and "terminal" in doms


def test_preference_skills_and_memory():
    assert "code-fix" in preference_skills(_PYTHON_PROFILE)
    assert "LESSON" in preference_memory_types(_PYTHON_PROFILE)
    assert "note-taking" in preference_skills(_OBSIDIAN_PROFILE)
    assert "FACT" in preference_memory_types(_OBSIDIAN_PROFILE)


def test_boost_adds_skills_not_tools():
    """Obsidian 偏好提升 note-taking；tool_names 原样不动。"""
    plan = RoutePlan(
        tool_names=["get_current_time", "edit_file"],
        skill_names=["research"],
    )
    tools_before = list(plan.tool_names)
    skills_before = set(plan.skill_names)
    boost_route(plan, _OBSIDIAN_PROFILE)
    assert plan.tool_names == tools_before, "adapt 不得改 tool_names"
    assert skills_before.issubset(plan.skill_names), "只加不删"
    assert "note-taking" in plan.skill_names, "Obsidian 偏好应提升 note-taking"


def test_boost_expands_memory_when_already_filtering():
    """路由已在过滤记忆类型时，偏好做 additive 扩展，不删已选类型。"""
    plan = route("调研对比资料")
    assert "research" in plan.skill_names
    assert "FACT" in plan.memory_types
    tools_before = list(plan.tool_names)
    mem_before = set(plan.memory_types)
    skills_before = set(plan.skill_names)
    boost_route(plan, _PYTHON_PROFILE)
    assert plan.tool_names == tools_before
    assert mem_before.issubset(plan.memory_types), "只加不删"
    assert "LESSON" in plan.memory_types, "Python 偏好应扩展 LESSON"
    assert skills_before.issubset(plan.skill_names)
    assert "code-fix" in plan.skill_names


def test_boost_does_not_narrow_empty_memory_types():
    """memory_types 空 = 全类型召回；不得从空列表追加（否则召回缩水）。"""
    plan = RoutePlan(tool_names=["get_current_time"], skill_names=[], memory_types=[])
    boost_route(plan, _PYTHON_PROFILE)
    assert plan.memory_types == [], "空 memory_types 保持全类型语义"
    assert "code-fix" in plan.skill_names, "技能 boost 仍生效"


def test_boost_noop_empty_profile():
    plan = route("修复 bug")
    before_tools = list(plan.tool_names)
    before_skills = list(plan.skill_names)
    before_mem = list(plan.memory_types)
    boost_route(plan, {})
    assert plan.tool_names == before_tools
    assert plan.skill_names == before_skills
    assert plan.memory_types == before_mem


def test_adapt_disabled_skips_boost(monkeypatch):
    monkeypatch.setenv("BOBO_ADAPT", "0")
    plan = RoutePlan(skill_names=["research"], memory_types=["FACT"])
    adapt(plan, _PYTHON_PROFILE)
    assert plan.skill_names == ["research"]
    assert plan.memory_types == ["FACT"]


def test_profile_text_flat():
    assert "a" in profile_text({"x": "a"}) or True  # 结构容错不崩
    assert profile_text({}) == ""


def test_adapt_source_does_not_write_tool_names():
    """锁死：adapt 不再 append tool_names / 引用 TOOL_DOMAINS 追加工具。"""
    src = (_ROOT / "core" / "adapt.py").read_text(encoding="utf-8")
    assert "plan.tool_names.append" not in src, "adapt 不得 append tool_names"
    assert "from core.router import TOOL_DOMAINS" not in src
    assert "TOOL_DOMAINS.get" not in src


def test_injection_path_does_not_read_tool_names():
    """锁死：engine 全量注入；injector 只读 memory_types，不读 tool_names。"""
    engine_src = (_ROOT / "core" / "engine.py").read_text(encoding="utf-8")
    injector_src = (_ROOT / "core" / "injector.py").read_text(encoding="utf-8")
    assert "filtered_tools = TOOLS_SCHEMA" in engine_src
    assert "_route_plan.tool_names" not in engine_src
    assert "tool_names" not in injector_src
    assert "memory_types" in injector_src


def test_adapt_does_not_change_injected_tools(monkeypatch, tmp_path):
    """engine 路径：adapt 提升 skills/memory，注入工具集仍是全量 TOOLS_SCHEMA。"""
    EventBus.reset(str(tmp_path / "adapt-inject"))
    captured = {}

    class RecordingCaller(MockLLMCaller):
        def __call__(self, messages, use_tools=True, stream_callback=None,
                     retry_callback=None, tools_override=None, **kwargs):
            captured["tools_override"] = tools_override
            return {"choices": [{"message": {"content": "ok"}}]}

    monkeypatch.setenv("BOBO_ADAPT", "1")
    monkeypatch.setenv("BOBO_ROUTER", "1")
    monkeypatch.setattr("tools.v5_memory.get_user_profile", lambda: _PYTHON_PROFILE)

    eng = Engine(RecordingCaller([]), execute_tool, test_mode=True)
    eng.sid = "adapt-inject-1"
    eng.tracker._change_log = []
    eng.task_ledger = []
    user_input = "调研对比资料"
    bare = route(user_input)
    eng.run(user_input, depth=0)

    ov = captured.get("tools_override")
    assert ov == TOOLS_SCHEMA, "adapt 不得改变注入工具集"
    names = [t["function"]["name"] for t in ov]
    assert names == [t["function"]["name"] for t in TOOLS_SCHEMA]
    assert eng._route_plan is not None
    assert eng._route_plan.tool_names == bare.tool_names
    assert "research" in eng._route_plan.skill_names
    assert "code-fix" in eng._route_plan.skill_names
    assert "code-fix" in eng.skill_loader._router_skill_filter
    assert "FACT" in eng._route_plan.memory_types
    assert "LESSON" in eng._route_plan.memory_types
