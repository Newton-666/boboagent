"""injector.py — Prompt 注入管道：将 engine 状态组装成完整的 messages 列表。

从 engine.py 的 _call_llm 方法提取。纯注入逻辑，不含 API 调用。
注入顺序必须与原 _call_llm 完全一致。
"""

import json
import os as _os
import re as _re
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


# 票 TICKET-PROFILE-1：USER.md 用户模型画像（docs/USER.md，行为影响型）
# 与 _load_guidance 同模式：mtime 缓存，缺失静默返回 None。
_USER_PROFILE_PATH = _os.path.join(
    _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
    "docs", "USER.md")
_USER_PROFILE_CACHE: dict = {"mtime": -1, "content": None}


def _load_user_profile() -> str | None:
    """模块级缓存读 docs/USER.md：mtime 变化才重读，缺失静默返回 None。"""
    try:
        st = _os.stat(_USER_PROFILE_PATH)
    except OSError:
        _USER_PROFILE_CACHE["content"] = None
        _USER_PROFILE_CACHE["mtime"] = -1
        return None
    if st.st_mtime != _USER_PROFILE_CACHE.get("mtime"):
        try:
            with open(_USER_PROFILE_PATH, encoding="utf-8") as f:
                _USER_PROFILE_CACHE["content"] = f.read()
            _USER_PROFILE_CACHE["mtime"] = st.st_mtime
        except OSError:
            _USER_PROFILE_CACHE["content"] = None
            _USER_PROFILE_CACHE["mtime"] = -1
            return None
    return _USER_PROFILE_CACHE["content"]


# ── 票 TICKET-G1（母子结构 v2）：SELF.md 母文档同源读取 ──
# 母文档 docs/SELF.md 已由 owner/Kimi 定稿（不许改写），本票只交付机制：
# L0 常驻注入 = 顶部 [SELF] 代码块原文（逐字节，不许摘要/改写——母子同源）。
# 章节触发展开 = §2 架构 / §4 边界 / §5 自救，关键词命中才注入该章全文。
_SELF_PATH = _os.path.join(
    _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
    "docs", "SELF.md")
_SELF_CACHE: dict = {"mtime": -1, "content": None}

# 章节触发展开：主题 → (章节号, 触发关键词表)。关键词命中 user_input 或
# 最近 history 即注入该章全文；无触发则零注入（对照组铁律）。
_SELF_CHAPTER_TRIGGERS = {
    "arch":   {"title": "2. Architecture map",   "keywords": ("engine", "gateway", "tui", "injector", "architecture", "架构", "rpc", "session", "decision chain", "闸", "_confirm", "command_safety")},
    "boundary": {"title": "4. Boundaries and enforcement", "keywords": ("ticket", "authorized_paths", "protected", "read-only", "boundary", "边界", "执法", "role", "角色", "豁免", "越权", "exemption")},
    "rescue": {"title": "5. Failure self-rescue", "keywords": ("crash", "崩溃", "排查", "forensics", "自救", "log", "evidence", "复现", "escalate", "升级", "测试汇报", "fabricat")},
}


def _load_selfmap() -> str | None:
    """读 docs/SELF.md 全文（mtime 缓存），缺失/不可读返回 None。

    与 _load_guidance 同模式：每轮只做一次 _os.stat，文件不变不重复读盘。
    """
    try:
        st = _os.stat(_SELF_PATH)
    except OSError:
        _SELF_CACHE["content"] = None
        _SELF_CACHE["mtime"] = -1
        return None
    if st.st_mtime != _SELF_CACHE.get("mtime"):
        try:
            with open(_SELF_PATH, encoding="utf-8") as f:
                _SELF_CACHE["content"] = f.read()
            _SELF_CACHE["mtime"] = st.st_mtime
        except OSError:
            _SELF_CACHE["content"] = None
            _SELF_CACHE["mtime"] = -1
            return None
    return _SELF_CACHE["content"]


def _extract_selfmap_l0() -> str | None:
    """提取 SELF.md 顶部 [SELF] 代码块原文（逐字节，含 [SELF] 前缀）。

    同步锁：本函数返回值是唯一常驻注入源，测试断言与母文档逐字节一致。
    块不存在时返回 None（静默降级，不注入也不炸）。
    """
    text = _load_selfmap()
    if not text:
        return None
    m = _re.search(r"```\n(\[SELF\].*?)\n```", text, _re.S)
    if not m:
        return None
    return m.group(1)


_WEEKDAYS_CN = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")


