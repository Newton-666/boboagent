"""proactive.py — 主动模式管理器：连接发现、上下文注入、用户参与度追踪。

从 engine.py 提取，原为 Engine 类的 _load_proactive_config / _extract_topic /
_semantic_filter / _find_connections / _inject_connection_context /
_track_engagement / _maybe_downgrade / _track_citation。
"""

import json
import re
import logging

logger = logging.getLogger(__name__)


class ProactiveManager:
    """管理主动知识注入：发现相关记忆 → 注入上下文 → 追踪用户参与度。"""

    def __init__(self):
        self.mode: str = "off"
        self.stats: dict = {"offered": 0, "engaged": 0}
        self._last_memory_ids: list = []

    # ── 配置加载 ──

    def load_config(self):
        """从 config 或环境变量加载主动模式级别。"""
        try:
            from config import BOBO_PROACTIVE_MODE
            self.mode = BOBO_PROACTIVE_MODE
        except (ImportError, AssertionError):
            self.mode = "off"

    # ── 工具方法 ──

    def _extract_topic(self, messages: list) -> str:
        """从最近几条用户消息中提取对话主题（用于搜索相关连接）。"""
        user_msgs = [m.get("content", "") for m in messages[-6:]
                     if m.get("role") == "user" and m.get("content")]
        if not user_msgs:
            return ""
        # 取最近 2 条用户消息拼接，不超过 200 字
        topic_text = " ".join(user_msgs[-2:])
        return topic_text[:200]

    def _semantic_filter(self, topic: str, candidates: list) -> list:
        """用 LLM 过滤不相关的记忆候选。

        Returns:
            过滤后的候选列表。失败时返回原列表。
        """
        if len(candidates) <= 1:
            return candidates
        try:
            from core.llm_caller import call_llm
            candidate_text = "\n".join(
                f"[{i}] {c.get('content', '')[:120]}"
                for i, c in enumerate(candidates)
            )
            prompt = (
                f"对话主题: {topic}\n\n"
                f"候选记忆:\n{candidate_text}\n\n"
                "请判断每条记忆与当前主题的相关性。"
                "仅返回相关条目的编号，用逗号分隔（例如: 0,2,5）。"
                "如果都不相关，返回 0。只返回数字和逗号。"
            )
            result = call_llm([{"role": "user", "content": prompt}], max_tokens=50)
            content = result.get("content", "") if isinstance(result, dict) else str(result)
            nums = re.findall(r'\d+', content)
            ids = [int(n) for n in nums]
            # 如果 LLM 说 0（都不相关），只保留第一条作为兜底
            if not ids or 0 in {int(n) for n in nums if int(n) == 0}:
                return candidates[:1]
            filtered = [candidates[i] for i in ids if 0 <= i < len(candidates)]
            return filtered or candidates[:1]
        except Exception:
            logger.debug("语义过滤失败", exc_info=True)
            return candidates[:3]  # 降级：取前 3 条

    def _find_connections(self, topic: str) -> list[str]:
        """发现与当前话题相关的知识连接（记忆 + Obsidian 笔记）。

        Returns:
            连接字符串列表，每条为一个可注入的上下文。
        """
        connections = []
        # 1. 搜索记忆
        try:
            from tools.v5_memory import get_top_memories, bump_signal
            candidates = get_top_memories(topic, limit=8)
            if candidates:
                filtered = self._semantic_filter(topic, candidates)
                for mem in filtered[:3]:
                    conn = f"[记忆] {mem.get('content', '')}"
                    if mem.get("id"):
                        conn += f" (id:{mem['id']})"
                    connections.append(conn)
                # bump 已过滤的记忆
                for mem in filtered[:3]:
                    bump_signal(mem.get("id", ""))
        except Exception:
            logger.debug("搜索记忆失败", exc_info=True)

        # 2. 搜索 Obsidian
        try:
            from tools.obsidian_tools import search_obsidian_notes
            results = search_obsidian_notes(topic)
            for r in results[:3]:
                connections.append(f"[笔记] {r}")
        except Exception:
            logger.debug("搜索 Obsidian 失败", exc_info=True)

        return connections

    # ── 注入 ──

    def inject_context(self, messages: list) -> list:
        """在 messages 中注入知识上下文（修改 system message 或前置）。"""
        if self.mode == "off":
            return messages

        topic = self._extract_topic(messages)
        if not topic:
            return messages

        connections = self._find_connections(topic)
        if not connections:
            return messages

        # 构建注入文本
        prefix = "以下是你之前的知识记录，可能对当前对话有帮助：\n"
        inject_text = prefix + "\n".join(f"- {c}" for c in connections)

        # 记录本轮注入的记忆 ID
        self._last_memory_ids = []
        for conn in connections:
            m = re.search(r'\(id:([^)]+)\)', conn)
            if m:
                self._last_memory_ids.append(m.group(1))

        if self.mode == "full":
            # full 模式：直接在首位插入 system 消息
            messages.insert(0, {"role": "system", "content": inject_text})
        else:
            # subtle 模式：追加到已有 system prompt 末尾
            for msg in messages:
                if msg.get("role") == "system":
                    msg["content"] = (msg["content"] or "") + "\n\n" + inject_text
                    break
            else:
                messages.insert(0, {"role": "system", "content": inject_text})

        # --- 降级检查 ---
        self.stats["offered"] += 1
        try:
            from tools.v5_memory import decay_all
            decay_all()
        except Exception:
            pass
        self._maybe_downgrade()

        return messages

    # ── 参与度追踪 ──

    def track_engagement(self, user_input: str):
        """追踪用户是否在回应上一轮的连接提议。"""
        if self.stats["offered"] == 0:
            return
        # 如果用户输入与注入记忆关键词有交集，算作"参与"
        if user_input:
            self.stats["engaged"] += 1

    def _maybe_downgrade(self) -> str | None:
        """根据参与率自动降级主动模式。"""
        s = self.stats
        if s["offered"] >= 5:
            rate = s["engaged"] / s["offered"]
            if rate < 0.2:
                old = self.mode
                if self.mode == "full":
                    self.mode = "subtle"
                elif self.mode == "subtle":
                    self.mode = "off"
                if self.mode != old:
                    return f"主动模式已从 {old} 降为 {self.mode}（参与率 {rate:.0%}）"
        return None

    def track_citation(self, assistant_response: str, memory_ids: list):
        """LLM 回复中若引用了注入的记忆，自动 bump 该记忆的活跃度。"""
        if not memory_ids or not assistant_response:
            return
        try:
            from tools.v5_memory import bump_signal, get_all
            all_memories = get_all()
            cited = False
            for mem_id in memory_ids:
                # 在 LLM 回复中查找记忆内容片段
                for mem in all_memories:
                    if str(mem.get("id", "")) == str(mem_id):
                        snippet = mem.get("content", "")[:50]
                        if snippet and snippet in assistant_response:
                            bump_signal(mem_id)
                            cited = True
                        break
            # 如果 LLM 确实引用了记忆，且主动模式不是 off，考虑升级
            if cited and self.mode != "off" and self.mode != "full":
                self.mode = "full" if self.stats["engaged"] > 2 else self.mode
        except Exception:
            logger.debug("引用追踪失败", exc_info=True)
