"""injector.py — Prompt 注入管道：将 engine 状态组装成完整的 messages 列表。

从 engine.py 的 _call_llm 方法提取。纯注入逻辑，不含 API 调用。
注入顺序必须与原 _call_llm 完全一致。
"""

import json
import os as _os
import logging

logger = logging.getLogger(__name__)

# 票 LN-4：活体知识库（library/<domain>/<topic>.md），与 tools/living_notes.py 同源
_LIBRARY_DIR = _os.path.join(
    _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "library")


def _read_note_frontmatter(path) -> dict:
    """轻量解析笔记 frontmatter（topic/domain/version/last_touched/source_sessions）。

    失败返回空 dict，保守不炸（扫描失败静默降级）。
    """
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except Exception:
        return {}
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    fm = {}
    for line in text[3:end].splitlines():
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        if not key or not val:
            continue
        if key == "source_sessions":
            val = val.strip("[]")
            fm[key] = [s.strip().strip("'\"") for s in val.split(",") if s.strip()]
        else:
            fm[key] = val
    return fm


class PromptInjector:
    """从 engine 状态构建完整的 messages 列表（system prompt + 所有注入 + history）。

    注入顺序：
    1. pending diff（代码审查）
    2. 推荐技能
    3. 自定义 API
    4. 用户资料 + 记忆
    5. AGENTS.md（项目规则）
    6. 改动日志（tracker.recent_changes）
    7. 已读文件（tracker.recent_reads）
    8. 主动连接（proactive.inject_context）
    9. 技能标准（skill_loader.load_standards）
    """

    def __init__(self, engine_ref):
        """初始化注入器。

        Args:
            engine_ref: Engine 实例引用，只读访问其状态。
        """
        self._engine = engine_ref

    def build_messages(
        self,
        system_prompt: str,
        user_input: str,
        tools_schema: list,
        extra_categories: set,
        session_id: str = "",
    ) -> list:
        """构建完整的 messages 列表。

        Returns:
            messages 列表，可直接传给 LLM caller。
        """
        engine = self._engine

        messages = [{"role": "system", "content": system_prompt}] + engine.history

        # ── 票 LN-4：上下文预算统计（各段组装时填充，return 前写 prompt.budget 事件）──
        budget_stats = {
            "identity": len(system_prompt),
            "memory": {"chars": 0, "entries": 0, "total_entries": 0, "evicted": 0},
            "skills": {"chars": 0, "truncated": False},
            "note_pointers": {"chars": 0, "count": 0, "topics": []},
        }

        # ── 1. pending diff ──
        if engine._pending_diff:
            diff_preview = engine._pending_diff[:4000]
            messages.insert(1, {
                "role": "system",
                "content": (
                    f"[代码变更 — 请审查以下 diff 是否有 bug、安全风险或性能问题:]\n"
                    f"{diff_preview}\n\n"
                    f"审查要点:\n"
                    f"1. 逻辑错误（拼写错误、条件反转、off-by-one）\n"
                    f"2. 安全风险（注入、硬编码密钥、权限问题）\n"
                    f"3. 性能问题（不必要的循环、重复计算、N+1 查询）\n"
                    f"4. 代码风格（与项目其他部分不一致的命名/格式）\n\n"
                    f"发现问题后如实报告，使用 review_diff 工具可查看完整 diff。"
                )
            })
            engine._pending_diff = ""

        # ── 2. 推荐技能 ──
        try:
            from core.skill_manager import get_skill_manager
            _skill_mgr = get_skill_manager()
            skill_refs = _skill_mgr.get_skill_tools()
            if skill_refs:
                user_text = (engine.current_user_input or "").lower()
                matched = []
                others = []
                for s in skill_refs:
                    name = s["function"]["name"].replace("run_skill:", "")
                    desc = s["function"]["description"]
                    triggers = s.get("triggers", [])
                    if triggers and any(t.lower() in user_text for t in triggers):
                        matched.append(f"  ▶ {name}: {desc}")
                        # 注入匹配 skill 的完整步骤 → LLM 直接可见，不需调工具
                        try:
                            skill_data = _skill_mgr.get_skill(name)
                            if skill_data and skill_data.get("steps"):
                                step_lines = []
                                for st in skill_data["steps"]:
                                    sn = st.get("name", "")
                                    sa = st.get("action", "")
                                    si = st.get("step", "")
                                    if sn or sa:
                                        step_lines.append(f"    {si}. {sn}: {sa[:200]}")
                                if step_lines:
                                    matched.append("\n".join(step_lines))
                        except Exception as e:
                            logger.debug("注入技能步骤失败 (%s): %s", name, e)
                    else:
                        others.append(f"  {name}: {desc[:100]}")
                lines = []
                if matched:
                    lines.append("[推荐技能 — 当前场景可用]:")
                    lines.extend(matched)
                    if others:
                        lines.append("")
                        lines.append("[其他技能]:")
                        lines.extend(others)
                else:
                    lines.append("[可参考的技能工作流]:")
                    lines.extend(others)
                # 票 LN-4：skill 段天花板 1500（保底 800 由独立段落保证，
                # 超额优先裁剪低相关度 others，从后往前丢行）
                content = "\n".join(lines)
                truncated = False
                if len(content) > 1500:
                    while len(content) > 1500 and len(lines) > 1:
                        lines.pop()
                        content = "\n".join(lines)
                    if len(content) > 1500:
                        content = content[:1500]
                    truncated = True
                budget_stats["skills"] = {
                    "chars": len(content), "truncated": truncated}
                messages.insert(1, {
                    "role": "system",
                    "content": content
                })
        except Exception as e:
            logger.debug("注入技能工作流失败: %s", e)

        # ── 3. 自定义 API ──
        apis_dir = _os.path.expanduser("~/.bobo/apis")
        if _os.path.isdir(apis_dir):
            apis = []
            for fname in sorted(_os.listdir(apis_dir)):
                if fname.endswith(".json"):
                    try:
                        with open(_os.path.join(apis_dir, fname)) as f:
                            cfg = json.load(f)
                        eps = [ep.get("name", "?") for ep in cfg.get("endpoints", [])]
                        apis.append(f"{cfg.get('name', fname)} ({', '.join(eps)})")
                    except Exception as e:
                        logger.debug("解析自定义 API 配置失败 (%s): %s", fname, e)
            if apis:
                messages.insert(1, {
                    "role": "system",
                    "content": "[已注册的自定义 API]:\n" + "\n".join(apis)
                })

        # ── 4. 用户资料 + 记忆 ──
        try:
            from tools.v5_memory import format_user_profile, format_memory_by_signal
            user_profile = format_user_profile()
            if user_profile:
                messages.insert(1, {
                    "role": "system",
                    "content": user_profile
                })
            # 注入记忆（票 LN-4：分段保底，按信号降序、天花板 2500、低信号淘汰）
            if not engine._compressing:
                mem_text, mem_stats = format_memory_by_signal(
                    max_chars=2500, min_chars=1000)
                if mem_text:
                    messages.insert(1, {
                        "role": "system",
                        "content": mem_text
                    })
                    budget_stats["memory"] = {
                        "chars": len(mem_text),
                        "entries": mem_stats.get("entries", 0),
                        "total_entries": mem_stats.get("total_entries", 0),
                        "evicted": mem_stats.get("evicted", 0),
                    }
        except Exception as e:
            logger.debug("注入用户资料/记忆失败: %s", e)

        # ── 4.5 关联笔记指针（票 LN-4：轻指针 + 按需翻阅，不整篇注入）──
        try:
            pointer_text, pointer_stats = self._build_note_pointers(
                session_id, user_input)
            if pointer_text:
                messages.insert(1, {
                    "role": "system",
                    "content": pointer_text
                })
                budget_stats["note_pointers"] = pointer_stats
        except Exception as e:
            logger.debug("注入笔记指针失败: %s", e)

        # ── 5. AGENTS.md ──
        try:
            vault = _os.environ.get("OBSIDIAN_VAULT", "")
            if vault:
                agents_path = _os.path.join(vault, "AGENTS.md")
                if _os.path.isfile(agents_path):
                    with open(agents_path, encoding="utf-8") as _f:
                        agents_content = _f.read(4000)
                    if agents_content.strip():
                        messages.insert(1, {
                            "role": "system",
                            "content": f"[项目规则 (AGENTS.md)]:\n{agents_content}"
                        })
        except Exception as e:
            logger.debug("注入 AGENTS.md 失败: %s", e)

        # ── 6. 改动日志 ──
        if engine.tracker._change_log:
            items = engine.tracker._change_log[-5:]
            lines = ["[本会话的改动记录]:", ""]
            for it in items:
                lines.append(f"  {it['desc']}")
            if len(engine.tracker._change_log) > 5:
                lines.append(f"  ...（共 {len(engine.tracker._change_log)} 次改动）")
            messages.insert(1, {"role": "system", "content": "\n".join(lines)})

        # ── 7. 已读文件 ──
        if engine.tracker._read_files:
            items = list(engine.tracker._read_files.items())[-3:]
            lines = ["[最近读过的文件]:", ""]
            for fpath, preview in items:
                short = preview[:120].replace('\n', ' ').strip()
                lines.append(f"  {fpath}: {short}...")
            messages.insert(1, {"role": "system", "content": "\n".join(lines)})

        # ── 8. 主动连接 ──
        messages = engine.proactive.inject_context(messages)

        # ── 9. 技能标准 ──
        skill_stds = engine.skill_loader.load_standards()
        if skill_stds:
            combined = "\n\n---\n\n".join(skill_stds)
            messages.append({
                "role": "system",
                "content": (
                    "## 项目标准 — 以下规则优先级高于一切，违反即不合格\n\n"
                    + combined
                ),
            })
        else:
            # 没有命中任何标准时，仍然告知可用标准列表（让 Bobo 知道自己的技能）
            available = engine.skill_loader.list_available()
            if available:
                messages.append({
                    "role": "system",
                    "content": (
                        "## 可用的项目标准（当前未命中，以下仅供参考）\n\n"
                        + available
                    ),
                })

        # ── 10. 上下文预算监控（票 LN-4）：组装完成写 1 条 prompt.budget 事件 ──
        try:
            from core.event_bus import event_bus
            event_bus.write("prompt.budget", {
                "sid": session_id,
                "total_chars": sum(len(m.get("content", "")) for m in messages),
                "sections": budget_stats,
            })
        except Exception:
            pass

        return messages

    def _build_note_pointers(self, session_id: str, user_input: str) -> tuple[str, dict]:
        """票 LN-4：关联笔记指针段（轻指针 + 按需翻阅，不整篇注入）。

        关联判定两条路径（多对多：一篇笔记 ←→ 多个会话，source_sessions 维系）：
          1. 当前 session id 命中笔记 frontmatter source_sessions → 必带
          2. 当前用户消息命中主题词（主题名 ∈ 用户消息 或 用户消息 ∈ 主题名）→ 临时带
        去重取前 3 条；段预算 300 字符（超了从末尾逐条丢弃）。
        library 不存在 / 无关联 → 整体省略（返回空串，零动作）。
        扫描失败静默降级（WARNING + notes.error），绝不阻塞注入。

        返回 (text, stats)：stats = {"chars", "count", "topics"}。
        """
        try:
            library = _LIBRARY_DIR
            if not _os.path.isdir(library):
                return "", {"chars": 0, "count": 0, "topics": []}
            notes = []
            for domain_name in sorted(_os.listdir(library)):
                if domain_name in (".history", "健康日报"):
                    continue
                domain_dir = _os.path.join(library, domain_name)
                if not _os.path.isdir(domain_dir):
                    continue
                for fname in sorted(_os.listdir(domain_dir)):
                    if not fname.endswith(".md"):
                        continue
                    stem = fname[:-3]
                    if stem in ("MEMORY", "index"):
                        continue
                    fm = _read_note_frontmatter(_os.path.join(domain_dir, fname))
                    if not fm:
                        continue
                    notes.append({
                        "domain": domain_name,
                        "topic": fm.get("topic") or stem,
                        "version": fm.get("version", "?"),
                        "last_touched": fm.get("last_touched", "?"),
                        "sessions": fm.get("source_sessions", []),
                    })
            if not notes:
                return "", {"chars": 0, "count": 0, "topics": []}
            picked = []
            seen = set()
            # 路径 1：sid 命中 source_sessions → 必带
            if session_id:
                for n in notes:
                    if session_id in n["sessions"] and n["topic"] not in seen:
                        picked.append(n)
                        seen.add(n["topic"])
            # 路径 2：用户消息命中主题词 → 临时带
            u = (user_input or "").strip()
            if u:
                for n in notes:
                    if n["topic"] in seen:
                        continue
                    if n["topic"] and (n["topic"] in u or u in n["topic"]):
                        picked.append(n)
                        seen.add(n["topic"])
            picked = picked[:3]
            if not picked:
                return "", {"chars": 0, "count": 0, "topics": []}
            lines = []
            for n in picked:
                lines.append(
                    f"📚 关联笔记：{n['domain']}/{n['topic']}.md"
                    f"（v{n['version']} · {n['last_touched']} 更新 · "
                    f"深入讨论请先用 read_local_file 读全文再答）"
                )
            # 段预算 300 字符：超了从末尾逐条丢弃（保留关联度最高的前几条）
            while len("\n".join(lines)) > 300 and len(lines) > 1:
                lines.pop()
            text = "\n".join(lines)
            if len(text) > 300:
                text = text[:300]
            return text, {
                "chars": len(text),
                "count": len(lines),
                "topics": [n["topic"] for n in picked[:len(lines)]],
            }
        except Exception as e:
            logger.warning("note pointer scan failed (silent degrade): %s", e)
            try:
                from core.event_bus import event_bus
                event_bus.write("notes.error", {"error": f"pointer scan: {e}"})
            except Exception:
                pass
            return "", {"chars": 0, "count": 0, "topics": []}