def _build_now_anchor() -> str:
    """票 TICKET-P1 + 票 COST-2：生成 [NOW] 日期时间锚点（≤60 字符）。

    格式：`[NOW] 2026-08-16 18时 周六 (Asia/Shanghai)`。
    每轮组装时调用（build_messages 内），取当前时间；优先 Asia/Shanghai 时区，
    系统无 tzdata 时回退本地时间（ZoneInfo 不可用不炸）。超长截断为无星期几格式。
    全模式（普通/auto/office）无差别注入——日期时间是无模式的基础信息。

    票 COST-2（前缀缓存稳定化）：精度从分钟级降为小时级——分钟级锚点每分钟变一次，
    锚点之后的全部 prompt tokens 缓存作废（实测命中率仅 3.4%）；小时级对
    日期/星期/时段类问题零影响，确需精确到分钟的问题走 get_current_time 工具。
    """
    try:
        from zoneinfo import ZoneInfo
        now = _datetime.now(ZoneInfo("Asia/Shanghai"))
    except Exception:
        now = _datetime.now()
    anchor = (
        f"[NOW] {now:%Y-%m-%d} {now.hour}时 "
        f"{_WEEKDAYS_CN[now.weekday()]} (Asia/Shanghai)"
    )
    if len(anchor) > 60:
        anchor = f"[NOW] {now:%Y-%m-%d} {now.hour}时 (Asia/Shanghai)"
    return anchor


def _extract_self_chapter(title_marker: str) -> str | None:
    """提取 SELF.md 指定章全文（## <title_marker> 起到下一个 ## 或文末）。

    用于 G1-2 章节触发展开：命中关键词才注入该章（L1 层，非常驻）。
    """
    text = _load_selfmap()
    if not text:
        return None
    pat = _re.compile(rf"##\s+{_re.escape(title_marker)}.*?(?=\n##\s|\Z)", _re.S)
    m = pat.search(text)
    if not m:
        return None
    return m.group(0).strip()


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


# ── 票 GOV-1：纪律注入（GUI-LESSONS + 工作流纪律，场景触发）──
# 场景：施工类回合注入施工纪律（L1-L10 + 六步工作流），收工类回合注入收工纪律
# （L8/L11/L12 + git diff 逐 hunk 自审）；票 DIAG-1：调试类回合注入调试纪律
# （先复现/先取证/假设验证/定位陈述/改后验证）；无触发零注入（对照组铁律）。
# 预算：≤ _DISCIPLINE_BUDGET_CHARS 字符（≈800 tokens，中文按 2 chars/token 保守折算），
# 超限逐条截断压缩；注入长度计入 prompt.budget 事件 discipline 段。
_GUI_LESSONS_PATH = _os.path.join(
    _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
    "docs", "GUI-LESSONS.md")
_GUI_LESSONS_CACHE: dict = {"mtime": -1, "content": None}
_DISCIPLINE_BUDGET_CHARS = 1600  # ≈800 tokens 预算上限（中文 2 chars/token 保守折算）
_DISCIPLINE_LINE_MAX = 120       # 压缩时单行上限

# 施工场景固定工作流（硬纪律，不依赖 lessons 文件存在）
_WORKFLOW_DISCIPLINE = (
    "【施工工作流纪律】（票 GOV-1 内化，不靠人盯）多步施工任务按此流程走：\n"
    "1. 先建台账：task_ledger create，每项当场带 verify（怎么算做完）与 evidence（完成证据）\n"
    "2. 读码定位：先 read_local_file 读目标文件再动手，禁止凭记忆猜\n"
    "3. 施工：edit_file 精确替换；一次可并行多个不冲突编辑\n"
    "4. 专项测试：先跑本票对应测试文件确认通过\n"
    "5. 全量回归：run_tests 确认零破坏\n"
    "6. 五查汇报：改动文件+行数 / 测试原话 / md5 / git 状态 / 风险，缺一项终审打回"
)

# 收工自审 + 汇报纪律（票 GOV-1 ②：收工自审固化）
_WRAPUP_DISCIPLINE = (
    "【收工自审纪律】（票 GOV-1 内化）：声明完工前必须：\n"
    "1. git diff 逐 hunk 自审一遍（实证：F12 自审自抓 4 个 bug），不审不算完\n"
    "2. 自审发现的问题先修再汇报，不许带着已知 bug 收工\n"
    "3. 汇报数字必须可复现：贴本地实跑原话输出，跑不动就如实说跑不动（L8）\n"
    "4. 收工汇报正文给人看：分条人话摘要 + 测试数字一行 + 风险 + 下一步；\n"
    "   git 实况 / md5 / 测试原始输出落盘 library 完成报告或票据附录，正文不糊原始输出（L12）"
)

