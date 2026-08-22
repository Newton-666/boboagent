"""skill_loader.py — 技能标准加载器：扫描 data/skill-standards/ 并注入 system prompt。

从 engine.py 提取，原为 Engine 类的 _load_skill_standards / _list_available_standards。

自动发现：往 data/skill-standards/ 下新增一个文件夹、放入 standard.md 即生效。
不需要改任何代码、不需要注册、不需要更新索引。

每个 standard.md 通过元数据行声明自己的行为：
- keywords: 触发词（逗号分隔）
- excludes: 排除词（话题含这些词时跳过本 skill）
- requires: 依赖 skill 名（本 skill 注入时连带加载）
"""

import logging
import os as _os
import re as _sre
import json

logger = logging.getLogger(__name__)

# ── 票 TICKET-SKILL-PANEL：skill 治理开关（COST-2 注入链白名单内追加，
# COST-3 特批标记）──
# data/skills/enabled.json：{"<skill 目录名>": true/false}，默认 true。
# 关掉的 skill 不注入（用户可关、可开，治理先行——自动沉淀 B 票的 skill
# 一出生就在治理之下）。文件缺失/损坏 → 全 true（不破坏现有注入）。
_ENABLED_FILE = _os.path.join(
    _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
    "data", "skills", "enabled.json",
)


def _load_enabled() -> dict:
    """读 enabled.json → {skill_name: bool}；缺失/损坏返回 {}（= 全默认开）。"""
    try:
        with open(_ENABLED_FILE, encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, dict):
            return {k: bool(v) for k, v in raw.items()}
    except (OSError, ValueError):
        pass
    return {}


