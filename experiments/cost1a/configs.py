#!/usr/bin/env python3
"""四档工具配置（TICKET-COST-1A-SANDBOX）。

- A 现状档：PARK-1 后 31 个在线工具（对照组）
- B 合并档：14 个 = 7 核心 + 7 家族合并工具（action 枚举分发）
- C 极简档：8 个核心工具
- D 全量档：82 个（外挂仓全放出，历史对照）

schema 全部从 tools/TOOLS_SCHEMA / ALL_TOOLS_SCHEMA 原样取，合并档改写 name/action。
"""

from __future__ import annotations

import copy
from tools import TOOLS_SCHEMA, ALL_TOOLS_SCHEMA

# ── 8 个核心工具（C 档 / B 档基底）──────────────────────────────
CORE_8 = [
    "read_local_file",
    "edit_file",
    "execute_terminal",
    "grep_code",
    "list_directory",
    "load_result",
    "save_memory",
    "web_search",
]

# ── 7 个家族（B 档合并；每族一个工具 + action 枚举）──────────────
FAMILIES = {
    "obsidian_tool": [
        "read_obsidian", "write_obsidian", "append_obsidian", "search_obsidian",
        "list_folder", "create_folder", "delete_folder", "move_note",
        "rename_note", "delete_note", "copy_to_obsidian", "code_to_obsidian",
        "review_to_obsidian", "batch_copy_notes", "batch_move_notes",
        "batch_delete_notes",
    ],
    "notion_tool": [
        "notion_create_page", "notion_append", "notion_read_page",
        "notion_search", "copy_to_notion", "notion_setup",
    ],
    "github_tool": [
        "github_create_repo", "github_create_pr", "github_pr_diff",
        "github_pr_comment", "github_check_auth", "github_setup",
    ],
    "web_tool": [
        "web_search", "web_fetch", "web_fetch_markdown", "web_extract",
        "open_url", "browser_get_title", "browser_open",
    ],
    "email_tool": [
        "read_email_content", "read_email_recent", "search_emails",
        "analyze_emails",
    ],
    "calendar_tool": [
        "set_reminder", "list_reminders", "create_calendar_event",
        "list_calendar_events",
    ],
    "clipboard_tool": [
        "write_clipboard", "read_clipboard",
    ],
}


def _schema_by_name(name: str) -> dict | None:
    """从全量注册表按名取 schema（原样）。"""
    for t in ALL_TOOLS_SCHEMA:
        if t.get("function", {}).get("name", "") == name:
            return copy.deepcopy(t)
    return None


def _core_schemas(names: list[str]) -> list[dict]:
    """取核心工具 schema（从在线表取；缺失回退全量表）。"""
    out = []
    for n in names:
        s = next((t for t in TOOLS_SCHEMA if t.get("function", {}).get("name") == n), None)
        if s is None:
            s = _schema_by_name(n)
        if s is not None:
            out.append(copy.deepcopy(s))
    return out


def _family_tool_schema(merged_name: str, members: list[str]) -> dict:
    """构建家族合并工具 schema：name=merged_name，action 枚举=成员名，描述=合并原文。"""
    descs = []
    for m in members:
        s = _schema_by_name(m)
        if s:
            d = s.get("function", {}).get("description", "") or ""
            descs.append(f"{m}: {d}")
    return {
        "type": "function",
        "function": {
            "name": merged_name,
            "description": (
                f"合并工具（TICKET-COST-1A）：覆盖 {len(members)} 个亲缘动作。"
                "用 action 参数选择具体动作；其余参数与对应原工具一致。\n"
                + "\n".join(descs)
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": members,
                        "description": "要执行的具体动作（原工具名）。",
                    },
                },
                "required": ["action"],
            },
        },
    }


def config_a() -> list[dict]:
    """A 现状档：PARK-1 后 31 个在线工具。"""
    return copy.deepcopy(TOOLS_SCHEMA)


def config_b() -> list[dict]:
    """B 合并档：7 核心（无 web_search，并入 web_tool）+ 7 家族合并工具 = 14。"""
    core7 = [n for n in CORE_8 if n != "web_search"]
    schemas = _core_schemas(core7)
    for merged, members in FAMILIES.items():
        schemas.append(_family_tool_schema(merged, members))
    return schemas


def config_c() -> list[dict]:
    """C 极简档：8 个核心工具。"""
    return _core_schemas(CORE_8)


def config_d() -> list[dict]:
    """D 全量档：82 个（外挂仓全放出）。"""
    return copy.deepcopy(ALL_TOOLS_SCHEMA)


CONFIGS = {
    "A": config_a,
    "B": config_b,
    "C": config_c,
    "D": config_d,
}

# 各档工具名集合（供测试/统计）
def config_names(cfg: str) -> set[str]:
    return {t.get("function", {}).get("name", "") for t in CONFIGS[cfg]()}


def validate() -> dict[str, int]:
    """四档工具数（票验收：31/14/8/82）。"""
    return {k: len(v()) for k, v in CONFIGS.items()}
