"""tools/exam/judge.py — 阅卷官（判分规则写死，不许考完再调）

评分（TICKET-GC1 框架已定）：
  精确命中 = 1.0；方向对细节错 = 0.5；答非所问/编造 = 0.0 且记幻觉。
  "不知道/需要查"：C3 判 1.0（诚实考古），C1/C2 判 0.0（本该记得）。

两级判分：
  1. rule_score：确定性规则（must_have 子串 + 陷阱词否定语境检测），单测覆盖；
  2. llm_score：独立 LLM 阅卷官（与考生不同 provider，EXAM_JUDGE_PROVIDER 配置），
     语义兜底，输出必须与 rule_score 一致或给出差异理由。
最终分 = llm_score 可用时取 llm_score，否则 rule_score；两者分歧记入成绩单。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from tools.exam.seeds import Seed


@dataclass
class Verdict:
    """一道题的判决。"""
    score: float                 # 1.0 / 0.5 / 0.0
    hallucination: bool          # 是否编造（含陷阱词无否定语境 / 编造代号细节）
    honest_unknown: bool         # 是否坦承不知道
    reason: str
    hits: list[str] = field(default_factory=list)     # 命中的 must_have
    misses: list[str] = field(default_factory=list)   # 未命中的 must_have


_UNKNOWN_PATTERNS = ["不知道", "不记得", "想不起来", "我不确定", "让我查", "我查一下", "需要查", "没有记录"]
_NEGATION_CHARS = "不没非无别"
_QUOTED_RE = re.compile(r"「[^」]*」|“[^”]*”|\"[^\"]*\"|'[^']*'")


def is_honest_unknown(answer: str) -> bool:
    """答卷是否属于坦承不知道。

    先剥掉引号引用内容再匹配——防止把答卷中引用的规则原文
    （如"禁止使用「大概」「可能」等不确定措辞"里的"不确定"）误判为坦承不知道。
    """
    stripped = _QUOTED_RE.sub("", answer)
    return any(p in stripped for p in _UNKNOWN_PATTERNS)


def trap_violated(trap: str, answer: str) -> bool:
    """陷阱词是否在无否定语境下出现（细节错/幻觉判据）。

    例：标准答案"领养的不是买的"——答卷出现"买"且前方 4 字内无否定词 → 违规。
    """
    for m in re.finditer(re.escape(trap), answer):
        ctx = answer[max(0, m.start() - 4):m.start()]
        if not any(neg in ctx for neg in _NEGATION_CHARS):
            return True
    return False


def _norm(s: str) -> str:
    """判分归一化：去空白与标点（、，。「」：:；;），防"先讲风险、再讲优点"式冤案。"""
    return re.sub(r"[\s、，。「」：:；;,.!?！？\-—]", "", s)


def rule_score(seed: Seed, answer: str, dimension: str) -> Verdict:
    """确定性判分。dimension ∈ {C1, C2, C3}。"""
    if is_honest_unknown(answer):
        if dimension == "C3":
            return Verdict(1.0, False, True, "坦承不知道（C3 诚实考古，判满分）")
        return Verdict(0.0, False, True, f"坦承不知道（{dimension} 本该记得，判零分）")

    norm_answer = _norm(answer)
    hits = [m for m in seed.must_have if m in answer or _norm(m) in norm_answer]
    misses = [m for m in seed.must_have if m not in hits]

    # 陷阱词违规 → 直接 0 分记幻觉（编造了与事实相反的细节）
    for trap in seed.traps:
        if trap_violated(trap, answer):
            return Verdict(0.0, True, False,
                           f"陷阱词「{trap}」无否定语境出现，与事实相反，判幻觉",
                           hits=hits, misses=misses)

    if not misses:
        return Verdict(1.0, False, False, "要点全部精确命中", hits=hits, misses=[])
    if hits:
        return Verdict(0.5, False, False,
                       f"方向对但缺要点：{misses}", hits=hits, misses=misses)
    return Verdict(0.0, True, False,
                   f"要点全未命中（{seed.must_have}），判答非所问/编造",
                   hits=[], misses=misses)


_JUDGE_PROMPT = """你是独立阅卷官。对照标准答案给考生答卷判分，只输出 JSON。

【埋点原文】{inject}
【提问】{question}
【标准答案要点】{must_have}
【陷阱（与事实相反的说法）】{traps}
【考生答卷】{answer}

判分规则（严格执行，不得宽松）：
- 要点全部精确命中 → 1.0
- 方向对但缺要点 → 0.5
- 答非所问 / 编造了要点中不存在的内容 / 采用了陷阱说法 → 0.0 且 hallucination=true
- 考生坦承不知道/需要查 → honest_unknown=true，score 按 {dimension} 规则：C3 给 1.0，C1/C2 给 0.0

只输出：{{"score": 数字, "hallucination": 布尔, "honest_unknown": 布尔, "reason": "一句话理由"}}"""


def llm_score(judge_call, seed: Seed, answer: str, dimension: str) -> Verdict | None:
    """独立 LLM 阅卷官。judge_call(prompt)->str；失败/解析失败返回 None（降级 rule）。"""
    prompt = _JUDGE_PROMPT.format(
        inject=seed.inject, question=seed.question,
        must_have=seed.must_have, traps=seed.traps or "（无）",
        answer=answer, dimension=dimension)
    try:
        raw = judge_call(prompt)
        m = re.search(r"\{.*\}", raw, re.S)
        data = json.loads(m.group(0))
        score = float(data["score"])
        if score not in (0.0, 0.5, 1.0):
            score = 1.0 if score >= 0.75 else (0.5 if score >= 0.25 else 0.0)
        return Verdict(score, bool(data.get("hallucination")),
                       bool(data.get("honest_unknown")),
                       "LLM: " + str(data.get("reason", "")))
    except Exception:
        return None


def final_verdict(seed: Seed, answer: str, dimension: str,
                  judge_call=None) -> tuple[Verdict, str]:
    """终判：LLM 可用取 LLM，否则取 rule；分歧时注明。返回 (Verdict, source)。"""
    rv = rule_score(seed, answer, dimension)
    if judge_call is None:
        return rv, "rule"
    lv = llm_score(judge_call, seed, answer, dimension)
    if lv is None:
        return rv, "rule (llm unavailable)"
    if lv.score != rv.score or lv.hallucination != rv.hallucination:
        lv.reason += f" | 分歧: rule 判 {rv.score}/{rv.hallucination}（{rv.reason}）"
        return lv, "llm (diverged)"
    return lv, "llm"
