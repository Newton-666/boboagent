"""上下文管理 — 历史压缩、查询分类、工具过滤"""

import re
from typing import Optional


class ContextMixin:
    """为 Engine 提供上下文压缩和工具过滤能力。"""

    MAX_HISTORY_CHARS = 80000
    MAX_HISTORY_MESSAGES = 200
    KEEP_EXCHANGES = 3

    TOOL_CATEGORIES = {
        "general": [
            "get_current_time", "save_memory", "search_memory",
            "save_skill", "render", "project_info",
        ],
        "web": [
            "web_search", "web_fetch", "web_extract", "open_url",
            "browser_get_title", "browser_open",
        ],
        "obsidian": [
            "read_obsidian", "write_obsidian", "search_obsidian",
            "append_obsidian", "classify_analyze", "classify_confirm",
            "batch_copy_notes", "batch_delete_notes", "batch_move_notes",
            "create_folder", "delete_folder", "delete_note",
            "list_folder", "move_note", "move_to_folder",
            "rename_note", "read_recent",
        ],
        "email": [
            "search_emails", "read_email_content", "analyze_emails",
        ],
        "code": [
            "code_execution", "file_writer", "execute_terminal",
            "search_code", "refactor", "git_status",
        ],
        "file": [
            "read_local_file", "list_directory", "file_operation",
        ],
        "macos": [
            "send_notification", "read_clipboard", "write_clipboard",
            "set_reminder", "list_reminders",
            "create_calendar_event", "list_calendar_events",
        ],
    }
    _FALLBACK_CATEGORIES = ["general"]

    _CLASSIFY_RULES = [
        ("web", ["search", "find online", "google it", "look up", "browse", "what is", "who is", "internet"]),
        ("obsidian", ["note", "obsidian", "vault", "日记", "笔记"]),
        ("email", ["email", "mail", "inbox", "收件箱", "邮件"]),
        ("code", ["code", "script", "write a", "create a file", "implement", "编程", "写代码", "debug"]),
        ("file", ["list file", "read file", "file operation", "directory", "文件夹", "文件"]),
        ("macos", ["notification", "remind", "clipboard", "剪贴板", "提醒", "通知"]),
    ]

    def _compress_history(self):
        """将早期对话压缩为摘要，保留最近 KEEP_EXCHANGES 轮完整对话。"""
        user_indices = [i for i, m in enumerate(self.history) if m.get("role") == "user"]
        if len(user_indices) <= self.KEEP_EXCHANGES:
            return

        split_idx = user_indices[-self.KEEP_EXCHANGES]
        old_msgs = self.history[:split_idx]
        self.history = self.history[split_idx:]

        text_parts = []
        for m in old_msgs:
            role = m.get("role", "")
            content = m.get("content", "")
            if role in ("user", "assistant") and content:
                label = "用户" if role == "user" else "Bobo"
                text_parts.append(f"{label}: {content[:200]}")
        if not text_parts:
            return
        old_text = "\n".join(text_parts)

        self._compressing = True
        try:
            prompt = [{"role": "user", "content": (
                f"请用中文将以下对话压缩为 3-5 行的简洁摘要，保留关键信息和决定。"
                f"只输出摘要，不要额外说明。\n\n{old_text}"
            )}]
            response = self.llm_caller(prompt, use_tools=False)
            summary = ""
            if isinstance(response, dict) and "error" not in response:
                content = (response.get("choices", [{}])[0]
                           .get("message", {}).get("content", ""))
                if content:
                    summary = content.strip()
        except Exception:
            summary = ""
        finally:
            self._compressing = False

        if summary:
            self.history.insert(0, {
                "role": "system",
                "content": f"[对话历史摘要]:\n{summary}"
            })

    def _classify_query(self) -> Optional[str]:
        """根据当前用户输入判断查询类别，返回类别名称或 None（使用全部工具）。"""
        text = (self.current_user_input or "").lower()
        if not text:
            return None
        for category, keywords in self._CLASSIFY_RULES:
            for kw in keywords:
                if kw in text:
                    return category
        return None

    def _get_filtered_tools(self) -> Optional[list]:
        """根据查询类别返回过滤后的工具列表，返回 None 表示使用全部工具。"""
        from tools import TOOLS_SCHEMA
        category = self._classify_query()
        if category is None:
            return None

        allowed_names = set()
        for cat in [category] + self._FALLBACK_CATEGORIES:
            allowed_names.update(self.TOOL_CATEGORIES.get(cat, []))

        if not allowed_names:
            return None

        filtered = []
        for tool in TOOLS_SCHEMA:
            name = tool.get("function", {}).get("name", "")
            if name in allowed_names:
                filtered.append(tool)
        return filtered if filtered else None
