"""signal_detector.py — 行为信号两级检测流水线（票 TICKET-PROFILE-5）。

【COST-3 特批标记】PROFILE 系列（PROFILE-5）授权：core/ 新增模块，
desk_v4/v4b/tel + cost1a IronRules 守卫白名单已登记。

自进化闭环最后一块：bobo 主动识别"以后别用 emoji"这类行为信号并自动写入
USER.md（signal_source=auto_detect），不再依赖手动调 write_user_profile。

流水线（两级，日常回合零成本）：
  一级 关键词门卫（确定性代码）：
    检测用户消息是否命中指令词：以后/别/不要/记住/每次/我其实喜欢/我讨厌/
    不要再/请记得。不命中 → 直接跳过（零 LLM 调用）。
  二级 LLM 精判（命中回合才 +1 次调用）：
    判断"这次真的是画像修正信号吗？"；是 → 提取候选画像（一句话）→
    调 write_user_profile（模板过滤兜底，signal_source=auto_detect）；
    否（如"以后再说吧"是敷衍）→ 丢弃。

注入点：回合收尾（engine_adapter.run_engine 的 message.complete 之后），
独立 daemon 线程异步执行，不阻塞主流程、不 emit 用户可见事件（ENG-1 保持：
message.complete 后主线程零调用，本模块在子线程中运行）。
"""

import json
import logging
import re
import threading
import time

logger = logging.getLogger(__name__)

# ── 一级门卫：指令词（命中任一即进二级精判）──
_KEYWORDS = (
    "以后",
    "别",
    "不要",
    "记住",
    "每次",
    "我其实喜欢",
    "我讨厌",
    "不要再",
    "请记得",
)

# 精判 LLM 提示：判断是否真画像信号 + 提取一句话候选
_JUDGE_PROMPT = """你是用户画像信号裁判。用户对助手说了一句话，可能包含对 bobo 的画像修正指示（以后怎么做 / 不要怎么做 / 每次怎么做）。

判断：这句话是否构成画像修正信号（用户明确指示助手以后应/不应如何做，且是可执行的长期行为方式）？
- 构成 → 只输出 JSON：{"is_signal": true, "category": "preference|taboo|workflow", "candidate": "提炼成一句话，必须含模板词：偏好类含'偏好 X 方式'或'喜欢 X 方式'；禁忌类含'不要 X'或'别 X'；工作流类含'先 X 再 Y'"}
- 不构成（寒暄、敷衍、纯事实、一次性请求、提问等，如"以后再说吧"）→ 只输出 JSON：{"is_signal": false}
只输出 JSON 对象，不要任何其他文字。"""

# 精判调用参数（短调用：小上下文、少 token）
_JUDGE_MAX_TOKENS = 200


def keyword_gate(text: str) -> bool:
    """一级门卫：确定性关键词匹配。日常回合零成本（无 LLM 调用）。"""
    if not text or not isinstance(text, str):
        return False
    return any(k in text for k in _KEYWORDS)


def _parse_judge_output(content: str) -> dict | None:
    """解析精判 LLM 输出：容错剥 JSON（``` 围栏 / 前后杂文）。失败返回 None。"""
    if not content:
        return None
    s = content.strip()
    if s.startswith("```"):
        # 剥 ```json ... ``` 围栏
        first_nl = s.find("\n")
        last_marker = s.rfind("```")
        if first_nl != -1 and last_marker > first_nl:
            s = s[first_nl + 1:last_marker].strip()
    try:
        obj = json.loads(s)
    except ValueError:
        # 容错：取首个 { ... } 片段
        start = s.find("{")
        end = s.rfind("}")
        if start == -1 or end <= start:
            return None
        try:
            obj = json.loads(s[start:end + 1])
        except ValueError:
            return None
    if not isinstance(obj, dict):
        return None
    return obj