# 调试纪律（票 DIAG-1 ③：说不清的 bug 五步排查，≤1200 字符）
# 2026-08-16 实证三起本可避免的事故：幻影 render()（假设函数存在未 grep）、
# 药丸恒 0%（双重剥壳未逐环取证）、Plugin 空白（初始化链静默中断）。
_DEBUG_DISCIPLINE = (
    "【调试纪律】（票 DIAG-1 内化，说不清的 bug 按此排查，先取证后动手）：\n"
    "1. 先复现：没亲眼看到症状不许动手。前端问题用 Playwright CDP 连真实实例\n"
    "   （scripts/e2e_gui_f14_verify.py 等现成探针可参考）；后端问题先读\n"
    "   data/logs/bobo.log 末尾 + data/logs/events.jsonl 尾部 + stack_dump.log\n"
    "2. 先取证：动手前必须拿到至少一条硬证据（报错原文/日志行/事件记录/状态快照），写进台账\n"
    "3. 假设必须验证：调用任何函数/字段/文件前，先 grep 确认它真实存在（L14：桩里禁止虚构全局）\n"
    "4. 定位陈述：改代码前必须能说出『根因是 X 文件 Y 行，因为证据 Z』——\n"
    "   说不出就继续查，不许猜了再改\n"
    "5. 改后验证：症状在真实环境消失才算完，测试绿不算完（L13/L14）"
)

# 场景裁剪表：场景 → 保留的 L 块号（与 GUI-LESSONS.md 同源，Kimi 更新后自动跟进）
_SCENE_LESSONS = {
    "work":   ("L1", "L2", "L3", "L4", "L5", "L6", "L7", "L8", "L9", "L10"),
    "wrapup": ("L8", "L11", "L12", "L13"),
    # 票 DIAG-1：调试场景关联 L2（真实可跑≠模拟通过）与 L14（桩里禁止虚构全局）
    "debug":  ("L2", "L14"),
}

# 场景触发关键词（命中 user_input 或最近 3 轮 history；收工优先，调试次之）
_WRAPUP_KEYWORDS = ("收工", "汇报", "总结", "销账", "五查", "终审", "收尾")
# 票 DIAG-1：调试类信号——症状描述/定位诉求/报错字样。与 work 关键词不重叠
# （"bug" 仍归 work），命中即注入调试纪律（场景优先级 wrapup > debug > work）。
_DEBUG_KEYWORDS = (
    "报错", "不对", "打不开", "坏了", "崩了", "崩溃", "白屏", "无响应",
    "卡住", "不工作", "为什么不", "怎么办", "定位", "排查", "复现", "取证",
    "error", "exception", "traceback", "crash", "failed", "not working",
)
_WORK_KEYWORDS = ("施工", "建账", "改码", "修 bug", "bug", "实现", "开发", "测试", "票 ")


def _load_gui_lessons() -> str | None:
    """模块级缓存读 docs/GUI-LESSONS.md（mtime 变化才重读），缺失/不可读返回 None。

    与 _load_guidance 同模式：每轮只做一次 _os.stat，文件不变不重复读盘。
    """
    try:
        st = _os.stat(_GUI_LESSONS_PATH)
    except OSError:
        _GUI_LESSONS_CACHE["content"] = None
        _GUI_LESSONS_CACHE["mtime"] = -1
        return None
    if st.st_mtime != _GUI_LESSONS_CACHE.get("mtime"):
        try:
            with open(_GUI_LESSONS_PATH, encoding="utf-8") as f:
                _GUI_LESSONS_CACHE["content"] = f.read()
            _GUI_LESSONS_CACHE["mtime"] = st.st_mtime
        except OSError:
            _GUI_LESSONS_CACHE["content"] = None
            _GUI_LESSONS_CACHE["mtime"] = -1
            return None
    return _GUI_LESSONS_CACHE["content"]


def _extract_lessons_sections(text: str) -> dict:
    """按 '### Lx. 标题' 切块，返回 {L号: 块文本}。"""
    sections: dict = {}
    current = None
    buf: list = []
    for line in text.splitlines():
        m = _re.match(r"^###\s+(L\d+)\.", line)
        if m:
            if current and buf:
                sections[current] = "\n".join(buf)
            current = m.group(1)
            buf = [line]
        elif current:
            buf.append(line)
    if current and buf:
        sections[current] = "\n".join(buf)
    return sections


def _detect_round_scene(user_input: str, history: list) -> str:
    """按输入与最近 3 轮 history 判定回合场景：'work' | 'wrapup' | 'debug' | ''。

    收工关键词优先（收工回合也是施工回合的收尾）；调试次之（症状/定位信号
    优先于施工指令——遇到问题先按调试纪律排查）；无命中零注入（对照组铁律）。
    """
    haystack = " ".join(
        str(m.get("content", "")) for m in (history or [])[-3:]
    ) + " " + (user_input or "")
    haystack_l = haystack.lower()
    if any(k in haystack_l for k in _WRAPUP_KEYWORDS):
        return "wrapup"
    if any(k in haystack_l for k in _DEBUG_KEYWORDS):
        return "debug"
    if any(k in haystack_l for k in _WORK_KEYWORDS):
        return "work"
    return ""


