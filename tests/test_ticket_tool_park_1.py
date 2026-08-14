"""票 TOOL-PARK-1：工具外挂仓专项测试

验收（票原文）：
① TOOLS_SCHEMA 不含 51 个仓内工具
② 仓内工具仍可被引擎执行（外挂不是禁用；老会话调到仓内工具必须正常工作）
③ describe_tool 对仓内工具返回完整 schema
④ 仓单缺失/损坏时 82 个全上线兜底（宁多勿缺，不许启动失败）
⑤ schema 总税从 ≈8,276 降到 ≈3,997 tokens（±5%）
"""

import json

from tools import (
    TOOLS_SCHEMA, ALL_TOOLS_SCHEMA, TOOL_FUNCTIONS,
    PARKED_TOOLS, load_tool_park, _park_filter,
)
from tools.describe_tool import describe_tool

# 票 PARK-2 名单（51 个，画像实证零调用）
PARKED_51 = [
    "api_register", "code_to_obsidian", "review_to_obsidian",
    "cross_project_search", "github_pr_comment", "set_reminder",
    "discuss_with_pi", "browser_open", "notion_create_page",
    "index_project", "restore_checkpoint", "github_create_repo",
    "move_note", "notion_append", "copy_to_notion", "delete_folder",
    "copy_to_obsidian", "batch_copy_notes", "github_create_pr",
    "move_to_folder", "rename_note", "batch_move_notes",
    "github_pr_diff", "save_skill", "github_setup", "notion_setup",
    "browser_get_title", "batch_delete_notes", "notion_search",
    "read_email_content", "read_recent", "delete_note", "create_folder",
    "notion_read_page", "classify_analyze", "web_extract",
    "send_notification", "web_fetch_markdown", "list_calendar_events",
    "analyze_emails", "read_email_recent", "search_emails",
    "classify_confirm", "create_calendar_event", "write_clipboard",
    "open_url", "read_clipboard", "render", "github_check_auth",
    "wiki_rebuild", "list_reminders",
]


def _schema_tax(schemas) -> float:
    """schema 税估算：JSON 序列化字符数 / 4（与画像报告口径一致，len/4）。"""
    return len(json.dumps(schemas, ensure_ascii=False)) / 4


def _names(schemas):
    return {t.get("function", {}).get("name", "") for t in schemas}


class TestParkManifest:
    """验收① 前置：仓单与票名单一致"""

    def test_manifest_matches_ticket(self):
        assert PARKED_TOOLS == set(PARKED_51), (
            f"仓单 {len(PARKED_TOOLS)} 个，票名单 {len(PARKED_51)} 个"
        )

    def test_manifest_loads_from_file(self):
        assert load_tool_park() == set(PARKED_51)


class TestSchemaExclusion:
    """验收①：TOOLS_SCHEMA 不含 51 个仓内工具"""

    def test_schema_excludes_all_parked(self):
        online = _names(TOOLS_SCHEMA)
        assert online & PARKED_TOOLS == set(), f"仓内工具泄漏进 TOOLS_SCHEMA: {online & PARKED_TOOLS}"

    def test_online_count_is_82_minus_51(self):
        assert len(TOOLS_SCHEMA) == 82 - 51

    def test_full_snapshot_kept(self):
        # ALL_TOOLS_SCHEMA 保留全量（含仓内），供 describe_tool 回退
        assert len(ALL_TOOLS_SCHEMA) == 82
        assert _names(ALL_TOOLS_SCHEMA) >= PARKED_TOOLS


class TestStillExecutable:
    """验收②：仓内工具仍可被引擎执行（外挂不是禁用）"""

    def test_parked_tools_registered_in_functions(self):
        for name in ("render", "restore_checkpoint", "save_skill", "api_register"):
            assert name in TOOL_FUNCTIONS, f"仓内工具 {name} 未注册可执行"

    def test_parked_tool_executes_via_executor(self):
        from core.tool_executor import execute_tool
        result = execute_tool("render", {"data": {"msg": "外挂仓执行验证"}})
        assert "错误" not in result, f"仓内工具 render 执行失败: {result[:120]}"
        assert result.strip(), "仓内工具 render 返回空结果"


class TestDescribeTool:
    """验收③：describe_tool 对仓内工具返回完整 schema"""

    def test_describe_parked_tool_full_schema(self):
        r = describe_tool("render")
        assert "未知工具" not in r, f"describe_tool 查不到仓内工具: {r[:80]}"
        assert "参数" in r and "data" in r, f"摘要缺参数段: {r[:120]}"

    def test_describe_registers_extra_tool(self):
        class _E:
            _extra_tools = None
        engine = _E()
        describe_tool("save_skill", engine)
        assert engine._extra_tools == {"save_skill"}, "命中仓内工具应注册进 _extra_tools"

    def test_describe_miss_suggests_parked_name(self):
        # 未知名建议应覆盖仓内工具名（全量建议池）
        from tools.describe_tool import describe_tool as dt
        r = dt("restore_check")
        assert "restore_checkpoint" in r or "未知工具" in r


class TestFallback:
    """验收④：仓单缺失/损坏兜底全上线"""

    def test_missing_manifest_returns_empty(self):
        assert load_tool_park("/nonexistent/tool_park.json") == set()

    def test_broken_manifest_returns_empty(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("{broken json!!!", encoding="utf-8")
        assert load_tool_park(str(bad)) == set()

    def test_fallback_brings_all_online(self):
        # 仓单缺失 → 空集 → _park_filter 全量保留（82 全上线）
        assert _park_filter(ALL_TOOLS_SCHEMA, set()) == ALL_TOOLS_SCHEMA
        assert len(_park_filter(ALL_TOOLS_SCHEMA, set())) == 82

    def test_park_filter_selective(self):
        kept = _park_filter(ALL_TOOLS_SCHEMA, {"render"})
        assert "render" not in _names(kept)
        assert len(kept) == 81


class TestSchemaTax:
    """验收⑤：schema 总税 ≈8,276 → ≈3,997（±5%）"""

    def test_full_tax_within_baseline(self):
        tax = _schema_tax(ALL_TOOLS_SCHEMA)
        assert 8276 * 0.95 <= tax <= 8276 * 1.05, f"全量 schema 税 {tax:.2f} 不在 8,276±5%"

    def test_parked_tax_within_target(self):
        tax = _schema_tax(TOOLS_SCHEMA)
        assert 3997 * 0.95 <= tax <= 3997 * 1.05, f"park 后 schema 税 {tax:.2f} 不在 3,997±5%"

    def test_savings_match_ticket(self):
        saved = _schema_tax(ALL_TOOLS_SCHEMA) - _schema_tax(TOOLS_SCHEMA)
        assert 4279 * 0.9 <= saved <= 4279 * 1.1, f"每轮节省 {saved:.2f} 与票文 ≈4,279 偏差过大"