def _llm_judge(llm_caller, user_text: str) -> dict | None:
    """二级精判：LLM 判断是否真信号 + 提取候选。

    失败（异常/网络错误/输出不可解析）→ 返回 None（静默丢弃，绝不影响主流程）。
    """
    try:
        resp = llm_caller(
            [
                {"role": "system", "content": _JUDGE_PROMPT},
                {"role": "user", "content": f"用户消息：{user_text}"},
            ],
            use_tools=False,
            max_tokens=_JUDGE_MAX_TOKENS,
            # 【COST-3 特批标记】P5-400 修复：独立冷调用关 thinking（thinking_disabled）
            thinking_disabled=True,
        )
    except Exception:
        logger.warning("signal_detector: LLM 精判调用失败，静默丢弃", exc_info=True)
        return None
    if not isinstance(resp, dict) or resp.get("error"):
        logger.warning("signal_detector: LLM 精判返回错误: %s", (resp or {}).get("error"))
        return None
    content = ""
    try:
        content = resp["choices"][0]["message"].get("content", "") or ""
    except (KeyError, IndexError, TypeError):
        return None
    return _parse_judge_output(content)


def detect_profile_signal(user_text: str, llm_caller, sid: str = "") -> dict | None:
    """两级流水线主入口（同步）：返回判定与写入结果，None=未触发/已丢弃。

    一级不命中 → None（零成本）；二级拒绝/失败 → None；写入结果带 write 详情。
    """
    if not keyword_gate(user_text):
        return None
    judged = _llm_judge(llm_caller, user_text)
    if not judged:
        return None  # 精判失败/输出不可解析 → 静默丢弃（与未触发同语义）
    if judged.get("is_signal") is not True:
        return {"judged": judged, "write": None}  # 二级拒绝（保留判定供审计/测试）
    candidate = str(judged.get("candidate", "")).strip()
    category = str(judged.get("category", "preference")).strip()
    if not candidate:
        return {"judged": judged, "write": None}
    # 写入走 write_user_profile（模板过滤兜底 + 去重 + 版本快照）
    from core.profile_writer import write_user_profile, set_last_sid
    set_last_sid(sid)  # 供 profile_writer 广播 profile.update 时带 session_id
    result = write_user_profile(candidate, category, signal_source="auto_detect")
    if not result.get("ok"):
        logger.info(
            "signal_detector: 候选被拒 reason=%s candidate=%r",
            result.get("reason"), candidate,
        )
    return {"judged": judged, "write": result}


def maybe_detect_profile_signal(
    sid: str,
    user_text: str,
    llm_caller,
    delay: float = 0.8,
) -> None:
    """异步入口（回合收尾调用）：daemon 线程执行，不阻塞主流程。

    delay：让主线程完全走完 message.complete 后的收尾（ENG-1：主线程
    complete 后零调用由异步线程承担，两者互不阻塞）。
    """

    def _run():
        try:
            time.sleep(delay)
            detect_profile_signal(user_text, llm_caller, sid=sid)
        except Exception:
            # 信号检测任何失败都只留痕，绝不向上抛（回合已结束）
            logger.exception("signal_detector: 异步检测失败 session=%s", sid)

    t = threading.Thread(target=_run, daemon=True, name="profile5-signal")
    t.start()


# ── TICKET-PROFILE-PARADIGM-VALIDATE：约束框架判断（纯验证辅助，不改主流程、不进生产路径）──
# 【COST-3 特批标记】PROFILE 系列授权：core/signal_detector.py 加纯验证辅助函数，
# 不接主流程、不影响 detect_profile_signal/maybe_detect_profile_signal 行为。

# 强话题限定词（单一领域 → 降为话题细节，非跨场景行为范式）
_STRONG_TOPIC = ("数学", "微积分", "评测", "K3", "代数", "几何", "物理", "化学", "编译", "API")

