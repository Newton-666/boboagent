"""core/adapt.py — 适配层（阶段 E：灵魂的第一实体）。

把用户画像（USER_PREF 记忆）接成路由器的"奖励通道"——只调整权重（哪些
skills / 记忆类型优先），不碰前馈逻辑与 description（Pi 边界写死：方向盘
不可动，权重可学）。

闭环：用户反馈 → learner 写 USER_PREF 记忆 → adapt 读画像 → 调整路由权重
     → 下一轮技能激活 / 记忆召回更贴合偏好 → 用户更顺 → （奖励信号回流）

护栏：只作用于"因人而异"的路由决策；安全/收尾永不碰；BOBO_ADAPT=0 可关（默认开，
随 ROUTER 一起生效——此前默认关，TICKET-HARNESS-LIGHTS：owner 点亮 harness 灯）。

红线（issue #8 / TICKET-HARNESS-LIGHTS）：boost 不得改 plan.tool_names，也不得
接到工具注入/过滤。全量工具注入是故意边界（commit 062ca05 / COST-3 / B55 召回
/ B68 schema 缓存），把 adapt 接回注入面会回退冷启动稳定性。正确修法是删死路径，
不是"补接线"。
"""
import logging
import os

logger = logging.getLogger(__name__)

# 画像关键词 → 偏好 domain（识别用；不再映射到 TOOL_DOMAINS / tool_names）
_PREFERENCE_DOMAINS = [
    (("python", "脚本", "代码", "编程", "开发"), ["file", "terminal"]),
    (("obsidian", "笔记"), ["obsidian"]),
    (("notion",), ["notion"]),
    (("邮件", "邮箱"), ["email"]),
    (("网页", "浏览器", "上网"), ["web"]),
    (("github", "git"), ["github"]),
]

# 偏好 domain → 技能候选（additive）。故意不映射 TOOL_DOMAINS：
# 全量工具注入是故意边界（062ca05 / COST-3 / B55 / B68）。
# TICKET-HARNESS-LIGHTS：boost 只留 skills/memory，禁止接注入面。
_DOMAIN_SKILLS = {
    "file": ["code-fix"],
    "terminal": ["code-fix"],
    "obsidian": ["note-taking"],
    "notion": ["note-taking"],
    "web": ["web-design", "research"],
    "github": ["git-workflow"],
}

_DOMAIN_MEMORY = {
    "file": ["LESSON", "FACT"],
    "terminal": ["LESSON"],
    "obsidian": ["FACT"],
    "notion": ["FACT"],
    "web": ["FACT"],
    "github": ["LESSON"],
    "email": ["FACT"],
}


def adapt_enabled() -> bool:
    return os.environ.get("BOBO_ADAPT", "1") == "1"


def profile_text(profile: dict) -> str:
    """画像 → 文本（供关键词扫描）。"""
    parts = []
    if isinstance(profile, dict):
        for v in profile.values():
            if isinstance(v, dict) and v.get("value"):
                parts.append(str(v["value"]))
            elif isinstance(v, str):
                parts.append(v)
    return " ".join(parts)


def preference_domains(profile: dict) -> list:
    """画像中命中的偏好 domain（权重提升对象）。"""
    text = (profile_text(profile) or "").lower()
    hits = []
    for keywords, domains in _PREFERENCE_DOMAINS:
        if any(k.lower() in text for k in keywords):
            hits.extend(domains)
    return hits


def _unique_extend(dst: list, src) -> list:
    seen = set(dst)
    out = list(dst)
    for item in src:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def preference_skills(profile: dict) -> list:
    """画像命中的技能候选（additive boost 对象）。"""
    hits = []
    for dom in preference_domains(profile):
        hits = _unique_extend(hits, _DOMAIN_SKILLS.get(dom, []))
    return hits


def preference_memory_types(profile: dict) -> list:
    """画像命中的记忆类型（additive boost 对象）。"""
    hits = []
    for dom in preference_domains(profile):
        hits = _unique_extend(hits, _DOMAIN_MEMORY.get(dom, []))
    return hits


def boost_route(plan, profile: dict) -> None:
    """按画像提升 skills / memory 路由权重（additive，不删不改判据）。

    TICKET-HARNESS-LIGHTS / issue #8：禁止改 plan.tool_names。
    全量工具注入是故意边界（062ca05 / COST-3 / B55 / B68）。把 adapt
    接到工具注入面会回退冷启动稳定性，不是该修的方向。

    memory_types 空列表 = injector 全类型召回（entry_types=None）。从空列表
    追加会把"全类型"收成子集（召回缩水）。只在路由已经在过滤时做 additive
    扩展。
    """
    if not profile:
        return
    for skill in preference_skills(profile):
        if skill not in plan.skill_names:
            plan.skill_names.append(skill)
    if plan.memory_types:
        for mt in preference_memory_types(profile):
            if mt not in plan.memory_types:
                plan.memory_types.append(mt)


def adapt(plan, profile: dict) -> None:
    """适配入口：BOBO_ADAPT=1 时按画像提升 skills/memory 路由权重。"""
    if adapt_enabled() and profile:
        boost_route(plan, profile)
