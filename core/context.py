"""上下文管理 — 历史压缩、查询分类、工具过滤、孤儿 tool_calls 清洗"""

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Optional

import tiktoken

logger = logging.getLogger(__name__)


# ── Token 估算（tiktoken cl100k_base，TICKET-024 彻底校准）─────────

_ENCODER = None


def _get_encoder():
    """惰性加载 tiktoken cl100k_base 编码器。"""
    global _ENCODER
    if _ENCODER is None:
        _ENCODER = tiktoken.get_encoding("cl100k_base")
    return _ENCODER


def _estimate_tokens(messages: list) -> int:
    """用 tiktoken cl100k_base 精确估算消息列表的 token 数。

    cl100k_base 是 GPT-4 / GPT-3.5-turbo 及大部分现代模型的编码，
    跨模型偏差典型 <5%，彻底替代 023 的启发式补丁。

    每条消息额外 +4 token 作为分隔符的保守开销（留安全边际）。
    注意：工具 schema、name 字段等完整编码，不做特殊处理。
    """
    enc = _get_encoder()
    total = 0
    for msg in messages:
        total += len(enc.encode(str(msg)))
    total += len(messages) * 4
    return total


# ── 消息条数兜底（票 TICKET-024：token 触发为主，条数降级为硬上限）─

def _get_msg_count_budget() -> int:
    """返回消息条数硬上限，从 BOBO_CONTEXT_BUDGET 环境变量读取，默认 200。

    TICKET-024 后此为兜底保护：正常压缩由 token 预算驱动（_get_context_budget），
    仅在 token 估算异常或极端场景时，条数触发作为最后的防溢出保险。
    """
    raw = os.environ.get("BOBO_CONTEXT_BUDGET", "200")
    try:
        return max(10, int(raw))
    except (ValueError, TypeError):
        return 200


# ── 上下文归档目录 ─────────────────────────────────────────────────

def _get_archive_dir(session_id: str = "") -> Path:
    """返回会话上下文归档目录。"""
    base = Path(os.environ.get("BOBO_DATA_DIR", str(Path.home() / ".bobo_v2")))
    archive_dir = base / "archives"
    archive_dir.mkdir(parents=True, exist_ok=True)
    return archive_dir


