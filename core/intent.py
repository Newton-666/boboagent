# ── 票 TICKET-COMPUTER-USE-INTENT（COST-3 特批标记）：computer use 意图判断 ──
# 核心：用户请求 → GOAL/TARGET/MEANS 三要素约束框架（LLM 判断 + 收敛）。
# 依据 docs/DISCUSSION-SELF-EVOLVING.md 第 36 节：意图是决策的根 +
# "给 LLM 足够好的引导让判断收敛"，防"把手段当目的"（谷歌被当搜索目标）。
# 复用 signal_detector 的"LLM + 约束框架"方法论：thinking_disabled 冷调用，
# 静默降级（失败/无 GOAL → 返回 None，绝不影响主流程）。

import json
import logging

logger = logging.getLogger(__name__)

_INTENT_MAX_TOKENS = 260

_INTENT_PROMPT = (
    "你是意图解析器。把用户请求解析成 GOAL/TARGET/MEANS 三要素，只输出一个 JSON 对象。\n"
    "约束框架（必须遵守）：\n"
    "1. GOAL（最终目标）：用户真正要得到什么。必须能一句话复述。GOAL 永不丢——"
    "无论换成什么手段/工具/系统，GOAL 都不变。\n"
    "2. TARGET（落点系统）：用户指定在哪个 APP/系统上操作。"
    "不能缩水成'文件/文本抽象层'——用户说在浏览器/Pages/谷歌，落点就是那个系统，"
    "不能降级成'写个文件'或'文本处理'。\n"
    "3. MEANS（手段，数组）：达成 GOAL 可用的工具/路径。可多个，可变。\n\n"
    "关键约束（防误判）：\n"
    "- MEANS/TARGET 区分：用户提到的工具是'手段'还是'目的'？"
    "例：'用谷歌搜DeepSeek新闻'→谷歌=手段（搜索工具），新闻=目的；绝不能把'谷歌'当成搜索目标。\n"
    "- 若 GOAL 无法一句话复述 / 请求含糊 → 输出 {\"goal\": \"\", \"target\": \"\", \"means\": [], \"need_clarify\": true}。\n"
    "- 若请求与打开APP/搜索/操作系统无关（纯聊天）→ {\"goal\": \"\", \"target\": \"\", \"means\": [], \"need_clarify\": false}。\n\n"
    "输出格式（严格 JSON）：\n"
    '{"goal": "一句话目标,不可变", "target": "落点系统(用户指定的那个)", "means": ["手段1","手段2"], "need_clarify": false}'
)


_INTENT_TRIGGERS = (
    "打开", "搜", "谷歌", "google", "safari", "chrome", "浏览器", "网页",
    "查", "找", "写", "粘贴", "登录", "下载", "启动", "运行", "进",
    "帮", "帮我", "去", "发", "创建", "DeepSeek", "news", "新闻", "周报",
)


def _intent_gate(text: str) -> bool:
    """零成本冷门卫（与 signal_detector.keyword_gate 同范式）：
    只在疑似"目标操作/打开系统/搜索"类请求才触发 LLM 判断，其余零调用。
    ——保证不占用 mock llm_caller 调用序列，也控制真实场景 LLM 成本。"""
    if not text or not isinstance(text, str):
        return False
    return any(k in text for k in _INTENT_TRIGGERS)


def _parse_json(content: str) -> dict | None:
    """容错剥 JSON（``` 围栏 / 前后杂文）。失败返回 None。"""
    if not content:
        return None
    s = content.strip()
    if s.startswith("```"):
        first_nl = s.find("\n")
        last_marker = s.rfind("```")
        if first_nl != -1 and last_marker > first_nl:
            s = s[first_nl + 1:last_marker].strip()
    try:
        obj = json.loads(s)
    except ValueError:
        start = s.find("{")
        end = s.rfind("}")
        if start == -1 or end <= start:
            return None
        try:
            obj = json.loads(s[start:end + 1])
        except ValueError:
            return None
    return obj if isinstance(obj, dict) else None


def parse_intent(user_input: str, llm_caller) -> dict | None:
    """用户请求 → {goal, target, means, need_clarify} 三要素。

    LLM 判断（thinking_disabled 冷调用）+ 约束框架（INTENT_PROMPT 缰绳）。
    GOAL 为空/不可复述/解析失败 → 返回 None（无有效意图锚点，调用方不注入）。
    失败静默丢弃（绝不影响主流程）——与 signal_detector._llm_judge 同语义。
    """
    if not user_input or not str(user_input).strip():
        return None
    if not _intent_gate(str(user_input)):
        return None  # 零成本冷门卫：非目标操作类请求，不调 LLM，不消耗调用序列
    try:
        resp = llm_caller(
            [
                {"role": "system", "content": _INTENT_PROMPT},
                {"role": "user", "content": f"用户请求：{user_input}"},
            ],
            use_tools=False,
            max_tokens=_INTENT_MAX_TOKENS,
            thinking_disabled=True,  # 【COST-3】冷调用关 thinking（与 signal_detector 同例）
        )
    except Exception:
        logger.warning("intent: LLM 意图判断失败，静默丢弃", exc_info=True)
        return None
    if not isinstance(resp, dict) or resp.get("error"):
        logger.warning("intent: LLM 意图判断返回错误: %s", (resp or {}).get("error"))
        return None
    content = ""
    try:
        content = resp["choices"][0]["message"].get("content", "") or ""
    except (KeyError, IndexError, TypeError):
        return None
    obj = _parse_json(content)
    if not obj:
        return None
    goal = str(obj.get("goal", "")).strip()
    if not goal:
        return None  # 无 GOAL（需澄清/纯聊天/含糊）→ 不注入，静默
    target = str(obj.get("target", "")).strip()
    means = obj.get("means") or []
    if not isinstance(means, list):
        means = [means] if means else []
    means = [str(m).strip() for m in means if str(m).strip()]
    return {"goal": goal, "target": target, "means": means,
            "need_clarify": bool(obj.get("need_clarify", False))}


def format_intent_block(intent: dict) -> str:
    """构造注入上下文用的意图锚点段（每次工具轮可见，防手段漂移）。"""
    if not intent or not intent.get("goal"):
        return ""
    goal = intent["goal"]
    target = intent.get("target", "") or ""
    means = "、".join(intent.get("means", [])) or "未指定"
    return (
        "\n\n📌 当前任务意图锚点（GOAL/TARGET/MEANS——每次行动、换手段先回到 GOAL 判断）：\n"
        f"- GOAL：{goal}\n"
        f"- TARGET：{target}\n"
        f"- MEANS：{means}\n"
        f"》无论换什么手段/工具/系统，GOAL 永不丢：{goal}"
    )
