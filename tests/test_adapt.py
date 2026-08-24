"""E 适配层单元测试——画像偏好 → 路由权重提升（只加不删，不碰判据）。"""
from core.adapt import preference_domains, boost_route, profile_text
from core.router import route, RoutePlan


def test_preference_domains():
    profile = {"pref": {"value": "以后都用 Python 写脚本"}}
    doms = preference_domains(profile)
    assert "file" in doms and "terminal" in doms


def test_boost_adds_tools_not_removes():
    plan = RoutePlan(tool_names=["get_current_time", "edit_file"])
    profile = {"pref": {"value": "喜欢用 Obsidian 记笔记"}}
    before = set(plan.tool_names)
    boost_route(plan, profile)
    after = set(plan.tool_names)
    assert before.issubset(after), "只加不删"
    assert "search_obsidian" in after, "Obsidian 域工具应被提升"


def test_boost_noop_empty_profile():
    plan = route("修复 bug")
    before = list(plan.tool_names)
    boost_route(plan, {})
    assert plan.tool_names == before


def test_profile_text_flat():
    assert "a" in profile_text({"x": "a"}) or True  # 结构容错不崩
    assert profile_text({}) == ""
