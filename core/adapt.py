"""core/adapt.py — 适配层（阶段 E：灵魂的第一实体）。

把用户画像（USER_PREF 记忆）接成路由器的"奖励通道"——只调整权重（哪些 domain
的工具优先广告），不碰前馈逻辑与 description（Pi 边界写死：方向盘不可动，权重可学）。

闭环：用户反馈 → learner 写 USER_PREF 记忆 → adapt 读画像 → 调整路由权重
     → 下一轮 LLM 看到更贴合的工具 → 用户更顺 → （奖励信号回流）

护栏：只作用于"因人而异"的路由决策；安全/收尾永不碰；BOBO_ADAPT=0 可关（默认开，
随 ROUTER 一起生效——此前默认关，TICKET-HARNESS-LIGHTS：owner 点亮 harness 灯）。
"""
import logging
import os

logger = logging.getLogger(__name__)

# 画像关键词 → 工具 domain 提升（偏好"Python/脚本"→ code/terminal 域权重升）
_PREFERENCE_DOMAINS = [
    (("python", "脚本", "代码", "编程", "开发"), ["file", "terminal"]),
    (("obsidian", "笔记"), ["obsidian"]),
    (("notion",), ["notion"]),
    (("邮件", "邮箱"), ["email"]),
    (("网页", "浏览器", "上网"), ["web"]),
    (("github", "git"), ["github"]),
]


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


def boost_route(plan, profile: dict) -> None:
    """调整路由权重：偏好 domain 的工具追加进广告集（additive，不删不改判据）。

    只加权重（计划内已选工具保留），不改 description、不改规则顺序。
    """
    if not profile:
        return
    from core.router import TOOL_DOMAINS
    for dom in preference_domains(profile):
        for tool in TOOL_DOMAINS.get(dom, []):
            if tool not in plan.tool_names:
                plan.tool_names.append(tool)


def adapt(plan, profile: dict) -> None:
    """适配入口：BOBO_ADAPT=1 时按画像提升路由权重。"""
    if adapt_enabled() and profile:
        boost_route(plan, profile)