def _compress_discipline(text: str, max_chars: int) -> tuple:
    """超预算压缩：先逐行截断，仍超则整体截断并标注。返回 (文本, 是否截断)。"""
    if len(text) <= max_chars:
        return text, False
    lines = [
        line if len(line) <= _DISCIPLINE_LINE_MAX
        else line[:_DISCIPLINE_LINE_MAX - 1] + "…"
        for line in text.splitlines()
    ]
    out = "\n".join(lines)
    if len(out) > max_chars:
        out = out[: max_chars - 12] + "\n…（纪律已压缩）"
    return out, True


def _summarize_lesson_block(block: str) -> str:
    """L 块摘要：保留标题行与 '规则：' 行（信息密度优先），丢弃事故描述/回归闸行。

    预算内装下更多规则：规则句是教训的结论，事故背景是佐证，超预算时先丢佐证。
    """
    keep = [
        line for line in block.splitlines()
        if line.startswith("###") or "规则：" in line
    ]
    return "\n".join(keep)


def _build_discipline_text(scene: str, lessons_text: str | None) -> tuple:
    """按场景组装纪律段：固定纪律段 + lessons 对应 L 块摘要（同源），预算内压缩。

    返回 (文本, 是否截断)。lessons 缺失时仅固定纪律段（静默降级不炸）。
    """
    parts: list = []
    if scene == "debug":
        parts.append(_DEBUG_DISCIPLINE)
    else:
        parts.append(_WORKFLOW_DISCIPLINE if scene == "work" else _WRAPUP_DISCIPLINE)
    if lessons_text:
        sections = _extract_lessons_sections(lessons_text)
        for lnum in _SCENE_LESSONS.get(scene, ()):
            block = sections.get(lnum)
            if block:
                parts.append(_summarize_lesson_block(block))
    text = "\n\n".join(parts)
    return _compress_discipline(text, _DISCIPLINE_BUDGET_CHARS)


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

        # ── 票 COST-2：动态段尾部收集器 ──
        # 前缀稳定化：所有"每轮组装内容可能变化"的注入段统一收集到这里，
        # 在 8.5 段插到最后一个 user 消息（本轮用户输入）之前；头部只留
        # 逐字节静态内容（system_prompt + L0 + 自查协议 + GUIDANCE + 用户资料
        # + 自定义 API），前缀随轮次稳定 → DeepSeek 前缀缓存生效。
        # 期望注入顺序（前→后）：proactive 连接 → 记忆 → 笔记指针 → 改动日志
        # → 已读文件 → 纪律 → SELF 章节 → NOW 锚点。
        _tail_blocks = []  # list[(name, content)]

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
            "office": {"chars": 0},
            "selfmap": {"chars": 0},
            "now": {"chars": 0},
            "selfmap_chapters": {"chars": 0, "chapters": []},
        }

        # ── 票 G1-1（v2 母子结构）：L0 常驻注入 = SELF.md 顶部 [SELF] 块原文 ──
        # 逐字节同源（不许改写/摘要）；缺失静默降级不注入。常驻无模式条件。
        # 同步锁：注入文本 == _extract_selfmap_l0() == 母文档顶部块（测试断言）。
        _l0 = _extract_selfmap_l0()
        if _l0:
            messages.insert(1, {
                "role": "system",
                "content": _l0,
            })
            budget_stats["selfmap"] = {"chars": len(_l0)}

        # ── 票 TICKET-PROFILE-1：USER.md 用户模型画像（行为影响型，L0 之后、自查协议之前）──
        # 位置：system_prompt(0) → SELF L0(1) → USER.md(2) → 自查协议(3)。
        # 与 L0 同源读取模式：mtime 缓存，缺失静默跳过（不注入也不炸）。
        # 不计入 prompt.budget sections（LN-4 验收口径 sections 精确九段，见 test_note_pointer）。
        _user_profile = _load_user_profile()
        if _user_profile:
            messages.insert(2 if _l0 else 1, {
                "role": "system",
                "content": _user_profile,
            })

        # ── 票 TICKET-P1 + 票 COST-2：日期时间锚点 ──
        # 原位置：紧跟 L0 之后 insert(2) 注入。COST-2 前缀稳定化后移——
        # 分钟级锚点在头部每轮必变，锚点之后数万 tokens 缓存全作废（实测命中率 3.4%）；
        # 现改为尾部"最新用户消息之前"注入（见下方第 9.5 段），前缀恢复稳定。
        # 引导行：日期/星期/时段类问题直接引用锚点禁调工具；精确到分钟走工具。

        # ── 票 TICKET-E3b：GUIDANCE 预付层导航（紧跟自查协议之后，缺失静默）──
        # 票 G1-1：L0 selfmap 已插在自查协议之前（index 1），故自查协议在 index 2。
        # 票 COST-2：NOW 锚点已后移至尾部（不再占 index 2），GUIDANCE 用 insert(3)
        # 紧跟自查协议之后（E3b "紧跟自查协议之后"语义不变）。
        # 票 TICKET-PROFILE-1：USER.md 注入后自查协议后移一位（L0=1, USER=2, 自查=3），
        # GUIDANCE 相应后移一位（仍紧跟自查协议之后，E3b 语义不变）。
        _guidance = _load_guidance()
        if _guidance:
            messages.insert(4 if _user_profile else 3, {
                "role": "system",
                "content": _guidance,
            })
            budget_stats["guidance"] = {"chars": len(_guidance)}

        # ── 票 GOV-1：纪律注入（GUI-LESSONS + 工作流纪律，场景触发）──
        # 施工类回合 → 施工纪律（六步工作流 + L1-L10）；收工类回合 → 收工自审
        # + 汇报纪律（L8/L11/L12 + git diff 逐 hunk 自审）；无触发零注入（对照组铁律）。
        # 预算 ≤1600 字符（≈800 tokens），超限压缩；记账走事件顶层 discipline 字段
        # （不进 sections：LN-4 验收口径 sections 精确九段，且防 payload 超限被丢弃）。
        _discipline_stats = None
        _discipline_scene = _detect_round_scene(user_input, engine.history)
        if _discipline_scene:
            _disc_text, _disc_truncated = _build_discipline_text(
                _discipline_scene, _load_gui_lessons())
            if _disc_text:
                # 票 COST-2：纪律段从头部 insert(5) 后移至尾部动态区
                # （场景触发、每轮内容可能变 → 头部会破坏前缀缓存）
                _tail_blocks.append(("discipline", _disc_text))
                _discipline_stats = {
                    "chars": len(_disc_text),
                    "scene": _discipline_scene,
                    "truncated": _disc_truncated,
                }

        # ── 票 G1-2：章节触发展开（L1，SELF.md §2 架构/§4 边界/§5 自救）──
        # 关键词命中 user_input 或最近 4 轮 history 才注入该章全文；无触发零注入。
        # 对照组铁律：不命中关键词绝不展开（与 O4-2 同款零注入原则）。
        _self_haystack = " ".join(
            str(m.get("content", "")) for m in engine.history[-4:]
        ) + " " + (user_input or "")
        _self_haystack_l = _self_haystack.lower()
        _selfmap_chapters = []
        _selfmap_chapter_texts = {}
        for _ckey, _ccfg in _SELF_CHAPTER_TRIGGERS.items():
            if any(kw in _self_haystack_l for kw in _ccfg["keywords"]):
                _chapter = _extract_self_chapter(_ccfg["title"])
                if _chapter:
                    _selfmap_chapter_texts[_ckey] = _chapter
                    # 票 COST-2：SELF 章节从头部 insert(5) 后移至尾部动态区
                    # （触发基于 history[-4:]/user_input，每轮内容可能变）
                    _tail_blocks.append((
                        f"selfmap_{_ckey}",
                        f"[SELF {_ccfg['title']}]\n{_chapter}",
                    ))
                    _selfmap_chapters.append(_ckey)
        if _selfmap_chapters:
            budget_stats["selfmap_chapters"] = {
                "chars": sum(len(t) for t in _selfmap_chapter_texts.values()),
                "chapters": _selfmap_chapters,
            }

        # ── 票 O4-2：OFFICE MODE 上下文告示（office_on 才注入；普通模式零注入）──
        # 对照组铁律：office off / 普通模式连字段都不读（不 import 读取器）——因此
        # 先只查 engine.sid 是否存在，延迟 import 读取器仅在 office 会话尝试。
        # 读取失败静默降级（office_on=False → 零注入），绝不影响工具链。
        _office_on = False
        _office_sid = session_id or getattr(engine, "sid", "")
        if _office_sid:
            try:
                from bobo_tui_gateway.server import get_office_on as _get_office_on
                _office_on = bool(_get_office_on(_office_sid))
            except Exception:
                _office_on = False
        if _office_on:
            _office_notice = (
                "【OFFICE MODE】当前处于 OFFICE 模式（会话级，owner 用 /office 显式开启）。"
                "你是老板（owner 的直接对话方），不是员工。职责：听懂 owner 的编制需求"
                "（几人/什么角色）→ 用 office_manager 搭建办公室（launch/status/teardown）→ "
                "relay 派工 → 收五查汇报 → 呈交 owner 终审。"
                "边界：普通对话/笔记考古不是本模式职责；owner 未给任务时先问清需求，不自行翻旧账。"
            )
            messages.insert(1, {
                "role": "system",
                "content": _office_notice,
            })
            budget_stats["office"] = {"chars": len(_office_notice)}

        # ── 1. pending diff（票 COST-2：一次性段 → 后移尾部动态区）──
        # 注入后清空（原语义：diff 只在首轮出现一次）；若留在头部 insert(1)，
        # 首轮有 diff 段、次轮无 → 前缀在 index 1 分叉，缓存全废（实弹实证：
        # 修复前 R1 命中 2.8% 仅 system_prompt 1152 tokens；R2→R3 前缀稳定后
        # 命中 99.8%）。后移后头部逐字节稳定。
        if engine._pending_diff:
            diff_preview = engine._pending_diff[:4000]
            _tail_blocks.append((
                "pending_diff",
                f"[代码变更 — 请审查以下 diff 是否有 bug、安全风险或性能问题:]\n"
                f"{diff_preview}\n\n"
                f"审查要点:\n"
                f"1. 逻辑错误（拼写错误、条件反转、off-by-one）\n"
                f"2. 安全风险（注入、硬编码密钥、权限问题）\n"
                f"3. 性能问题（不必要的循环、重复计算、N+1 查询）\n"
                f"4. 代码风格（与项目其他部分不一致的命名/格式）\n\n"
                f"发现问题后如实报告，使用 review_diff 工具可查看完整 diff。"
            ))
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
            # 票 COST-2：记忆段从头部 insert(1) 后移至尾部动态区（signal 随
            # decay/touch 变化 → 内容可能逐轮变，留头部会破坏前缀缓存）
            if not engine._compressing:
                pool = get_prompt_pool()
                mem_floor = pool.floor("memory")
                mem_ceiling = pool.ceiling("memory")
                mem_text, mem_stats = format_memory_by_signal(
                    max_chars=mem_ceiling, min_chars=min(mem_floor, mem_ceiling))
                if mem_text:
                    _tail_blocks.append(("memory", mem_text))
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
                # 票 COST-2：笔记指针从头部 insert(1) 后移至尾部动态区
                # （路径 2 按 user_input 主题词命中 → 每轮可能变）
                _tail_blocks.append(("note_pointers", combined))
                merged_stats = {**pointer_stats}
                merged_stats["session_notes"] = ledger_stats.get("session_notes", 0)
                budget_stats["note_pointers"] = merged_stats
        except Exception as e:
            logger.debug("注入笔记指针失败: %s", e)

        # ── 6. 改动日志（票 COST-2：会话累计增长 → 后移至尾部动态区）──
        if engine.tracker._change_log:
            items = engine.tracker._change_log[-5:]
            lines = ["[本会话的改动记录]:", ""]
            for it in items:
                lines.append(f"  {it['desc']}")
            if len(engine.tracker._change_log) > 5:
                lines.append(f"  ...（共 {len(engine.tracker._change_log)} 次改动）")
            _tail_blocks.append(("change_log", "\n".join(lines)))

        # ── 7. 已读文件（票 COST-2：会话累计增长 → 后移至尾部动态区）──
        if engine.tracker._read_files:
            items = list(engine.tracker._read_files.items())[-3:]
            lines = ["[最近读过的文件]:", ""]
            for fpath, preview in items:
                short = preview[:120].replace('\n', ' ').strip()
                lines.append(f"  {fpath}: {short}...")
            _tail_blocks.append(("read_files", "\n".join(lines)))

        # ── 8. 主动连接 ──
        messages = engine.proactive.inject_context(messages)

        # ── 8.5 票 TICKET-P1 + COST-2：动态段统一尾部注入（紧跟最新用户消息之前）──
        # COST-2 前缀稳定化：NOW 锚点（原头部 index 2，分钟级每轮必变）+ 全部动态段
        # （proactive 知识连接、记忆、笔记指针、改动日志、已读文件、纪律、SELF 章节）
        # 统一插到最后一个 user 消息（本轮用户输入）之前；头部只留逐字节静态内容
        # → 前缀随轮次稳定 → DeepSeek 前缀缓存生效（受控实验：固定前缀命中 98%+）。
        # 模型可见性不变（全部仍在 messages 内、用户消息前）。预算记账保留。
        # 1) proactive 知识连接搬回尾部：full 模式 inject_context 把连接 insert(0)，
        #    按轮次主题检索（_extract_topic 取最近 user 消息）→ 内容逐轮变，
        #    位于前缀第一位最致命。先识别其标志性前缀并 pop 收集（必须先 pop
        #    再算 _last_user_idx，否则 pop 后 index 前移导致锚点错位）。
        #    （subtle 模式追加到 system prompt 内部，无法搬移；当前配置为 full。）
        _PROACTIVE_MARK = "以下是你之前的知识记录，可能对当前对话有帮助："
        if (messages and messages[0].get("role") == "system"
                and str(messages[0].get("content", "")).startswith(_PROACTIVE_MARK)):
            _pa = messages.pop(0)
            _tail_blocks.append(("proactive", _pa["content"]))

        # 2) NOW 锚点（期望顺序最末；随冻结段统一置前，跨小时自动重建）
        _now_anchor = _build_now_anchor()
        if _now_anchor:
            _now_block = (
                _now_anchor + "\n"
                "回答日期/星期/时间类问题直接引用上方 [NOW] 锚点，禁止为此调用工具；"
                "确需精确到分钟的时间问题可调用 get_current_time 工具。"
            )
            _tail_blocks.append(("now", _now_block))
            budget_stats["now"] = {"chars": len(_now_block)}

        # 票 COST-3：工作锚点（原 TICKET-020 压缩时 insert(0) 进 history 头部 →
        # 长会话前缀杀手，位于 system 之后第一条，含 current_user_input 每轮必变
        # → 其后的历史 tokens 缓存全废）改为每轮随 COST-2 动态块注入（附加到
        # 本轮 user content 前部，历史区逐字节稳定）。压缩豁免语义保留：锚点
        # 内容（当前任务/已写文件/台账）全部来自会话级属性，压缩不丢，每轮
        # 重建即最新；压缩路径仅刷新 self._work_anchor，不再触碰 history。
        try:
            _build_wa = getattr(engine, "_build_work_anchor", None)
            if callable(_build_wa):
                _wa = _build_wa()
                if _wa and _wa.get("content"):
                    _tail_blocks.append(("work_anchor", _wa["content"]))
        except Exception:
            logger.debug("工作锚点注入失败（静默降级）", exc_info=True)

        # ── 票 DESK-P1：会话项目根（project_root 尾部动态段，COST-3 之后顺延）──
        # 有项目时注入"当前项目根"提示（文件操作/终端命令基准目录）；无项目时
        # 零注入（一字节都不许多——缓存前缀稳定红线）。engine.project_root 由
        # gateway 经 engine_adapter 注入（session["project_root"]），None=默认现状。
        try:
            _pr = getattr(engine, "project_root", None)
            if _pr:
                _tail_blocks.append(("project_root",
                                     f"当前项目根：{_pr}——所有文件操作/终端命令基于该目录"))
        except Exception:
            logger.debug("project_root 注入失败（静默降级）", exc_info=True)

        # ── 票 GUI-F24：会话级 Roles/Rules（request 尾部动态段，project_root 之后）──
        # 有 request 时注入"会话请求"引导（角色/规则分行）；无 request 时零注入
        # （一字节都不许多——缓存前缀稳定红线）。engine.request 由 gateway 经
        # engine_adapter 注入（session["request"]），None=默认现状。
        try:
            _req = getattr(engine, "request", None)
            if _req and (_req.get("roles") or _req.get("rules")):
                _req_parts = []
                if _req.get("roles"):
                    _req_parts.append("角色：" + str(_req.get("roles")))
                if _req.get("rules"):
                    _req_parts.append("规则：" + str(_req.get("rules")))
                _req_text = "【会话请求】\n" + "\n".join(_req_parts)
                _tail_blocks.append(("request", _req_text))
                # TICKET-GUI-F28：request 预算记账（prompt.budget 事件可观测注入，
                # 验证 request 是否真正进入上下文——F24 漏记）
                budget_stats["request"] = {"chars": len(_req_text)}
        except Exception:
            logger.debug("request 注入失败（静默降级）", exc_info=True)

        # 3a) 技能标准收集（票 TICKET-E3b：未命中清单已删，仅命中才注入）
        # 票 COST-2：必须在本段统一注入之前收集；原第 9 段（注入后）append
        # 到 messages 末尾，位置逐轮漂移导致前缀错位（详见第 9 段注释）。
        skill_stds = engine.skill_loader.load_standards()
        if skill_stds:
            _skill_combined = "\n\n---\n\n".join(skill_stds)
            _tail_blocks.append((
                "skill",
                "## 项目标准 — 以下规则优先级高于一切，违反即不合格\n\n"
                + _skill_combined,
            ))
            budget_stats["skills"] = {"chars": len(_skill_combined),
                                      "truncated": False}

        # 3) 统一注入 + 票 COST-2：动态块附加到当前轮 user 消息内容前部
        #    （前缀稳定化终极方案）。实弹暴露：动态段若以 system 消息插在 user
        #    消息之前，锚点逐轮漂移（R1 的 T 块在 R1u 前、R2 的 T 块在 R2u 前）
        #    + 内容逐轮变（proactive 主题/记忆 touch/pending_diff 首轮有次轮无）
        #    → R1 与 R2 公共前缀只有头部（实测命中率 5.3%）。
        #    修复：所有动态块（proactive/记忆/笔记指针/纪律/SELF 章节/change_log/
        #    read_files/pending_diff/NOW）按期望顺序拼接，附加到 messages 最后一
        #    个 user 消息（本轮输入）的 content 前部 —— 位于消息序列末尾，历史
        #    消息区逐字节稳定 → R2 前缀 == R1 全部（命中率 ~100%），且每轮内容
        #    照常刷新（纪律场景/记忆 touch/NOW 小时级都实时，无冻结锁死）。
        #    注：原实现"附加到最后一个 user 写回 history"（共享引用 mutate）——
        #    票 COST-6 发现该写回制造"双 user 夹工具轮"触发结构（400），
        #    已改方案 B：动态块注入为尾部 system 消息（不写回 history），
        #    前缀稳定论证见下方 8.5 段实现注释。
        _TAIL_ORDER = {"proactive": 0, "memory": 1, "note_pointers": 2,
                       "change_log": 3, "read_files": 4, "pending_diff": 5,
                       "discipline": 6,
                       "selfmap_arch": 7, "selfmap_boundary": 8, "selfmap_rescue": 9,
                       "skill": 10, "now": 11, "work_anchor": 12,
                       "project_root": 13,  # 票 DESK-P1：COST-3 之后顺延
                       "request": 14}  # 票 GUI-F24：project_root 之后顺延
        if _tail_blocks:
            _ordered = sorted(
                _tail_blocks, key=lambda b: _TAIL_ORDER.get(b[0], 99))
            _dyn_text = "\n\n".join(c for _n, c in _ordered)
            _DYN_MARK = "【COST-2 动态块】"
            # 票 COST-6（方案 B 定案）：动态块注入为"尾部 system"消息——
            # 不写回 history、不占 user 角色。
            # 消除"双 user 夹工具轮"触发结构（400 根因：动态块写回使 history
            # 出现两个 user 消息（user#0 与 user#104 均含动态块）中间夹大量
            # 工具轮 → DeepSeek 要求其中 assistant 的 reasoning_content 回传
            # → 缺失即 400，REASONING-ECHO 修回传不修结构，故复现）。
            # 前缀稳定论证：history 从此不被动态块污染（纯用户输入逐字节
            # 不变），跨轮公共前缀 = [system + 历史区]；动态块在消息序列
            # 末尾逐轮变化，不影响前缀 → 缓存命中率保持（改前基线
            # e2e_cost2_probe R3=99.9%，改后同探针对比，见完成报告）。
            # 注：COST-2 实测 5.3% 塌方的是"system 插在 user 之前"（锚点
            # 逐轮漂移 + 头部变化）；本方案固定尾部位置，不漂移。
            messages.append({
                "role": "system",
                "content": _DYN_MARK + "\n" + _dyn_text,
            })

        # ── 9. 技能标准（票 TICKET-E3b：未命中清单已删，仅命中才注入）──
        # 票 COST-2：收集已前移至 8.5 段 3a（必须在统一注入之前）；此处仅
        # 记录原语义——原实现 append 到 messages 末尾（user 之后），实弹暴露：
        # R1=[H, 动态块, 技能] / R2=[H, 动态块, A1, 动态块2, 技能]——技能段
        # 位置逐轮漂移（夹在历史区之间），R2 前缀与 R1 在技能段错位分叉，
        # 命中率塌回头部（实测 5.3%）。修复：技能并入尾部动态块（随本轮
        # user 消息附加、写回 history 后逐字节固定），跨轮稳定。

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
                # 票 GOV-1：纪律记账在事件顶层（不进 sections——LN-4 九段口径）；
                # 仅实际注入时带 discipline 字段，未注入不写空壳（payload 最小化）
                **({"discipline": _discipline_stats} if _discipline_stats else {}),
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

        # ── 票 REASONING-ECHO：thinking → reasoning_content 回传（方案 B）──
        # DeepSeek thinking 模式铁律：两个 user 消息之间若夹工具轮，中间
        # assistant 的 reasoning_content 必须随上下文回传，否则 HTTP 400
        # （"reasoning_content in the thinking mode must be passed back"）。
        # 引擎落盘字段是 thinking（GUI-F8 折叠框内部名，engine.py:1646），
        # 发送侧必须转回 DeepSeek 认识的 reasoning_content。
        # 铁律：只改发送副本——messages 内层 dict 与 engine.history 共享引用
        # （见上方 COST-2 注释），补字段必须浅拷贝 dict，绝不 mutate 原 dict
        # （否则存档/恢复带 reasoning_content，GUI-F8 折叠框读取路径要复查）。
        # 判断依据是"工具轮"而非"有无思考"：带 tool_calls 的 assistant 一律补
        # （有 thinking 用 thinking，压缩摘要无 thinking 则补空串——DeepSeek
        # 是否接受空串由实弹定案，见 TICKET-REASONING-ECHO 报告）；
        # 纯文本 assistant（编辑冲突注入等，无 tool_calls）不补。
        _echoed = []
        for _m in messages:
            if isinstance(_m, dict) and _m.get("role") == "assistant" \
                    and (_m.get("tool_calls") or _m.get("thinking")):
                _m2 = dict(_m)
                _m2["reasoning_content"] = _m.get("thinking") or ""
                _echoed.append(_m2)
            else:
                _echoed.append(_m)
        messages = _echoed

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