def _archive_compressed(session_id: str, old_msgs: list, summary: str,
                        pre_count: int, post_count: int, pre_tokens: int, post_tokens: int):
    """将被压缩的原文追加写入会话归档文件。

    归档文件路径: ~/.bobo_v2/archives/{session_id}.jsonl
    每行一条 JSON 记录，包含时间戳、原文消息列表、摘要文本、统计信息。
    此文件只追加不修改，保证可回溯审计。
    """
    try:
        archive_dir = _get_archive_dir(session_id)
        archive_path = archive_dir / f"{session_id}.jsonl"
        record = {
            "ts": time.time(),
            "type": "context.compressed",
            "session_id": session_id,
            "pre_msg_count": pre_count,
            "post_msg_count": post_count,
            "pre_tokens": pre_tokens,
            "post_tokens": post_tokens,
            "summary": summary,
            "archived_messages": [
                {k: v for k, v in m.items() if k in ("role", "content", "tool_calls", "tool_call_id", "name")}
                for m in old_msgs
            ],
        }
        with open(archive_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    except Exception:
        logger.warning("上下文归档失败（静默降级）", exc_info=True)


# ── 固定开销（工具 schema + system prompt + 记忆注入，实测约 20-25K）──
_FIXED_OVERHEAD_TOKENS = 25000


def _get_context_budget(_engine=None) -> int:
    """返回当前模型的上下文预算（token 数），TICKET-024 重构。

    预算 = (context_length - max_tokens 预留 - 固定开销) × BOBO_CONTEXT_BUDGET_RATIO

    固定开销 = 工具 schema + system prompt + 记忆注入（实测约 20-25K token）。
    max_tokens 扣除上限不超过 context_length 的 50%（防大 max_tokens 配小窗口时预算归零）。
    BOBO_CONTEXT_BUDGET_RATIO 默认 0.7，可通过环境变量覆盖。
    """
    import os
    from core.provider import get_context_length

    context_len = get_context_length()
    raw_max_tokens = int(os.environ.get("BOBO_MAX_TOKENS", "8192"))
    max_tokens = min(raw_max_tokens, int(context_len * 0.5))
    ratio = float(os.environ.get("BOBO_CONTEXT_BUDGET_RATIO", "0.7"))
    # TICKET-024：扣除固定开销（工具 schema + system prompt + 记忆注入）
    # 固定开销上限不超过 (context_len - max_tokens) 的 40%，防止小窗口模型预算归零
    effective_overhead = min(_FIXED_OVERHEAD_TOKENS,
                             int((context_len - max_tokens) * 0.4))
    available = context_len - max_tokens - effective_overhead
    return max(int(available * ratio), 1)  # 至少 1 token

def _build_local_fallback_summary(old_msgs: list) -> str:
    """生成本地机械摘要——当 LLM 摘要失败或无文本时做兜底（票 TICKET-023）。

    输出格式：
      [对话历史摘要 · 本地兜底]
      ## 用户发言（逐条，截断 200 字）
      ## 助手结论（最后一条非工具文本，截断 400 字）
      ## 工具动作（名称 + 结果前 50 字）

    宁可机械，不丢数据。
    """
    lines = ["[对话历史摘要 · 本地兜底]"]

    # 用户发言
    user_parts = []
    for m in old_msgs:
        if m.get("role") == "user":
            content = str(m.get("content", "") or "")[:200]
            if content.strip():
                user_parts.append(f"- {content}")
    if user_parts:
        lines.append("## 用户发言")
        lines.extend(user_parts[:20])
    else:
        lines.append("## 用户发言\n(无)")

    # 助手结论（最后一条非工具文本）
    asst_text = ""
    for m in reversed(old_msgs):
        if m.get("role") == "assistant":
            content = str(m.get("content", "") or "")
            if content.strip() and "[RESULT:" not in content[:30]:
                asst_text = content[:400]
                break
    lines.append(f"## 助手结论\n{asst_text if asst_text else '(无)'}")

    # 工具动作
    tool_parts = []
    for m in old_msgs:
        if m.get("role") == "tool":
            name = m.get("name", m.get("tool_call_id", "?"))
            content = str(m.get("content", "") or "")[:50].replace("\n", " ")
            if content.strip():
                tool_parts.append(f"- {name}: {content}")
    if tool_parts:
        lines.append("## 工具动作")
        lines.extend(tool_parts[:20])
    else:
        lines.append("## 工具动作\n(无)")

    return "\n".join(lines)


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
            "api_register", "api_call", "bobo_config", "bobo_schedule", "wiki_rebuild", "task_ledger",
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

    def _build_work_anchor(self) -> dict[str, str]:
        """构建工作锚点——跨压缩存活的机械提取状态快照。

        不从 LLM 摘要提取，从可靠来源直接取：
        - 当前任务：self.current_user_input（前 200 字符）
        - 已写文件：self.tracker._change_log 中提取路径，去重最多 10 条
        - 台账未完成项：self.task_ledger 中 status != "done" 的项（最多 5 条）

        每次压缩时重建，旧锚点被新锚点替换。
        任何来源读取失败 → 降级跳过对应段，绝不阻塞压缩。
        """
        lines = ["[工作锚点 · 压缩豁免 · 每轮更新]"]

        # ── 当前任务 ──
        task = (getattr(self, 'current_user_input', None) or '').strip()
        if task:
            lines.append(f"🎯 当前任务：{task[:200]}")

        # ── 已写文件 ──
        # 票 TICKET-025：从会话级只增集合取，防 change_log 塌缩丢失。
        # 集合只在 engine.py 工具调用时同步入。无文件→降级跳过。
        try:
            session_files = getattr(self, '_session_written_files', None)
            if session_files:
                file_list = sorted(session_files)[:10]
                lines.append(f"📁 本会话已写文件：{', '.join(file_list)}（共 {len(session_files)} 个）")
            elif hasattr(self, 'tracker') and hasattr(self.tracker, '_change_log'):
                # 仅读结构化 path 字段——log_change 始终写入此字段（TICKET-025 ③）
                written: set[str] = set()
                for entry in self.tracker._change_log:
                    p = entry.get('path', '')
                    if p and not p.startswith('['):
                        written.add(p)
                if written:
                    file_list = sorted(written)[:10]
                    lines.append(f"📁 本会话已写文件：{', '.join(file_list)}（共 {len(written)} 个）")
        except Exception:
            pass

        # ── 台账 ──
        try:
            ledger = getattr(self, 'task_ledger', None) or []
            pending = [e for e in ledger if e.get('status') != 'done']
            if pending:
                circles = ['①', '②', '③', '④', '⑤']
                items = []
                for i, e in enumerate(pending[:5]):
                    items.append(f"{circles[i] if i < 5 else ''}{e.get('title', '')[:40]}")
                lines.append(f"📋 台账未完成：{' '.join(items)}")
        except Exception:
            pass

        return {"role": "system", "content": "\n".join(lines)}

    # ── 三层压缩参数（TICKET-024）─────────────────────────────────────
    _LAYER_0_TOKEN_LIMIT = 15000   # 层0 逐字保留 token 上限
    _LAYER_1_SEGMENT_ROUNDS = 25   # 层1 每段约 25 轮
    _LAYER_1_MAX_SEGMENTS = 5      # 层1 超过 5 段 → 二次压缩合并下沉
    _LAYER_1_MAX_PER_SEGMENT = 300  # 每段摘要上限 token
    _LAYER_2_MAX_TOKENS = 200       # 层2 极简摘要上限 token

    def _compress_history(self, *, _event_bus=None):
        """Token 驱动三层压缩（票 TICKET-024 重构）。

        触发：history token > _get_context_budget()，或条数 > 200 硬上限兜底。
        分层：
          层0 逐字保留：最近 ~15K token 的消息（~15-20 条），完整原文
          层1 分段摘要：中段每 20-30 轮结构化摘要（分段由 LLM 智能划分）
          层2 极简摘要：最旧段合并为 Active Task + Key Decisions（一条消息）
        二次压缩：层1 段数 > 5 时自动合并下沉为层2
        记忆沉淀：同一次 LLM 调用产出摘要 + 知识条目 → knowledge_base.json
        """
        from core.event_bus import event_bus as _default_event_bus

        bus = _event_bus or _default_event_bus
        token_budget = _get_context_budget()
        msg_budget = _get_msg_count_budget()
        total_msg_count = len(self.history)
        total_tokens = _estimate_tokens(self.history)

        # ── 触发判断：token 优先，条数兜底 ──
        if total_tokens <= token_budget and total_msg_count <= msg_budget:
            return

        # ── 空转防护（TICKET-023 保留）：可压缩段 token < 15% → 跳过 ──
        layer_0_tokens = 0
        layer_0_msgs = []
        for m in reversed(self.history):
            mt = _estimate_tokens([m])
            if layer_0_tokens + mt > self._LAYER_0_TOKEN_LIMIT:
                break
            layer_0_msgs.insert(0, m)
            layer_0_tokens += mt
        split_idx = total_msg_count - len(layer_0_msgs)
        archivable_ratio = 1.0 - (len(layer_0_msgs) / max(total_msg_count, 1))
        if archivable_ratio < 0.15 and total_tokens <= token_budget * 1.2 and total_msg_count <= msg_budget:
            # 可归档太少且未严重超预算 → 不压
            session_id = getattr(self, 'sid', '')
            try:
                bus.write("context.compress_skipped", {
                    "session_id": session_id,
                    "reason": "archivable_too_small",
                    "ratio": round(archivable_ratio, 4),
                    "total_tokens": total_tokens,
                    "token_budget": token_budget,
                })
            except Exception:
                logger.warning("context.compress_skipped 事件写入失败（静默降级）", exc_info=True)
            # 票 COST-3：工作锚点不再 insert 进 history（任何位置都不许）——
            # 改为随 COST-2 尾部动态段由 injector 每轮请求组装时注入。
            # 压缩豁免语义保留：锚点内容（当前任务/已写文件/台账）全部来自
            # 会话级属性，不随压缩丢失；此处仅清理 history 中残留旧锚点
            # （兼容旧存盘/旧测试），并刷新 self._work_anchor 供尾部注入。
            _ANCHOR_PREFIX = "[工作锚点"
            self.history = [m for m in self.history
                            if not (m.get("role") == "system" and
                                    m.get("content", "").startswith(_ANCHOR_PREFIX))]
            self._work_anchor = self._build_work_anchor()
            return

        # ── 预统计 ──
        pre_msg_count = total_msg_count
        pre_tokens = total_tokens

        # ── 构建 + 刷新工作锚点（TICKET-020 → 票 COST-3 移位） ──
        # COST-3：锚点不再 insert 进 history（头部 insert 破坏前缀缓存），
        # 改为存 self._work_anchor，由 injector 每轮组装时注入尾部动态段
        # （最后一个 user 消息之前）。压缩豁免语义不变：锚点内容全部来自
        # 会话级属性，压缩不丢。history 中残留旧锚点照常清理（兼容旧数据）。
        _ANCHOR_PREFIX = "[工作锚点"
        self.history = [m for m in self.history
                        if not (m.get("role") == "system" and
                                m.get("content", "").startswith(_ANCHOR_PREFIX))]
        self._work_anchor = self._build_work_anchor()

        # ── 三层分割 ──
        # 层0：从尾部往前取，直到累计 token 超 _LAYER_0_TOKEN_LIMIT
        # TICKET-024：锚点消息不计入层0 token 累计
        layer_0 = []
        layer_0_tokens = 0
        tail_idx = len(self.history)
        for m in reversed(self.history):
            if m.get("role") == "system" and m.get("content", "").startswith(_ANCHOR_PREFIX):
                layer_0.insert(0, m)
                tail_idx -= 1
                continue
            mt = _estimate_tokens([m])
            if layer_0_tokens + mt > self._LAYER_0_TOKEN_LIMIT:
                break
            layer_0.insert(0, m)
            layer_0_tokens += mt
            tail_idx -= 1

        # 可用于压缩的全部旧消息（层1+层2 原料）
        compressible = self.history[:tail_idx]

        # ── 工具截断：只作用于层0，compressible 中的工具保持原样 ──
        # TICKET-024：截断从分层前移到分层后，确保 compressible 中工具内容完整交给摘要/兜底
        tool_msgs_in_layer0 = [(i, m) for i, m in enumerate(layer_0) if m.get("role") == "tool"]
        total_tool_l0 = sum(len(str(m.get("content", ""))) for _, m in tool_msgs_in_layer0)
        if tool_msgs_in_layer0 and total_tool_l0 > 30000:
            per_tool = max(500, 30000 // len(tool_msgs_in_layer0))
            for i, m in tool_msgs_in_layer0:
                tr = m.get("content", "")
                if len(str(tr)) > per_tool:
                    m["content"] = str(tr)[:per_tool] + f"\n...(截断，原{len(str(tr))}字符)"

        # ── 分离已有摘要（幂等） ──
        existing_l2 = [m for m in compressible
                       if m.get("role") == "system" and
                       m.get("content", "").startswith("[L2 极简摘要")]
        existing_l1 = [m for m in compressible
                       if m.get("role") == "system" and
                       m.get("content", "").startswith("[L1 段摘要")]
        existing_old_summary = [m for m in compressible
                                if m.get("role") == "system" and
                                m.get("content", "").startswith("[对话历史摘要]")
                                and m not in existing_l2 and m not in existing_l1]

        # 将旧的 [对话历史摘要] 归入层2（向下兼容旧格式）
        existing_l2.extend(existing_old_summary)

        # 纯对话（不含任何 system 摘要/锚点）
        pure_msgs = [m for m in compressible
                     if m not in existing_l2 and m not in existing_l1
                     and not (m.get("role") == "system" and
                               m.get("content", "").startswith("[对话历史摘要]"))
                     ]

        # ── 二次压缩：层1 段数 > 5 → 合并下沉为层2 ──
        if len(existing_l1) > self._LAYER_1_MAX_SEGMENTS:
            merged_text = "\n---\n".join(
                m.get("content", "") for m in existing_l1
            )
            if merged_text.strip():
                # 调用 LLM 合并
                merge_prompt_text = (
                    "将以下多段历史摘要合并为一条 200 token 以内的极简摘要，"
                    "只保留 Active Task / Completed / Key Decisions：\n\n"
                    + merged_text
                )
                merge_summary = self._call_summary_llm(merge_prompt_text)
                if merge_summary:
                    existing_l2.insert(0, {
                        "role": "system",
                        "content": f"[L2 极简摘要]\n{merge_summary}"
                    })
                # 丢弃旧层1
                existing_l1 = []

        # ── 如果没有纯对话需要压缩 → 直接组装 ──
        if not pure_msgs:
            self._assemble_compressed(existing_l2, existing_l1, layer_0)
            return

        # ── 分段：层2（最旧 30% 的纯对话）+ 层1（剩余中段） ──
        pure_msg_count = len(pure_msgs)
        l2_cutoff = max(1, pure_msg_count // 3)  # 前 1/3 → 层2
        l2_msgs = pure_msgs[:l2_cutoff]
        l1_msgs = pure_msgs[l2_cutoff:]

        # ── 构造 LLM 提示 ──
        prompt_parts = []
        prompt_parts.append("请总结以下对话历史（较早的对话，最近的对话已保留原文）。\n")

        # 层2 部分的文本
        if l2_msgs:
            prompt_parts.append("## 最早阶段（层2 · 极简摘要）\n")
            for m in l2_msgs:
                role = m.get("role", "")
                content = str(m.get("content", "") or "")
                if role in ("user", "assistant") and content.strip():
                    label = "用户" if role == "user" else "Bobo"
                    prompt_parts.append(f"{label}: {content[:300]}")
                elif role == "tool":
                    prompt_parts.append(f"[工具: {content[:100]}]")
            prompt_parts.append("")

        # 层1 部分的文本
        if l1_msgs:
            prompt_parts.append("## 中间阶段（层1 · 分段摘要，请自动划分时间段落）\n")
            for m in l1_msgs:
                role = m.get("role", "")
                content = str(m.get("content", "") or "")
                if role in ("user", "assistant") and content.strip():
                    label = "用户" if role == "user" else "Bobo"
                    prompt_parts.append(f"{label}: {content[:300]}")
                elif role == "tool":
                    prompt_parts.append(f"[工具: {content[:100]}]")

        # 输出格式指令
        prompt_parts.append("""
## 输出格式（严格遵守）

### L2_ULTRA_BRIEF
[一段话：当前活跃任务、已完成事项、关键决策。200 token 以内。]

### L1_SEGMENT_1
[第一个段落的摘要，150-300 token]

### L1_SEGMENT_2
[第二个段落的摘要，150-300 token]
...（根据对话内容自动划分 1-5 个段落）

### MEMORY
- KEY_DECISION: 内容
- USER_PREF: 内容
- FACT: 内容
...（可选，无关键信息则省略此段）
""")

        full_prompt = "\n".join(prompt_parts)

        # ── 调用 LLM（一次产出：摘要 + 记忆沉淀） ──
        response_text = self._call_summary_llm(full_prompt)

        # ── 解析 LLM 输出 ──
        summary_source = "llm"
        l2_text, l1_segments, memory_entries = self._parse_compression_output(response_text)

        if not response_text or (not l2_text and not l1_segments):
            # 降级：本地机械兜底
            local_summary = _build_local_fallback_summary(pure_msgs)
            existing_l2.insert(0, {
                "role": "system",
                "content": f"[L2 极简摘要]\n{local_summary}"
            })
            summary_source = "local_fallback"
        else:
            if l2_text:
                existing_l2.insert(0, {
                    "role": "system",
                    "content": f"[L2 极简摘要]\n{l2_text}"
                })
            for seg in reversed(l1_segments):
                existing_l1.insert(0, {
                    "role": "system",
                    "content": f"[L1 段摘要]\n{seg}"
                })

        # ── 记忆沉淀（TICKET-024 D） ──
        if memory_entries:
            self._precipitate_memory(memory_entries)

        # ── 组装最终 history ──
        self._assemble_compressed(existing_l2, existing_l1, layer_0)

        # ── 后统计 ──
        post_msg_count = len(self.history)
        post_tokens = _estimate_tokens(self.history)
        layer_stats = {
            "l0_msg_count": len(layer_0),
            "l0_tokens": layer_0_tokens,
            "l1_summary_count": len(existing_l1),
            "l2_summary_count": len(existing_l2),
        }

        # ── 归档 + 事件 ──
        session_id = getattr(self, 'sid', '')
        _archive_compressed(
            session_id=session_id,
            old_msgs=compressible,
            summary=(l2_text or "") + (" | L1:" + str(len(l1_segments)) if l1_segments else ""),
            pre_count=pre_msg_count,
            post_count=post_msg_count,
            pre_tokens=pre_tokens,
            post_tokens=post_tokens,
        )
        try:
            bus.write("context.compressed", {
                "session_id": session_id,
                "pre_msg_count": pre_msg_count,
                "post_msg_count": post_msg_count,
                "pre_tokens": pre_tokens,
                "post_tokens": post_tokens,
                "summary_source": summary_source,
                "layer_stats": layer_stats,
                "archived_count": len(compressible),
            })
        except Exception:
            logger.warning("context.compressed 事件写入失败（静默降级）", exc_info=True)

    def _call_summary_llm(self, prompt_text: str) -> str:
        """调用 LLM 做摘要——轻量封装，失败返回空字符串。"""
        self._compressing = True
        try:
            prompt = [{"role": "user", "content": prompt_text}]
            response = self.llm_caller(prompt, use_tools=False)
            if isinstance(response, dict) and "error" not in response:
                content = (response.get("choices", [{}])[0]
                           .get("message", {}).get("content", ""))
                return content.strip() if content else ""
            return ""
        except Exception:
            logger.warning("LLM 摘要调用失败（静默降级）", exc_info=True)
            return ""
        finally:
            self._compressing = False

    def _parse_compression_output(self, text: str) -> tuple:
        """解析 LLM 压缩输出，返回 (l2_text, l1_segments_list, memory_entries_list)。"""
        if not text:
            return "", [], []

        l2_text = ""
        l1_segments = []
        memory_entries = []
        current_section = None
        current_content = []

        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("### L2_ULTRA_BRIEF") or stripped.startswith("## L2_ULTRA_BRIEF"):
                if current_section == "l1" and current_content:
                    l1_segments.append("\n".join(current_content).strip())
                    current_content = []
                if current_section == "l2" and current_content:
                    l2_text = "\n".join(current_content).strip()
                    current_content = []
                current_section = "l2"
            elif stripped.startswith("### L1_SEGMENT") or stripped.startswith("## L1_SEGMENT"):
                if current_section == "l1" and current_content:
                    l1_segments.append("\n".join(current_content).strip())
                    current_content = []
                if current_section == "l2" and current_content:
                    l2_text = "\n".join(current_content).strip()
                    current_content = []
                current_section = "l1"
            elif stripped.startswith("### MEMORY") or stripped.startswith("## MEMORY"):
                if current_section == "l1" and current_content:
                    l1_segments.append("\n".join(current_content).strip())
                    current_content = []
                if current_section == "l2" and current_content:
                    l2_text = "\n".join(current_content).strip()
                    current_content = []
                current_section = "memory"
            elif current_section and stripped:
                current_content.append(line)

        # 处理最后一段
        if current_section == "l2" and current_content:
            l2_text = "\n".join(current_content).strip()
        elif current_section == "l1" and current_content:
            l1_segments.append("\n".join(current_content).strip())
        elif current_section == "memory" and current_content:
            for entry in current_content:
                entry = entry.strip().lstrip("- ")
                if entry:
                    memory_entries.append(entry)

        return l2_text, l1_segments, memory_entries

    def _precipitate_memory(self, entries: list):
        """将 LLM 产出的知识条目写入 knowledge_base.json（信号分 100）。

        条目格式：KEY_DECISION: xxx / USER_PREF: xxx / FACT: xxx
        失败静默降级，不阻塞压缩。
        """
        try:
            from tools.v5_memory import add_entry
            for entry in entries:
                # 解析 TYPE: content 格式
                if ":" in entry:
                    parts = entry.split(":", 1)
                    etype = parts[0].strip().upper()
                    content = parts[1].strip()
                else:
                    etype = "FACT"
                    content = entry.strip()
                if content:
                    add_entry(
                        text=content,
                        entry_type=etype,
                        tags=["compression"],
                        folder="compressed",
                    )
        except Exception:
            logger.warning("记忆沉淀失败（静默降级）", exc_info=True)

    def _assemble_compressed(self, l2_summaries: list, l1_summaries: list,
                              layer_0: list):
        """组装压缩后的 history：[L2摘要] + [L1段摘要] + [锚点] + [层0逐字]。

        TICKET-024：层0 内不得含锚点消息，否则会重复插入。
        """
        _ANCHOR_PREFIX = "[工作锚点"

        # ── 断言/清理：层0 内不得含锚点 ──
        anchors_in_l0 = [m for m in layer_0
                         if m.get("role") == "system" and
                         m.get("content", "").startswith(_ANCHOR_PREFIX)]
        if anchors_in_l0:
            logger.warning(
                f"_assemble_compressed: 层0 内发现 {len(anchors_in_l0)} 个锚点消息，已自动剔除。"
                f" 累计层0 token 时不应计入锚点，请检查调用方。"
            )
            layer_0 = [m for m in layer_0 if m not in anchors_in_l0]

        # 票 COST-3：锚点不再 append 进 history（原 TICKET-020 放摘要后/层0前，
        # 位于头部导致其后 tokens 缓存作废——长会话杀手）。压缩豁免语义由
        # self._work_anchor 属性承载：压缩主路径/跳过路径已在上游刷新属性，
        # 此处仅兜底确保属性非空，绝不触碰 history。
        if not getattr(self, "_work_anchor", None):
            self._work_anchor = self._build_work_anchor()
        # 组装
        new_history = []
        new_history.extend(l2_summaries)
        new_history.extend(l1_summaries)
        new_history.extend(layer_0)
        self.history = new_history

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

    # 元工具：永远不可被分类裁剪（票 TICKET-E2b）
    _META_TOOLS: set[str] = {"describe_tool", "load_result", "read_local_file"}

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

        # 票 TICKET-E2b：describe_tool 取件注册的额外工具，永远并入允许集
        allowed_names.update(getattr(self, "_extra_tools", set()) or set())
        # 票 TICKET-E2b：元工具不可被分类裁剪
        allowed_names.update(self._META_TOOLS)

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