class SkillLoader:
    """扫描技能标准目录，匹配触发词后注入标准到 system prompt。两遍评分 + 依赖链解析。"""

    def __init__(self, get_history, llm_caller=None):
        """初始化技能加载器。

        Args:
            get_history: 可调用对象，返回 self.history 列表（用于提取用户消息匹配触发词）
            llm_caller: 可选 callable（create_llm_caller 返回），用于 LLM 语义判断
                skill 匹配（替代硬编码 trigger_words）。None 时回退 trigger_words 评分。
        """
        self._get_history = get_history
        self._llm_caller = llm_caller

    def load_standards(self) -> list[str]:
        """扫描 data/skill-standards/*/standard.md，返回所有匹配的标准全文（按匹配度降序）。

        匹配策略（票 TICKET-SKILL-LLM-MATCH，COST-2/COST-3 特批）：
        - 有 llm_caller → LLM 语义判断命中（thinking_disabled=True 冷调用）
        - 无 llm_caller 或 LLM 判断失败 → trigger_words 评分兜底（降级不丢纪律）
        enabled 治理：用户关掉的 skill 不参与判断（同 SKILL-PANEL）。
        """
        try:
            std_dir = _os.path.join(_os.path.dirname(_os.path.dirname(
                _os.path.abspath(__file__))), "data", "skill-standards")
            if not _os.path.isdir(std_dir):
                return []
            history = self._get_history()
            # TICKET-VISION-CHAT-UPLOAD（COST-3 特批标记）：user content 可能是
            # 多模态 list（[{"type":"text",...},{"type":"image_url",...}]）——
            # 取 text 部分，否则 " ".join 遇 list 元素报
            # "sequence item 0: expected str"。
            def _as_text(c):
                if isinstance(c, str):
                    return c
                if isinstance(c, list):
                    return " ".join(str(x.get("text", "")) for x in c
                                    if isinstance(x, dict) and x.get("text"))
                return str(c)
            user_msgs = [_as_text(m.get("content", "")) for m in history[-4:]
                         if m.get("role") == "user" and m.get("content")]
            topic = " ".join(user_msgs[-1:]).lower() if user_msgs else ""

            entries = self._load_entries(std_dir)

            # ── 票 TICKET-SKILL-PANEL：治理开关——关掉的 skill 不参与判断 ──
            enabled = _load_enabled()

            # 第一层：trigger 找候选（本地零成本）——作为候选范围，缩小 LLM 判断。
            # 保留 trigger 是为了：(a) 无 llm_caller 时降级不丢纪律；(b) 缩小 LLM
            # 判断范围省 token（COST-2）；(c) 普通消息无候选 → 不调 LLM（零成本）。
            candidates = self._judge_by_triggers(topic, entries, enabled)

            # 第二层：LLM 语义确认（有 llm_caller + 候选 + topic 时）——从候选里挑
            # 真正语义匹配的，消除触发词重叠误触发（如 code-fix vs self-diagnose）。
            # None = LLM 失败/不可用 → 用候选兜底（降级不丢纪律）。
            hits = None
            if self._llm_caller and topic and candidates:
                hits = self._judge_by_llm(topic, candidates, entries, enabled)
            if hits is None:
                hits = candidates

            # requires 依赖链（连带加载依赖 skill，跳过 excludes 检查）
            hits = self._resolve_requires(hits, entries, enabled)

            return [entries[name]["content"] for name in hits]
        except Exception:
            return []

    def _load_entries(self, std_dir):
        """第一遍：加载所有 skill 的元数据（不评分）。"""
        entries = {}
        for entry in _os.listdir(std_dir):
            path = _os.path.join(std_dir, entry, "standard.md")
            if not _os.path.isfile(path):
                continue
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            kw = _sre.search(r'keywords:\s*(.+)', content, _sre.IGNORECASE)
            trigger_words = [w.strip().lower() for w in (kw.group(1).split(",") if kw else [])]
            if not trigger_words:
                trigger_words = (entry + " " + content.split("\n")[0]).lower().split()
            ex = _sre.search(r'excludes:\s*(.+)', content, _sre.IGNORECASE)
            exclude_words = [w.strip().lower() for w in (ex.group(1).split(",") if ex else [])]
            req = _sre.search(r'requires:\s*(.+)', content, _sre.IGNORECASE)
            require_names = [w.strip() for w in (req.group(1).split(",") if req else [])]
            entries[entry] = {
                "content": content,
                "trigger_words": trigger_words,
                "exclude_words": exclude_words,
                "require_names": require_names,
            }
        return entries

    def _judge_by_triggers(self, topic, entries, enabled):
        """第二遍：trigger_words 评分 + 排除过滤（LLM 不可用时的兜底）。"""
        scored = []
        for name, info in entries.items():
            if info["exclude_words"] and any(ew in topic for ew in info["exclude_words"]):
                continue
            score = sum(1 for tw in info["trigger_words"] if tw and tw in topic)
            if score > 0:
                scored.append((score, name))
        scored.sort(key=lambda x: x[0], reverse=True)
        top_names = [name for _, name in scored[:3]]
        if enabled:
            top_names = [n for n in top_names if enabled.get(n, True)]
        return top_names

    def _build_catalog(self, candidates, entries, enabled):
        """构建 LLM 判断用的候选技能清单（name + 一句话描述，不含全文）。"""
        lines = []
        for name in candidates:
            info = entries.get(name)
            if not info:
                continue
            if enabled and not enabled.get(name, True):
                continue
            kw = ", ".join(info["trigger_words"][:8])
            lines.append(f"- {name}: 触发词 {kw}")
        return "\n".join(lines)

    def _judge_by_llm(self, topic, candidates, entries, enabled):
        """从 trigger 候选里做 LLM 语义确认（thinking_disabled 冷调用，防烧 token）。

        返回 list[str]（候选内的命中）或 None（无 llm_caller / 无 topic / 无候选 /
        LLM 异常 → 调用方用候选兜底）。
        """
        if not self._llm_caller or not topic or not candidates:
            return None
        try:
            catalog = self._build_catalog(candidates, entries, enabled)
            if not catalog:
                return []
            system = (
                "你是技能标准匹配判断器。根据用户任务描述，从候选技能中判断应激活哪些。\n"
                "规则：\n"
                "1. 只返回任务**直接**匹配的技能名，每行一个，不要序号/解释。\n"
                "2. 触发词重叠导致多个候选时，只选语义最匹配的（通用纪律类技能如\n"
                "   self-diagnose 仅在无更具体技能时才返回）。\n"
                "3. 候选都不匹配任务 → 只输出 NONE。\n"
                "候选技能：\n" + catalog
            )
            user = "任务描述：\n" + topic
            prompt = [{"role": "system", "content": system},
                      {"role": "user", "content": user}]
            resp = self._llm_caller(prompt, use_tools=False,
                                    thinking_disabled=True, max_tokens=200)
            text = ""
            try:
                text = (resp.get("choices", [{}])[0]
                        .get("message", {}).get("content", ""))
            except (AttributeError, IndexError, TypeError):
                text = ""
            return self._parse_hits(text, candidates, entries, enabled)
        except Exception:
            return None

    def _parse_hits(self, text, candidates, entries, enabled):
        """从 LLM 返回文本解析命中的候选 skill 名（仅保留 enabled 且存在者）。

        返回 list[str] 或 None：None = LLM 无有效输出（判断失败）→ 调用方走候选
        兜底；[] = LLM 明确无匹配（如输出 NONE）→ 不注入；[names] = 命中。
        """
        if not text or not text.strip():
            return None
        hits = []
        for name in candidates:
            if enabled and not enabled.get(name, True):
                continue
            if _sre.search(r'\b' + _sre.escape(name) + r'\b', text, _sre.IGNORECASE):
                hits.append(name)
        return hits

    def _resolve_requires(self, hits, entries, enabled):
        """解析 requires：连带加载依赖 skill（跳过 excludes 检查），enabled 一视同仁。"""
        top_set = set(hits)
        for name in list(hits):
            for req_name in entries.get(name, {}).get("require_names", []):
                if req_name in entries and req_name not in top_set:
                    top_set.add(req_name)
                    hits.append(req_name)
        if enabled:
            hits = [n for n in hits if enabled.get(n, True)]
        return hits
