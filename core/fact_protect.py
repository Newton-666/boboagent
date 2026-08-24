"""core/fact_protect.py — 压缩必保层（B67 设计：保存层守卫，注入层按需）。

在压缩替换历史前，从"将要被压掉的消息"中捞取关键事实 → 沉淀进记忆（durable）。
准入漏斗（非仅关键词，防缺触发词漏网）：
  ① 显式信号（关键词快路径，零成本）：记住/我喜欢/以后/别忘了/最重要…
  ② 硬事实规则（确定性）：代码/数字/路径/具体名字/决策结论（决定/改成/选/用）
  （③ LLM 语义兜底：预留——成本纪律下暂不默认启用，见 HARNESS-TECHNICAL #7）

两层分离：本模块只管"保存"（durable）；"注入"由 MoE 路由按需召回（不在此）。
"""
import logging
import re

logger = logging.getLogger(__name__)

# ① 显式信号关键词（用户明确要求记住 → 必保）
_EXPLICIT_KEYWORDS = (
    "记住", "别忘了", "以后都", "以后就", "我一直", "我喜欢", "我不喜欢",
    "我的习惯", "记住我", "最重要", "关键", "必须", "千万不要",
)

# ② 硬事实规则（确定性正则）
_HARD_FACT_PATTERNS = [
    (re.compile(r"https?://\S+"), "url"),
    (re.compile(r"[\w./\\-]+\.(py|js|ts|md|json|yaml|yml|txt|html|css)\b"), "path_file"),
    (re.compile(r"(/[\w.-]+){2,}"), "path"),
    (re.compile(r"\b\d{2,}\b"), "number"),
    (re.compile(r"(决定|改成|改为|换成|选用|选择用|以后用|不(再|要)用)\s*[^。！？\n]{2,30}"), "decision"),
    (re.compile(r"(密码|密钥|账号|token|api\s*key|配置|端口)\s*[=：:]\s*\S+"), "credential"),
]


def _explicit_hit(text: str) -> bool:
    t = str(text or "")
    return any(k in t for k in _EXPLICIT_KEYWORDS)


def _hard_fact_hits(text: str) -> list:
    hits = []
    for pat, kind in _HARD_FACT_PATTERNS:
        for m in pat.finditer(str(text or "")):
            hits.append((kind, m.group(0)[:60]))
    return hits


def protect_from_messages(messages: list, max_facts: int = 8) -> int:
    """从将被压缩的消息中提取受保护事实 → 写记忆（FACT/USER_PREF）。

    返回沉淀条数。零 LLM 成本（关键词 + 规则）。
    """
    try:
        from tools.v5_memory import save_to_knowledge_base
    except Exception:
        return 0
    saved = 0
    seen = set()
    for m in messages:
        content = m.get("content", "") or ""
        if isinstance(content, list):
            content = " ".join(str(x.get("text", "")) for x in content if isinstance(x, dict))
        text = str(content)
        if not text.strip():
            continue
        # ① 显式信号 → 整句必保（USER_PREF）
        if _explicit_hit(text):
            snippet = text.strip()[:120]
            if snippet and snippet not in seen:
                seen.add(snippet)
                try:
                    r = save_to_knowledge_base(snippet, entry_type="USER_PREF")
                    if r and "已保存" in r:
                        saved += 1
                except Exception:
                    pass
            continue
        # ② 硬事实 → 逐条沉淀（FACT）
        for kind, fact in _hard_fact_hits(text):
            if fact and fact not in seen and len(fact) >= 4:
                seen.add(fact)
                entry = f"{kind}: {fact}"
                try:
                    r = save_to_knowledge_base(entry, entry_type="FACT")
                    if r and "已保存" in r:
                        saved += 1
                except Exception:
                    pass
        if saved >= max_facts:
            break
    if saved:
        logger.debug("fact_protect: 保护 %d 条事实（压缩前沉淀）", saved)
    return saved
