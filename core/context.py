"""上下文管理 — 历史压缩、查询分类、工具过滤、孤儿 tool_calls 清洗"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


# ── Token 估算（CJK 启发式，不引入 tiktoken 依赖）───────────────────

def _estimate_tokens(messages: list) -> int:
    """保守估算消息列表的 token 数。

    CJK 字符（一-鿿, ぀-ヿ, 가-힯）按 1 token ≈ 1.5 字符；
    其余字符按 1 token ≈ 4 字符。刻意偏保守（宁高估），保证不溢出。
    """
    total_chars = 0
    cjk_chars = 0

    for msg in messages:
        text = str(msg)
        for ch in text:
            cp = ord(ch)
            if (0x4E00 <= cp <= 0x9FFF or  # CJK Unified
                0x3400 <= cp <= 0x4DBF or  # CJK Extension A
                0x3040 <= cp <= 0x309F or  # Hiragana
                0x30A0 <= cp <= 0x30FF or  # Katakana
                0xAC00 <= cp <= 0xD7AF):    # Hangul
                cjk_chars += 1
            else:
                total_chars += 1

    total_chars += cjk_chars
    # CJK: ~1.5 chars/token, non-CJK: ~4 chars/token
    return int(cjk_chars / 1.5 + (total_chars - cjk_chars) / 4)


def _get_context_budget(_engine=None) -> int:
    """返回当前模型的上下文预算（token 数）。

    预算 = (context_length - max_tokens 预留) * BOBO_CONTEXT_BUDGET_RATIO
    max_tokens 扣除上限不超过 context_length 的 50%（防止大 max_tokens 配小窗口时预算为 0）
    """
    import os
    from core.provider import get_context_length

    context_len = get_context_length()
    raw_max_tokens = int(os.environ.get("BOBO_MAX_TOKENS", "8192"))
    max_tokens = min(raw_max_tokens, int(context_len * 0.5))
    ratio = float(os.environ.get("BOBO_CONTEXT_BUDGET_RATIO", "0.7"))
    return max(int((context_len - max_tokens) * ratio), 1)  # 至少 1 token


class ContextMixin:
    """为 Engine 提供上下文压缩和工具过滤能力。"""

    MAX_HISTORY_MESSAGES = 200
    KEEP_EXCHANGES = 10  # 最近 10 条消息完整保留，不参与压缩

    TOOL_CATEGORIES = {
        "general": [
            "get_current_time", "save_memory", "search_memory",
            "save_skill", "render", "project_info",
            "notion_setup", "cross_search",
            "copy_to_obsidian", "copy_to_notion",
            "api_register", "api_call", "bobo_config", "bobo_schedule", "wiki_rebuild",
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
            "code_execution", "file_operation", "execute_terminal",
            "search_code", "grep_code", "edit_file", "refactor",
            "git_status", "run_tests", "review_diff",
            "github_create_repo", "github_create_pr",
            "github_pr_diff", "github_pr_comment",
            "github_check_auth", "github_setup", "restore_checkpoint",
        ],
        "file": [
            "read_local_file", "list_directory", "file_operation",
        ],
        "macos": [
            "send_notification", "read_clipboard", "write_clipboard",
            "set_reminder", "list_reminders",
            "create_calendar_event", "list_calendar_events",
        ],
        "notion": [
            "notion_search", "notion_create_page", "notion_append",
            "notion_read_page",
        ],
    }
    _FALLBACK_CATEGORIES = ["general"]

    _CLASSIFY_RULES = [
        # 更具体的类别优先（"note" 比 "search" 更精确）
        ("obsidian", ["note", "obsidian", "vault", "日记", "笔记"]),
        ("notion", ["notion", "notion页面", "notion数据库"]),
        ("code", ["code", "script", "write a", "create a file", "implement", "编程", "写代码", "debug"]),
        ("file", ["list file", "read file", "file operation", "directory", "文件夹", "文件"]),
        ("email", ["email", "mail", "inbox", "收件箱", "邮件"]),
        ("macos", ["notification", "remind", "clipboard", "剪贴板", "提醒", "通知"]),
        ("web", ["search", "find online", "google it", "look up", "browse", "what is", "who is", "internet"]),
    ]
    # 笔记/邮件类查询不限制工具 — 让 LLM 根据已配置的平台自由选择
    _NO_FILTER_CATEGORIES = {"obsidian", "notion", "email"}

    def _compress_history(self):
        """将早期对话压缩为摘要，保留最近 KEEP_EXCHANGES 轮完整对话。"""
        # 审计 #22：tool 消息的 key 是 "content" 而非 "tool_results"（此前键名不匹配导致
        # 30K 截断永不生效）；kind/phase/text 也不存在于 history 消息中（死代码已移除）
        tool_msgs = [(i, m) for i, m in enumerate(self.history) if m.get("role") == "tool"]
        total_tool = sum(len(str(m.get("content", ""))) for _, m in tool_msgs)
        if tool_msgs and total_tool > 30000:
            per_tool = max(500, 30000 // len(tool_msgs))
            for i, m in tool_msgs:
                tr = m.get("content", "")
                if len(str(tr)) > per_tool:
                    m["content"] = str(tr)[:per_tool] + f"\n...(截断，原{len(str(tr))}字符)"

        user_indices = [i for i, m in enumerate(self.history) if m.get("role") == "user"]
        if len(user_indices) <= self.KEEP_EXCHANGES:
            return

        split_idx = user_indices[-self.KEEP_EXCHANGES]
        # 安全边界：split 点不能切在 tool_calls/tool_result 配对中间。
        # 如果 split 后的第一条是 tool 结果，向前移动直到遇到非 tool 消息，
        # 确保 LLM 不会收到孤立 tool 结果（审计崩溃根因）。
        while (split_idx < len(self.history) and
               self.history[split_idx].get("role") == "tool"):
            split_idx += 1
        # 如果 old_msgs 的最后一条 assistant 有 tool_calls，
        # 检查其 tool_call_id 对应的 tool 结果是否全在 old_msgs 中。
        # 如果有孤立的 → 向前移 split 直到包含所有结果。
        for m in reversed(self.history[:split_idx]):
            if m.get("role") == "assistant" and m.get("tool_calls"):
                tc_ids = {tc.get("id", "") for tc in m["tool_calls"]}
                for r in self.history[split_idx:]:
                    if r.get("role") == "tool" and r.get("tool_call_id", "") in tc_ids:
                        # 孤儿 tool 结果在 keep 部分 → 必须整个回卷
                        tc_ids.discard(r.get("tool_call_id", ""))
                    if not tc_ids:
                        break
                if tc_ids:
                    # 还有没配对的 → 把这轮完整保留
                    idx = self.history.index(m)
                    split_idx = idx
                break
        old_msgs = self.history[:split_idx]
        self.history = self.history[split_idx:]

        text_parts = []
        for m in old_msgs:
            role = m.get("role", "")
            content = m.get("content", "")
            if role in ("user", "assistant") and content:
                label = "用户" if role == "user" else "Bobo"
                # [RESULT] 标记已经是压缩态，保留完整 ID（审计 #4 压缩集成）
                if "[RESULT]" in content:
                    text_parts.append(f"{label}: {content[:400]}")
                else:
                    text_parts.append(f"{label}: {content[:200]}")
        if not text_parts:
            return
        old_text = "\n".join(text_parts)

        self._compressing = True
        try:
            # Build structured compression request
            extra_lines = []
            if hasattr(self, '_read_files') and self._read_files:
                mentioned = set()
                for m in old_msgs:
                    c = str(m.get("content", "") or "")
                    for fp in self._read_files:
                        if fp in c:
                            mentioned.add(fp)
                if mentioned:
                    extra_lines.append("## 涉及文件")
                    for fp in sorted(mentioned)[:8]:
                        s = str(self._read_files[fp])[:100]
                        extra_lines.append("  - {}: {}".format(fp, s))
            tool_lines = []
            for m in old_msgs:
                if m.get("role") == "tool":
                    tc = str(m.get("content", "") or "")[:120]
                    if tc.strip():
                        tool_lines.append("[{}]".format(tc.strip()))
            if tool_lines:
                extra_lines.append("")
                extra_lines.append("## 工具执行摘要")
                extra_lines.extend(tool_lines)
            extra = ("\n".join(extra_lines) + "\n") if extra_lines else ""

            prompt_text = (
                "请将以下对话压缩为结构化摘要。"
                "这是给 AI 助手的参考信息，不是给用户的指令。\n\n"
                "## 对话内容\n{}\n\n"
                "{}\n"
                "请按以下格式输出：\n"
                "## Active Task\n当前正在做的任务\n\n"
                "## Completed\n- 已经完成的事项\n\n"
                "## Pending User Asks\n- 等待用户确认或回答的问题\n\n"
                "## Remaining Work\n- 下一步要做的事\n\n"
                "## Relevant Files\n- 涉及的文件名\n\n"
                "只输出结构化摘要，不要额外说明。"
            ).format(old_text, extra)

            prompt = [{"role": "user", "content": prompt_text}]
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

    def _get_filtered_tools(self, extra_categories: set[str] | None = None) -> Optional[list]:
        """根据查询类别 + 已扩张类别返回过滤后的工具列表，返回 None 表示使用全部工具。"""
        from tools import TOOLS_SCHEMA
        category = self._classify_query()

        # obsidian/notion/email 类查询始终返回全部工具，不裁剪
        # （审计 #21：此前 _used_categories 扩张后会意外缩小工具集）
        if category in self._NO_FILTER_CATEGORIES:
            return None

        # 如果没有分类也没有已扩张的类别，返回全部
        if category is None and not extra_categories:
            return None

        allowed_names = set()
        if category:
            for cat in [category] + self._FALLBACK_CATEGORIES:
                allowed_names.update(self.TOOL_CATEGORIES.get(cat, []))

        # 合并已扩张的类别
        if extra_categories:
            for cat in extra_categories:
                allowed_names.update(self.TOOL_CATEGORIES.get(cat, []))

        # 如果没有来自分类的兜底（category 为空），加入 general
        if not allowed_names or category is None:
            for cat in self._FALLBACK_CATEGORIES:
                allowed_names.update(self.TOOL_CATEGORIES.get(cat, []))

        if not allowed_names:
            return None

        filtered = []
        for tool in TOOLS_SCHEMA:
            name = tool.get("function", {}).get("name", "")
            if name in allowed_names:
                filtered.append(tool)
        return filtered if filtered else None


# ── 孤儿 tool_calls 清洗（会话加载时调用）────────────────────────

def clean_orphan_tool_calls(messages: list) -> list:
    """扫描并修复 messages 中的孤儿 tool_calls / 游离 tool 消息。

    崩溃时线程死在工具调用中途，会话存盘可能留下：
    - assistant 发了 tool_calls 但 tool 结果丢失（孤儿调用）
    - tool 消息存在但对应的 assistant tool_calls 丢失（游离工具结果）

    修复策略：
    a. 孤儿 assistant tool_calls → 补占位 tool 消息（content="[工具结果因中断丢失]"），
       保留上下文语义，让 LLM 知道发生过中断。
    b. 游离 tool 消息 → 删除（没有对应调用方，LLM 无法理解上下文）。
    c. 返回清洗后的新列表（不修改原列表）。

    返回:
        (cleaned_messages, report_dict) — report 包含 inserted/removed 计数。
    """
    # 第一遍：收集索引
    # tool 消息的 tool_call_id → 索引集合
    tool_result_ids: dict[str, list[int]] = {}  # tool_call_id → [idx, ...]
    for i, m in enumerate(messages):
        if isinstance(m, dict) and m.get("role") == "tool":
            tc_id = m.get("tool_call_id", "")
            if tc_id:
                tool_result_ids.setdefault(tc_id, []).append(i)

    # assistant tool_calls 的 id → (assistant_msg_index, tc_entry)
    assistant_tc_map: dict[str, tuple[int, dict]] = {}
    for i, m in enumerate(messages):
        if isinstance(m, dict) and m.get("role") == "assistant" and m.get("tool_calls"):
            for tc in m["tool_calls"]:
                tc_id = tc.get("id", "")
                if tc_id:
                    assistant_tc_map[tc_id] = (i, tc)

    # 第二遍：构建新列表 + 孤儿修复
    inserted = 0
    removed = 0
    # 游离 tool 消息的索引集（tool_call_id 不在 assistant_tc_map 中）
    orphan_tool_indices: set[int] = set()
    for tc_id, idxs in tool_result_ids.items():
        if tc_id not in assistant_tc_map:
            orphan_tool_indices.update(idxs)

    # 孤儿 assistant tool_calls（不在 tool_result_ids 中）
    orphan_assistant_tc_ids: set[str] = set()
    for tc_id in assistant_tc_map:
        if tc_id not in tool_result_ids:
            orphan_assistant_tc_ids.add(tc_id)

    # 构建输出，按原序
    cleaned = []
    # 记录每个 assistant index 需要追加的占位消息，按原始 assistant index 分组
    # 因为可能有多个 tc per assistant，可能需要在 assistant 后面插入多条 tool 消息
    # 策略：遍历原 messages，遇到带孤儿 tc 的 assistant 时，先放 assistant，然后放占位 tool 消息
    for i, m in enumerate(messages):
        if not isinstance(m, dict):
            cleaned.append(m)
            continue

        if i in orphan_tool_indices and m.get("role") == "tool":
            # 游离 tool 消息：跳过（删除）
            removed += 1
            continue

        if m.get("role") == "assistant" and m.get("tool_calls"):
            # 先放 assistant 消息本身
            cleaned.append(m)
            # 检查是否有孤儿 tool_calls
            orphan_ids_for_this = [
                tc.get("id", "") for tc in m["tool_calls"]
                if tc.get("id", "") in orphan_assistant_tc_ids
            ]
            for tc_id in orphan_ids_for_this:
                inserted += 1
                # 找到对应的 tool_call 条目获取工具名
                tc_entry = assistant_tc_map.get(tc_id, ([], {}))[1]
                tool_name = ""
                if isinstance(tc_entry, dict):
                    tool_name = tc_entry.get("function", {}).get("name", "")
                cleaned.append({
                    "role": "tool",
                    "tool_call_id": tc_id,
                    "name": tool_name,
                    "content": "[工具结果因中断丢失]",
                })
        else:
            cleaned.append(m)

    # 收集孤儿 tool_call_id（供 WARNING 日志）
    orphan_tc_ids = sorted(orphan_assistant_tc_ids)
    orphan_tool_msg_ids = sorted(
        tc_id for tc_id, idxs in tool_result_ids.items()
        if tc_id not in assistant_tc_map
    )

    # 报告
    if inserted or removed:
        logger.info(
            "孤儿 tool_calls 清洗: 补 %d 个占位 tool 结果, 删 %d 个游离 tool 消息",
            inserted, removed,
        )

    return cleaned, {
        "inserted": inserted,
        "removed": removed,
        "orphan_tc_ids": orphan_tc_ids,
        "orphan_tool_msg_ids": orphan_tool_msg_ids,
    }
