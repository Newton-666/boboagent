"""core/router.py — 统一路由器（阶段 B，MoE 规则版 v1）。

接口（写死）：route(task, user_profile, recent_rounds) -> RoutePlan
  RoutePlan = {tool_names, skill_names, memory_types}  — 该轮上下文应带什么。

默认关闭（BOBO_ROUTER=0）：engine 行为不变（基线 diff=0）。
开启后：工具广告/技能激活/记忆召回按路由结果执行。

规则版 v1（从 tool_park + skill_loader 起步，适配层是第二阶段）：
- 工具：常驻小集 + 任务分类 → domain 映射
- 技能：任务分类 → 技能候选（最终激活仍由 description 语义，在 injector/LLM 侧）
- 记忆：任务分类 → 相关记忆类型

护栏：信号与结构分轨（本模块只做确定性规则，不碰学习环）。
"""
import os
import re
from dataclasses import dataclass, field

# ── 常驻工具（固定底座，每轮广告）──
RESIDENT_TOOLS = [
    "get_current_time", "read_local_file", "list_directory", "grep_code",
    "save_memory", "search_memory", "execute_terminal",
]

# ── 工具 domain 映射（预筛定位用，description 语义在 LLM 侧）──
TOOL_DOMAINS = {
    "file": ["edit_file", "file_operation", "file_writer", "delete_file",
             "read_local_file", "list_directory", "grep_code", "code_execution"],
    "terminal": ["execute_terminal", "run_tests", "code_execution"],
    "web": ["web_search", "web_fetch", "web_extract", "open_url"],
    "obsidian": ["search_obsidian", "read_obsidian", "write_obsidian",
                 "append_obsidian", "classify_note", "batch_move_notes"],
    "notion": ["notion_search", "notion_read_page", "notion_create_page", "notion_append"],
    "email": ["search_emails", "read_email_content", "analyze_emails"],
    "github": ["github_check_auth", "github_create_repo", "github_create_pr",
               "github_pr_comment", "github_pr_diff", "git_status"],
    "calendar": ["list_calendar_events", "create_calendar_event"],
    "memory": ["save_memory", "search_memory", "delete_entry", "memory_migrate"],
    "computer_use": ["computer_use", "capture", "click", "type", "key", "open_app", "scroll"],
    "notification": ["send_notification", "set_reminder"],
    "api": ["api_call", "api_register"],
}

# ── 任务关键词 → domain 分类（规则版 v1 的预筛判据）──
_TASK_RULES = [
    (("修复", "bug", "报错", "测试", "编译", "重构", "调试"), ["file", "terminal"]),
    (("提交", "commit", "推送", "push", "仓库", "pr", "github", "git"), ["github", "terminal"]),
    (("查", "搜索", "搜", "调研", "对比", "房价", "新闻", "资料", "research"), ["web", "obsidian"]),
    (("笔记", "obsidian", "记到", "整理笔记", "写作", "note"), ["obsidian"]),
    (("notion",), ["notion"]),
    (("邮件", "邮箱", "email", "收件"), ["email"]),
    (("日历", "日程", "提醒", "通知"), ["calendar", "notification"]),
    (("记住", "记忆", "保存记忆", "忘掉", "偏好"), ["memory"]),
    (("屏幕", "点击", "打开应用", "输入", "computer", "界面"), ["computer_use"]),
    (("api", "接口", "注册api"), ["api"]),
]

# ── 任务关键词 → 技能候选（激活仍由 description 语义定）──
_SKILL_RULES = [
    (("修复", "bug", "报错", "测试失败", "调试"), ["code-fix"]),
    (("提交", "commit", "push", "git"), ["git-workflow"]),
    (("查", "调研", "对比", "资料", "research", "搜"), ["research"]),
    (("笔记", "记到", "整理", "note"), ["note-taking"]),
    (("网页", "设计", "配色", "前端"), ["web-design"]),
]

# ── 任务关键词 → 相关记忆类型（B4 记忆召回路由）──
_MEMORY_RULES = [
    (("修复", "bug", "报错", "测试"), ["LESSON", "FACT"]),
    (("记住", "偏好", "习惯", "以后"), ["USER_PREF"]),
    (("不要", "规则", "禁止"), ["RULES"]),
    (("完成", "成就", "目标"), ["ACHIEVEMENT", "GOAL"]),
    (("查", "事实", "资料", "信息"), ["FACT"]),
]


@dataclass
class RoutePlan:
    tool_names: list = field(default_factory=list)
    skill_names: list = field(default_factory=list)
    memory_types: list = field(default_factory=list)


def router_enabled() -> bool:
    """BOBO_ROUTER=1 开启路由（默认关：行为不变，基线 diff=0）。"""
    return os.environ.get("BOBO_ROUTER", "0") == "1"


def classify_task(task: str) -> list:
    """任务关键词 → 命中规则（返回 [(domain/skill/memory, 关键词), ...]）。"""
    if not task:
        return []
    t = str(task).lower()
    hits = []
    for keywords, tags in _TASK_RULES:
        for k in keywords:
            if k.lower() in t:
                hits.append(("domain", k, tags))
                break
    return hits


def route(task: str, user_profile: dict = None, recent_rounds: list = None) -> RoutePlan:
    """统一路由（规则版 v1）：任务 → 工具/技能/记忆子集。

    无命中 → 返回常驻工具 + 空技能/记忆（对应"无技能命中按 domain 兜底"的设计；
    本版无命中时工具仅常驻集，兜底域在启用后观察再补）。
    """
    plan = RoutePlan(tool_names=list(RESIDENT_TOOLS))
    t = (task or "").lower()

    # 工具：domain 命中 → 追加 domain 工具
    for keywords, tags in _TASK_RULES:
        if any(k.lower() in t for k in keywords):
            for tag in tags:
                for tool in TOOL_DOMAINS.get(tag, []):
                    if tool not in plan.tool_names:
                        plan.tool_names.append(tool)
    # 技能：候选（最终激活由 injector/LLM 读 description 语义）
    for keywords, skills in _SKILL_RULES:
        if any(k.lower() in t for k in keywords):
            for s in skills:
                if s not in plan.skill_names:
                    plan.skill_names.append(s)
    # 记忆：相关类型
    for keywords, mtypes in _MEMORY_RULES:
        if any(k.lower() in t for k in keywords):
            for mt in mtypes:
                if mt not in plan.memory_types:
                    plan.memory_types.append(mt)
    return plan
