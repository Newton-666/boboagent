"""injector.py — Prompt 注入管道：将 engine 状态组装成完整的 messages 列表。

从 engine.py 的 _call_llm 方法提取。纯注入逻辑，不含 API 调用。
注入顺序必须与原 _call_llm 完全一致。
"""

import json
import os as _os
import logging
import time as _time
from datetime import datetime as _datetime

from core.prompt_pool import get_prompt_pool

logger = logging.getLogger(__name__)

# 票 LN-4：活体知识库（library/<domain>/<topic>.md），与 tools/living_notes.py 同源
_LIBRARY_DIR = _os.path.join(
    _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "library")

# 票 TICKET-E3b：GUIDANCE 预付层导航（L2，docs/GUIDANCE.md）
_GUIDANCE_PATH = _os.path.join(
    _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
    "docs", "GUIDANCE.md")
_GUIDANCE_CACHE: dict = {"mtime": -1, "content": None}


def _load_guidance() -> str | None:
    """模块级缓存读 docs/GUIDANCE.md：mtime 变化才重读，缺失静默返回 None。

    每轮 build_messages 只做一次 _os.stat（无 IO），文件不变不重复读盘；
    文件缺失或不可读时返回 None，调用方静默跳过注入。
    """
    try:
        st = _os.stat(_GUIDANCE_PATH)
    except OSError:
        _GUIDANCE_CACHE["content"] = None
        _GUIDANCE_CACHE["mtime"] = -1
        return None
    if st.st_mtime != _GUIDANCE_CACHE.get("mtime"):
        try:
            with open(_GUIDANCE_PATH, encoding="utf-8") as f:
                _GUIDANCE_CACHE["content"] = f.read()
            _GUIDANCE_CACHE["mtime"] = st.st_mtime
        except OSError:
            _GUIDANCE_CACHE["content"] = None
            _GUIDANCE_CACHE["mtime"] = -1
            return None
    return _GUIDANCE_CACHE["content"]


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
    2. 自定义 API
    3. 用户资料 + 记忆
    4. 改动日志（tracker.recent_changes）
    5. 已读文件（tracker.recent_reads）
    6. 主动连接（proactive.inject_context）
    7. 技能标准（skill_loader.load_standards，命中才注入全文）
    8. GUIDANCE 导航（docs/GUIDANCE.md，预付层 L2，紧跟自查协议之后）
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

        # ── 票 TICKET-021：失忆自查协议（身份段追加，指令口吻，≤250字符）──
        _lib_index = _os.path.relpath(_os.path.join(_LIBRARY_DIR, "index.md"))
        messages.insert(1, {
            "role": "system",
            "content": (
                "【上下文自查协议】当你无法确定本会话之前做过什么、"
                "或用户引用你没有印象的前文时：禁止猜测。"
                f"先 read_local_file 读 {_lib_index} 找相关笔记，"
                "再读笔记全文恢复上下文。笔记是你在过去会话中亲手写的工作记录，可信。"
            ),
        })

        # ── 票 LN-4：上下文预算统计（各段组装时填充，return 前写 prompt.budget 事件）──
        budget_stats = {
            "identity": len(system_prompt),
            "memory": {"chars": 0, "entries": 0, "total_entries": 0, "evicted": 0},
            "skills": {"chars": 0, "truncated": False},
            "note_pointers": {"chars": 0, "count": 0, "topics": []},
            "guidance": {"chars": 0},
        }

        # ── 票 TICKET-E3b：GUIDANCE 预付层导航（紧跟自查协议之后，缺失静默）──
        _guidance = _load_guidance()
        if _guidance:
            messages.insert(2, {
                "role": "system",
                "content": _guidance,
            })
            budget_stats["guidance"] = {"chars": len(_guidance)}

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
            # 注入记忆（票 LN-5：按总池比例计算 memory floor/ceiling，低信号淘汰）
            if not engine._compressing:
                pool = get_prompt_pool()
                mem_floor = pool.floor("memory")
                mem_ceiling = pool.ceiling("memory")
                mem_text, mem_stats = format_memory_by_signal(
                    max_chars=mem_ceiling, min_chars=min(mem_floor, mem_ceiling))
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
                        "floor": mem_floor,
                        "ceiling": mem_ceiling,
                    }
        except Exception as e:
            logger.debug("注入用户资料/记忆失败: %s", e)

        # ── 4.5 关联笔记指针（票 LN-4：轻指针 + 按需翻阅，不整篇注入）──
        # 票 TICKET-022：分区展示——产出清单在前（"你写的"），主题词命中在后（"相关"）
        # 翻阅纪律作为尾部文案
        try:
            ledger_text, ledger_stats = self._build_session_notes_ledger(session_id)
            pointer_text, pointer_stats = self._build_note_pointers(
                session_id, user_input)

            combined_parts = []
            if ledger_text:
                combined_parts.append(ledger_text)
            if pointer_text:
                # 票 TICKET-021：上轮压缩过则置顶"历史已压缩"指引
                if getattr(engine, '_just_compressed', False):
                    pointer_text = (
                        "⚠️ 历史已压缩。若对早前工作有疑问，先翻阅上方关联笔记再作答。\n"
                        + pointer_text
                    )
                    engine._just_compressed = False
                combined_parts.append(pointer_text)

            if combined_parts:
                combined = "\n".join(combined_parts)
                messages.insert(1, {
                    "role": "system",
                    "content": combined
                })
                merged_stats = {**pointer_stats}
                merged_stats["session_notes"] = ledger_stats.get("session_notes", 0)
                budget_stats["note_pointers"] = merged_stats
        except Exception as e:
            logger.debug("注入笔记指针失败: %s", e)

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

        # ── 9. 技能标准（票 TICKET-E3b：未命中清单已删，仅命中才注入）──
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

        # ── 10. 上下文预算监控（票 LN-4 + LN-5）────
        # 组装完成写 prompt.budget 事件（兼容 LN-4）
        # 同时写 prompt.budget.decision 事件，记录每段 allocated/used/evicted
        try:
            from core.event_bus import event_bus

            pool = get_prompt_pool()
            allocated = {name: pool.ceiling(name) for name in budget_stats.keys()}
            total_chars = sum(len(m.get("content", "")) for m in messages)
            event_bus.write("prompt.budget", {
                "sid": session_id,
                "total_chars": total_chars,
                "pool_total": pool.total,
                "pool_source": pool.source,
                "sections": budget_stats,
            })
            event_bus.write("prompt.budget.decision", {
                "sid": session_id,
                "total_pool": pool.total,
                "pool_source": pool.source,
                "total_chars": total_chars,
                "allocated": allocated,
                "used": {
                    name: (stats.get("chars") if isinstance(stats, dict) else stats)
                    for name, stats in budget_stats.items()
                },
                "evicted": {
                    "memory": budget_stats.get("memory", {}).get("evicted", 0),
                    "skills": 0,
                    "note_pointers": 0,
                },
            })
        except Exception:
            pass

        return messages

    def _build_session_notes_ledger(self, session_id: str) -> tuple[str, dict]:
        """票 TICKET-022：会话笔记台账——从 events.jsonl 尾部读取 notes.written/updated
        事件，按当前 sid 过滤，生成本会话产出清单。

        IO 防护：只读尾部 N 行（默认 2000，可用 BOBO_EVENTS_TAIL_LINES 环境变量调），
        禁止全文件扫描。文件不存在 / 无事件 / 读取失败 → 返回空串，静默省略。

        返回 (text, stats)：stats = {"session_notes": 产出篇数}。
        """
        if not session_id:
            return "", {"session_notes": 0}
        try:
            from core.event_bus import event_bus as _ebus
        except Exception:
            return "", {"session_notes": 0}

        events_path = _ebus.filepath if hasattr(_ebus, 'filepath') else ""
        if not events_path or not _os.path.isfile(events_path):
            return "", {"session_notes": 0}

        tail_lines = 2000
        try:
            tail_lines = int(_os.environ.get("BOBO_EVENTS_TAIL_LINES", "2000"))
        except (ValueError, TypeError):
            pass

        try:
            with open(events_path, "rb") as f:
                f.seek(0, 2)
                fsize = f.tell()
                if fsize == 0:
                    return "", {"session_notes": 0}
                # 从尾部读约 tail_lines 行的块
                chunk_size = tail_lines * 512
                offset = max(0, fsize - chunk_size)
                f.seek(offset)
                raw = f.read().decode("utf-8", errors="replace")
                lines = raw.splitlines()
                if len(lines) > tail_lines:
                    lines = lines[-tail_lines:]
        except Exception:
            return "", {"session_notes": 0}

        # 解析尾部 JSONL，按 sid 过滤 notes.written / notes.updated
        seen_paths: dict[str, dict] = {}  # path → {topic, version, ts}
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if e.get("type") not in ("notes.written", "notes.updated"):
                continue
            # sid 字段可能在 sid 或 session_id
            e_sid = e.get("sid") or e.get("session_id", "")
            if e_sid != session_id:
                continue
            path = e.get("path", "")
            if not path:
                continue
            topic = e.get("topic", "")
            version = e.get("version", 1)
            ts = e.get("ts", 0)
            # notes.updated 覆盖 notes.written（更高版本）
            if path not in seen_paths or version > seen_paths[path].get("version", 0):
                seen_paths[path] = {
                    "path": path,
                    "topic": topic,
                    "version": version,
                    "ts": ts,
                }

        if not seen_paths:
            return "", {"session_notes": 0}

        # 按时间排序，生成产出清单
        sorted_notes = sorted(seen_paths.values(), key=lambda x: x["ts"])
        count = len(sorted_notes)

        # 预算来自 PromptPool note_pointers 段（6% 总池），产出清单在其中优先分配
        pool = get_prompt_pool()
        pointer_ceiling = pool.ceiling("note_pointers")

        # 确保最少能展示页眉 + 翻阅纪律（约 120 字符），剩余给条目
        header = f"\n📝 本会话已产出笔记 {count} 篇（可按需 read_local_file 翻阅，勿全量读取）：\n"
        footer = "翻阅纪律：笔记按需单篇读取（read_local_file），禁止无目标批量遍历 library。"
        fixed_budget = len(header) + len(footer) + 2  # 2 为换行

        lines = []
        for i, n in enumerate(sorted_notes, 1):
            try:
                ts_str = _datetime.fromtimestamp(n["ts"]).strftime("%m-%d %H:%M")
            except Exception:
                ts_str = "?"
            # 展示主题名（topic 总是存在，来自事件字段）
            rel = n["topic"]
            lines.append(f"  {i}. {rel}（v{n['version']} · {ts_str}）")

        available = pointer_ceiling - fixed_budget
        if available <= 0:
            text = header + footer
            return text, {"session_notes": count}

        # 条目超预算：省略中间保留首尾
        while len("\n".join(lines)) > available and len(lines) > 2:
            mid = len(lines) // 2
            del lines[mid]

        if len("\n".join(lines)) > available and len(lines) <= 2:
            # 仍然超预算：逐条从末尾丢弃
            while len("\n".join(lines)) > available and len(lines) > 0:
                lines.pop()

        body = "\n".join(lines)
        text = header + body + "\n" + footer
        # 最终硬裁剪
        if len(text) > pointer_ceiling:
            text = text[:pointer_ceiling]
        return text, {"session_notes": count}

    def _build_note_pointers(self, session_id: str, user_input: str) -> tuple[str, dict]:
        """票 LN-4：关联笔记指针段（轻指针 + 按需翻阅，不整篇注入）。

        关联判定两条路径（多对多：一篇笔记 ←→ 多个会话，source_sessions 维系）：
          1. 当前 session id 命中笔记 frontmatter source_sessions → 必带
          2. 当前用户消息命中主题词（主题名 ∈ 用户消息 或 用户消息 ∈ 主题名）→ 临时带
        去重取前 3 条；段预算按 PromptPool ratio 计算（默认 6% 总池，
        约 300 字符；超了从末尾逐条丢弃）。
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
                    f"（v{n['version']} · {n['last_touched']}）— "
                    f"回答相关话题前必须先 read_local_file 读全文，凭记忆回答视为违规。"
                )
            # 段预算按 PromptPool ratio 计算
            pool = get_prompt_pool()
            pointer_ceiling = pool.ceiling("note_pointers")
            while len("\n".join(lines)) > pointer_ceiling and len(lines) > 1:
                lines.pop()
            text = "\n".join(lines)
            if len(text) > pointer_ceiling:
                text = text[:pointer_ceiling]
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