# 一次性信号词（这类样本无论含多少偏好词，都应丢弃）
_ONCE_PAT = re.compile(r"这次|先定评测集|先.*测一下")
# 纠正信号词（应修正旧条目而非新增）
_CORRECT_PAT = re.compile(r"别再用|别再|不要每次|不要每[次一]|不要每次都")
# 显式指令词（记住 + 非话题限定 → 直接进）
_INSTR_PAT = re.compile(r"记住")
# 长期行为词（跨场景可复用）
_REUSE_PAT = re.compile(r"以后|每次|都|任何|偏好|喜欢|先.+再|习惯")
# 思维链条（表达"先 X 再 Y / 每次 / 都"等长期思考模式）
_CHAIN_PAT = re.compile(r"都|任何|先.+再|每次|以后|习惯")
# 可操作（具体可执行的长期行为）
_ACT_PAT = re.compile(r"(以后|每次|都|任何).*(用|写|记|讲|说|做|测|画)|先.+再")


def _judge_by_constraints(sample: str) -> dict:
    """约束框架判断（纯验证辅助函数，不改主流程）。

    对单条样本做 7 维约束评分 → 判定画像信号类别，用于与词眼判断（detect_profile_signal
    的 keyword_gate + LLM）做小规模对比验证（TICKET-PROFILE-PARADIGM-VALIDATE）。

    返回：
      {"classify": "profile|memory|discard|correction|instruction",
       "dims": {7 维打分}, "reason": "判定依据"}

    归类对齐写 USER.md 与否：
      profile / instruction → 写 USER.md
      memory / discard / correction → 不写（discard 丢弃，memory 存记忆，correction 修正旧条目）

    7 维约束：
      diversity    跨场景多样性（0=单一话题, 1=跨场景）
      chain        思维链条（长期思考模式）
      reusable     可跨回合复用
      actionable   可执行（具体长期行为，非一次性步骤）
      evidence     行为证据（"偏好/喜欢/不要/别"等明确立场）
      causality    因果（因为/所以/避免/而非）
      consistency  一致性（非一次性、非纠正则视为一致）
    """
    s = sample.strip()
    topic_hits = [w for w in _STRONG_TOPIC if w in s]
    chain = 1 if _CHAIN_PAT.search(s) else 0
    reusable = 1 if (_REUSE_PAT.search(s) and not _ONCE_PAT.search(s)) else 0
    actionable = 1 if _ACT_PAT.search(s) else 0
    evidence = 1 if re.search(r"偏好|喜欢|不要|别|讨厌|其实", s) else 0
    causality = 1 if re.search(r"因为|所以|避免|导致|而非", s) else 0
    dims = {
        "diversity": 0 if topic_hits else 1,
        "chain": chain,
        "reusable": reusable,
        "actionable": actionable,
        "evidence": evidence,
        "causality": causality,
        "consistency": 1,
    }

    # 判定优先级：discard > correction > instruction > 话题/范式
    if _ONCE_PAT.search(s):
        return {"classify": "discard", "dims": dims, "reason": "一次性请求/步骤，应丢弃"}
    if _CORRECT_PAT.search(s):
        return {"classify": "correction", "dims": dims, "reason": "纠正旧条目，应修正写入"}
    if _INSTR_PAT.search(s) and not topic_hits:
        return {"classify": "instruction", "dims": dims, "reason": "显式指令，直接进 USER.md"}
    # 话题细节：强话题限定 + 长期词 → 单一领域偏好，存记忆不入 USER.md
    if topic_hits and (reusable or actionable):
        return {"classify": "memory", "dims": dims, "reason": "话题细节（限定单一领域），存记忆不入 USER.md"}
    # 跨场景行为范式
    if reusable and actionable:
        return {"classify": "profile", "dims": dims, "reason": "跨场景可复用可操作行为范式，写 USER.md"}
    if reusable and not actionable:
        return {"classify": "profile", "dims": dims, "reason": "长期偏好但可操作性弱，仍按范式写入"}
    return {"classify": "profile", "dims": dims, "reason": "默认按行为范式写入"}
