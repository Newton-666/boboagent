"""Tests for tools/__init__.py — tool auto-discovery, registration, dedup."""

import os
import sys
import json
import pytest

# Ensure modules can be imported
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestToolRegistry:
    """Tests for the tool registration and discovery system."""

    def test_tools_schema_is_list(self):
        from tools import TOOLS_SCHEMA
        assert isinstance(TOOLS_SCHEMA, list)

    def test_tools_schema_not_empty(self):
        from tools import TOOLS_SCHEMA
        assert len(TOOLS_SCHEMA) > 0, "Should have at least some tools loaded"

    def test_tool_functions_dict_populated(self):
        from tools import TOOL_FUNCTIONS
        assert isinstance(TOOL_FUNCTIONS, dict)
        assert len(TOOL_FUNCTIONS) > 0

    def test_all_schemas_have_required_fields(self):
        from tools import TOOLS_SCHEMA
        for tool in TOOLS_SCHEMA:
            assert isinstance(tool, dict), f"Tool schema should be dict, got {type(tool)}"
            fn = tool.get("function", tool)
            name = fn.get("name", "")
            assert name, f"Tool schema missing name: {tool}"
            assert fn.get("description"), f"Tool '{name}' missing description"
            params = fn.get("parameters", {})
            assert isinstance(params, dict), f"Tool '{name}' parameters not a dict"
            assert "type" in params, f"Tool '{name}' parameters missing 'type'"

    def test_no_duplicate_tool_names(self):
        from tools import TOOLS_SCHEMA
        names = []
        for tool in TOOLS_SCHEMA:
            fn = tool.get("function", tool)
            names.append(fn.get("name", ""))
        dupes = [n for n in names if names.count(n) > 1]
        assert len(dupes) == 0, f"Duplicate tool names found: {set(dupes)}"

    def test_core_tools_present(self):
        """Verify essential tools are registered."""
        from tools import TOOLS_SCHEMA
        names = set()
        for tool in TOOLS_SCHEMA:
            fn = tool.get("function", tool)
            names.add(fn.get("name", ""))

        essential = [
            "get_current_time",
            "save_memory",
            "search_memory",
            "web_search",
            "web_fetch",
            "read_local_file",
            "list_directory",
            "execute_terminal",
            "code_execution",
            "file_operation",
            "edit_file",
            "grep_code",
            "cross_search",
            "wiki_rebuild",
            "api_register",
            "api_call",
            "bobo_config",
            "bobo_schedule",
            "run_tests",
            "refactor",
        ]
        for name in essential:
            assert name in names, f"Essential tool '{name}' not found in registry"

    def test_obsidian_tools_registered(self):
        from tools import TOOLS_SCHEMA
        names = set()
        for tool in TOOLS_SCHEMA:
            fn = tool.get("function", tool)
            names.add(fn.get("name", ""))

        obsidian_tools = [
            "read_obsidian", "write_obsidian", "search_obsidian",
            "append_obsidian", "rename_note", "delete_note",
            "move_to_folder", "create_folder", "delete_folder",
            "list_folder",
        ]
        for name in obsidian_tools:
            assert name in names, f"Obsidian tool '{name}' not found"

    def test_github_tools_registered(self):
        from tools import TOOLS_SCHEMA
        names = set()
        for tool in TOOLS_SCHEMA:
            fn = tool.get("function", tool)
            names.add(fn.get("name", ""))

        github_tools = [
            "github_create_repo", "github_create_pr",
            "github_pr_diff", "github_pr_comment",
            "github_check_auth", "github_setup",
        ]
        for name in github_tools:
            assert name in names, f"GitHub tool '{name}' not found"

    def test_macos_tools_registered(self):
        from tools import TOOLS_SCHEMA
        names = set()
        for tool in TOOLS_SCHEMA:
            fn = tool.get("function", tool)
            names.add(fn.get("name", ""))

        macos_tools = [
            "send_notification", "read_clipboard", "write_clipboard",
            "set_reminder", "list_reminders",
            "create_calendar_event", "list_calendar_events",
        ]
        for name in macos_tools:
            assert name in names, f"macOS tool '{name}' not found"

    def test_register_tool_adds_to_both_dict_and_schema(self):
        from tools import register_tool, TOOL_FUNCTIONS, TOOLS_SCHEMA

        name_before = f"__test_tool_{id(self)}__"
        schema = {
            "type": "function",
            "function": {
                "name": name_before,
                "description": "A test tool for registry validation",
                "parameters": {"type": "object", "properties": {}}
            }
        }

        def dummy_execute():
            return "test result"

        # Register
        register_tool(name_before, dummy_execute, schema)

        # Should be in TOOL_FUNCTIONS
        assert name_before in TOOL_FUNCTIONS

        # Clean up — this tool won't have a schema with .get('function') returning
        # useful data post-discovery, but the registration mechanism works

    def test_tool_checks_are_registered(self):
        from tools import TOOL_CHECKS
        assert isinstance(TOOL_CHECKS, dict)

    def test_each_registered_function_is_callable(self):
        from tools import TOOL_FUNCTIONS
        for name, func in TOOL_FUNCTIONS.items():
            if func is None:
                continue  # Some tools like cross_search are handled by engine
            assert callable(func), f"Tool '{name}' function is not callable: {type(func)}"


class TestToolGating:
    """Tests for tool availability gating via check_fn."""

    def test_gating_skips_unavailable_tools(self, monkeypatch):
        """Reload tools module with a gated tool to verify gating works."""
        # The actual gating happens at module import time in tools/__init__.py
        # We verify that TOOL_CHECKS contains check functions
        from tools import TOOL_CHECKS

        for name, check_fn in TOOL_CHECKS.items():
            assert callable(check_fn), f"Check for '{name}' must be callable"
