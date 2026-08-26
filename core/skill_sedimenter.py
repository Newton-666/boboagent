"""skill_sedimenter.py — skill 自动沉淀流水线（票 TICKET-SKILL-ACTIVE-3，B 票）。

【COST-3 守卫登记】core/ 新增模块，TICKET-SKILL-ACTIVE-3 owner 授权；
挂载点 engine_adapter.run_engine 的 message.complete 异步收尾（与
TICKET-PROFILE-5 的 signal_detector 同款 daemon 线程模式，主线程零阻塞）；
二级 LLM 精判复用 signal_detector 的 thinking_disabled 冷调用（P5-400 修复
同款——独立冷调用关 thinking，避免 DeepSeek 400）。

三级流水线（完全自动、零用户确认、零打扰——owner 红线：不值得就静默）：
  一级 门卫（确定性，零成本）：负向清单硬拦截 + 每会话/每日冷却闸。
    数量不再作为门槛，仅作为 LLM 精判的参考信号。
  二级 LLM 精判（命中才 +1 次短调用）：四问——①是否工作流（流程性）
    ②可复用？③用户受益？④确定性/置信度？→ 值得 → 生成草案；
    不值得 → 静默。优先 patch 现有类级 skill，禁止 fix/debug/session 等
    一次性命名。
  三级 自动沉淀：
    - 若 LLM 判定为"记忆"（非工作流）→ 直接静默跳过，不建 skill；
    - 若判定为"技能"且存在同类 skill → patch 现有 skill；
    - 若判定为"技能"且无同类 → 新建 data/skills/custom/<name>/standard.md；
    - 写完后调用 skill_lifecycle.register_skill(name, agent_created=True) 登记。

（COST-3 守卫标记：本文件沉淀机制升级——bobo 施工 2026-08-26，入库配套。）
"""

import json
import logging
import os
import re
import threading
import time
from datetime import date
from pathlib import Path

from core import skill_lifecycle

logger = logging.getLogger(__name__)

# ── 路径（测试可 monkeypatch 模块级常量隔离）──────────────────────────
_BASE = Path(__file__).resolve().parent.parent
_EVENTS_FILE = _BASE / "data" / "logs" / "events.jsonl"
_SKILLS_DIR = _BASE / "data" / "skills"
_CUSTOM_DIR = _SKILLS_DIR / "custom"
_SEDIMENTED_FILE = _SKILLS_DIR / "sedimented.json"

# 一级门卫参数
_SCAN_LIMIT = 800         # 最近 N 条 tool.exec 事件（控制扫描成本）
_TRIGGER_DELAY = 0.8      # 异步线程延迟（错开 message.complete 收尾，ENG-1）

# 负向清单：这些模式无论出现多少次都不沉淀（防止自缚/一次性/环境错误）
_NEGATIVE_PATTERNS = [
    # 环境依赖失败 / 路径错误
    r"command\s+not\s+found",
    r"no\s+such\s+file",
    r"no\s+module\s+named",
    r"permission\s+denied",
    r"cannot\s+find",
    r"is\s+not\s+recognized",
    r"not\s+installed",
    r"missing\s+dependency",
    # 负面断言 / 工具坏了
    r"\bbroken\b",
    r"\bbug\b",
    r"\bfails?\b",
    r"\bnever\s+works\b",
    r"\balways\s+fails\b",
    r"\b坏了\b",
    r"\b报错\b",
    r"\b失败\b",
    # 一次性 / 临时叙事
    r"just\s+this\s+once",
    r"only\s+this\s+time",
    r"一次性",
    r"临时",
    r"one-off",
    r"this\s+one\s+time",
]
_NEGATIVE_RE = re.compile("|".join(f"({p})" for p in _NEGATIVE_PATTERNS), re.IGNORECASE)

# 禁止的类级命名前缀（防止把一次性修复沉淀为技能）
_FORBIDDEN_NAME_PREFIXES = ("fix-", "debug-", "error-", "err-", "session-", "tmp-", "temp-")

# 二级精判参数（短调用：小上下文、少 token，thinking_disabled 防 400）
_JUDGE_MAX_TOKENS = 400
_JUDGE_PROMPT = """你是技能沉淀裁判。bobo 最近执行了以下工具调用模式：
工具: {tool}
参数样例: {sample}
出现次数: {count}（仅作参考，不是门槛）

判断这个信号应该进入记忆还是技能：

第一问（决定性）：这是否构成一个工作流？
- 工作流 = 一套可复用的步骤序列，有明确触发条件，未来同类任务可按此执行。
- 不是工作流 = 单点偏好、单点事实、单点规则、一次性操作、环境报错、负面断言。

如果不是工作流 → 输出：{{"memory_only": true}}

如果是工作流，继续回答下面四问：
① 流程性：步骤是否固定、可编码？
② 可复用性：未来是否可能重复遇到同类任务？
③ 用户受益：沉淀后能否省时/少犯错/提升一致性？
④ 确定性：你对"这是工作流"的置信度高吗？

输出 JSON（只输出 JSON，不要任何其他文字）：
{{
  "memory_only": false,
  "worth": true/false,
  "confidence": "high|medium|low",
  "update_priority": "patch-existing|create-new|drop",
  "existing_skill": "现有 skill 名（如果 update_priority=patch-existing）",
  "name": "短横线英文类级名（如 pytest-runner），禁止 fix-/debug-/error-/session-/tmp-/temp- 前缀",
  "triggers": ["触发词1", "触发词2"],
  "steps": ["步骤1", "步骤2"],
  "reason": "一句话判断理由"
}}

- worth=false 或 confidence=low → 静默不沉淀。
- update_priority=patch-existing 时，必须提供 existing_skill（最匹配的已有 skill 名）。
- update_priority=drop → 不值得，静默。
"""

# 进程内 session 冷却（每会话限一次；防多轮重复触发）
_session_done: set = set()


# ── 一级：参数指纹（保留）────────────────────────────────────────────

def _fingerprint(args_summary: str, max_len: int = 30) -> str:
    """args_summary（JSON 字符串）→ 参数模式指纹。

    从 command/pattern/path 等字段取第一个字符串值，规范化：
    去引号、压空白、去掉 "cd <path> && " 前缀、取动词+目标（目标去掉
    文件级细节，如 tests/test_x.py → tests/）。无参数 → 空串（纯工具名聚类）。
    """
    if not args_summary:
        return ""
    try:
        parsed = json.loads(args_summary)
    except (ValueError, TypeError):
        return ""
    if not isinstance(parsed, dict):
        return ""
    val = ""
    for k in ("command", "pattern", "query", "path", "file_path"):
        v = parsed.get(k)
        if isinstance(v, str):
            val = v
            break
    if not val:
        for v in parsed.values():
            if isinstance(v, str):
                val = v
                break
    if not val:
        return ""
    val = re.sub(r'["\'`]', "", val)
    val = re.sub(r"^cd\s+[^&]+&&\s*", "", val)  # 去 cd 前缀
    val = re.sub(r"\s+", " ", val).strip()
    tokens = val.split()
    if not tokens:
        return ""
    verb = tokens[0]
    if len(tokens) > 1:
        obj = tokens[1]
        if "/" in obj:
            obj = re.sub(r"/[^/]+$", "/", obj)  # 去文件级细节
        return f"{verb} {obj}"[:max_len]
    return verb[:max_len]


def _task_pattern(evt: dict) -> str:
    """tool.exec 事件 → 任务模式 key（工具名 + 参数指纹）。"""
    name = evt.get("name", "")
    if not name:
        return ""
    fp = _fingerprint(evt.get("args_summary", ""))
    return f"{name}|{fp}" if fp else name


# ── 一级：数量门卫（已降级为参考信号）────────────────────────────────

def count_patterns(limit: int = _SCAN_LIMIT) -> dict:
    """扫 events.jsonl 最近 limit 条 tool.exec → {模式: 次数}。

    不再设置 min_count 门槛；返回所有计数供 LLM 参考。
    历史记录无 args_summary（旧版本）→ 退化为纯工具名聚类；文件缺失/损坏
    → 返回空（一级静默跳过，零打扰）。
    """
    counts: dict = {}
    try:
        with open(_EVENTS_FILE, encoding="utf-8") as f:
            lines = f.readlines()[-limit:]
    except OSError:
        return {}
    for ln in lines:
        try:
            evt = json.loads(ln)
        except (ValueError, TypeError):
            continue
        if not isinstance(evt, dict) or evt.get("type") != "tool.exec":
            continue
        p = _task_pattern(evt)
        if not p:
            continue
        counts[p] = counts.get(p, 0) + 1
    return counts


def _negative_pattern(pattern: str) -> bool:
    """负向清单硬闸：命中则无论次数/LLM 都直接静默。"""
    return bool(_NEGATIVE_RE.search(pattern))


# ── 冷却：每会话/每日限一次 + 已沉淀不重复 ───────────────────────────

def _load_sedimented() -> dict:
    """读 data/skills/sedimented.json → {"patterns": [...], "last_date": "YYYY-MM-DD"}。"""
    try:
        with open(_SEDIMENTED_FILE, encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, dict):
            return raw
    except (OSError, ValueError):
        pass
    return {}


def _save_sedimented(data: dict) -> None:
    try:
        _SKILLS_DIR.mkdir(parents=True, exist_ok=True)
        with open(_SEDIMENTED_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError:
        pass  # 冷却记录失败不阻断沉淀主流程


def _can_trigger(session_id: str, pattern: str) -> bool:
    """防刷屏闸：同 session 不重复 / 每日限一次 / 已沉淀模式不重复。"""
    if session_id in _session_done:
        return False
    data = _load_sedimented()
    today = date.today().isoformat()
    if data.get("last_date") == today:
        return False
    if pattern in data.get("patterns", []):
        return False
    return True


def _mark_triggered(session_id: str, pattern: str, sedimented: bool) -> None:
    """记录冷却（无论是否沉淀都记：当日已精判过）。"""
    _session_done.add(session_id)
    data = _load_sedimented()
    data["last_date"] = date.today().isoformat()
    if sedimented and pattern not in data.get("patterns", []):
        data.setdefault("patterns", []).append(pattern)
    _save_sedimented(data)


# ── 二级：LLM 精判（thinking_disabled 冷调用）────────────────────────

def _judge(pattern: str, count: int, llm_caller) -> dict | None:
    """四问精判 → 草案 dict 或 None（静默）。任何失败 → None（不打扰）。"""
    tool, _, sample = pattern.partition("|")
    prompt = _JUDGE_PROMPT.format(
        tool=tool,
        sample=sample or "（无参数样例）",
        count=count,
    )
    try:
        resp = llm_caller(
            [
                {"role": "system", "content": prompt},
                {"role": "user", "content": f"请判断该模式是否值得沉淀为 skill。模式: {pattern}"},
            ],
            use_tools=False,
            max_tokens=_JUDGE_MAX_TOKENS,
            # 【COST-3 特批标记】P5-400 修复同款：独立冷调用关 thinking
            thinking_disabled=True,
        )
    except Exception:
        logger.warning("skill_sedimenter: LLM 精判失败，静默跳过", exc_info=True)
        return None
    if not isinstance(resp, dict) or resp.get("error"):
        logger.warning("skill_sedimenter: LLM 精判返回错误: %s", (resp or {}).get("error"))
        return None
    content = ""
    try:
        content = resp["choices"][0]["message"].get("content", "") or ""
    except (KeyError, IndexError, TypeError):
        return None
    return _parse_judge_output(content)


def _parse_judge_output(content: str) -> dict | None:
    """解析裁判输出：找 JSON 对象；worth=false / memory_only / drop → None。"""
    if not content:
        return None
    m = re.search(r"\{.*\}", content, re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None

    # 非工作流 → 进记忆路径（本模块不处理记忆写入，直接静默跳过）
    if data.get("memory_only"):
        return None

    if not data.get("worth"):
        return None
    if data.get("confidence") == "low":
        return None
    if data.get("update_priority") == "drop":
        return None

    name = str(data.get("name", "")).strip()
    if not name or not re.match(r"^[a-z0-9][a-z0-9-]{1,49}$", name):
        return None
    if name.startswith(_FORBIDDEN_NAME_PREFIXES):
        return None

    return {
        "name": name,
        "triggers": [str(t).strip() for t in (data.get("triggers") or []) if str(t).strip()][:8],
        "steps": [str(s).strip() for s in (data.get("steps") or []) if str(s).strip()][:12],
        "update_priority": str(data.get("update_priority", "create-new")).strip(),
        "existing_skill": str(data.get("existing_skill", "")).strip() or None,
        "reason": str(data.get("reason", "")).strip(),
    }


# ── 三级：自动沉淀（零确认）──────────────────────────────────────────

def _find_similar_skill(name: str, triggers: list) -> str | None:
    """扫描 data/skills/custom/，找最匹配的已有 skill 名。

    匹配策略：名称完全一致 或 keywords 行包含任一 trigger。
    返回 skill 名（目录名）或 None。
    """
    if not _CUSTOM_DIR.exists():
        return None
    candidates = []
    for entry in _CUSTOM_DIR.iterdir():
        if not entry.is_dir():
            continue
        std = entry / "standard.md"
        if not std.exists():
            continue
        skill_name = entry.name
        # 名称完全一致
        if skill_name == name:
            return skill_name
        # keywords 匹配
        try:
            text = std.read_text(encoding="utf-8")
        except OSError:
            continue
        for t in triggers:
            if t and t.lower() in text.lower():
                candidates.append((skill_name, len(t)))
                break
    if not candidates:
        return None
    # 选 trigger 最长命中的那个（最相关）
    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates[0][0]


def _patch_existing_skill(draft: dict, existing_name: str, pattern: str) -> str:
    """合并新步骤到已有 skill 的 standard.md，返回 skill 名。"""
    std_path = _CUSTOM_DIR / existing_name / "standard.md"
    try:
        old = std_path.read_text(encoding="utf-8")
    except OSError as e:
        raise RuntimeError(f"读取现有 skill 失败: {existing_name}") from e

    new_steps = draft.get("steps") or []
    if not new_steps:
        return existing_name

    # 简单去重：如果步骤已存在，跳过
    existing_lines = [ln.strip() for ln in old.splitlines()]
    additions = []
    for s in new_steps:
        if s not in old:
            additions.append(s)
    if not additions:
        return existing_name

    appended = "\n\n## 更新（自动沉淀）\n\n自动沉淀自重复工具模式: " + pattern + "\n\n"
    appended += "\n".join(f"- {s}" for s in additions)
    std_path.write_text(old.rstrip() + "\n" + appended + "\n", encoding="utf-8")
    return existing_name


def _create_new_skill(draft: dict, pattern: str) -> str:
    """新建 data/skills/custom/<name>/standard.md，返回 skill 名。"""
    name = draft["name"]
    std_dir = _CUSTOM_DIR / name
    std_dir.mkdir(parents=True, exist_ok=True)
    triggers = ", ".join(draft.get("triggers") or []) or name
    steps = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(draft.get("steps") or [])) or "（自动沉淀，无显式步骤）"
    content = f"""# {name} v1

> keywords: {triggers}
> status: draft
> source: auto-sedimented

## 工作流

自动沉淀自重复工具模式: {pattern}

## 描述

由 bobo 自动沉淀的工作流（TICKET-SKILL-ACTIVE-3，零用户确认）。

## 步骤

{steps}
"""
    filepath = std_dir / "standard.md"
    filepath.write_text(content, encoding="utf-8")
    return name


def save_custom_skill(draft: dict, pattern: str) -> str:
    """写 data/skills/custom/<name>/standard.md（格式对齐 save_from_recording）。

    根据 update_priority 决定 patch 现有 skill 还是新建。
    返回沉淀的 skill 名。写失败上抛（由调用方留痕）。
    """
    name = draft["name"]
    existing = draft.get("existing_skill")

    # 如果 LLM 要求 patch 且指定了现有 skill，校验存在性
    if draft.get("update_priority") == "patch-existing" and existing:
        if (_CUSTOM_DIR / existing / "standard.md").exists():
            name = _patch_existing_skill(draft, existing, pattern)
        else:
            # 指定 skill 不存在 → 降级为新建（类级名使用 draft.name）
            name = _create_new_skill(draft, pattern)
    else:
        # 未指定 patch → 扫描同类；有则 patch，无则新建
        similar = _find_similar_skill(name, draft.get("triggers") or [])
        if similar:
            name = _patch_existing_skill(draft, similar, pattern)
        else:
            name = _create_new_skill(draft, pattern)

    # 登记生命周期（首次见到锚定 now，防新技能立即归档）
    try:
        skill_lifecycle.register_skill(name, agent_created=True)
    except Exception:
        logger.warning("skill_sedimenter: 生命周期登记失败（静默）", exc_info=True)

    return name


def _emit_skill_card(name: str) -> None:
    """emit skill.activate 事件（前端 Skill 卡自动刷新，失败静默）。"""
    try:
        from core.event_bus import event_bus
        event_bus.write("skill.activate", {"skill_name": name})
    except Exception:
        logger.warning("skill_sedimenter: skill.activate emit 失败（静默降级）", exc_info=True)


# ── 主入口 ────────────────────────────────────────────────────────────

def _sediment_skill(session_id: str, llm_caller) -> None:
    """同步流水线：门卫 → 精判 → 沉淀。全程静默失败（零打扰）。"""
    patterns = count_patterns()
    if not patterns:
        return  # 无任何模式 → 一级静默

    # 选出现次数最多的模式进入精判（数量仅为参考）
    pattern, count = max(patterns.items(), key=lambda kv: kv[1])

    # 负向清单硬拦截
    if _negative_pattern(pattern):
        logger.info("skill_sedimenter: 命中负向清单，静默跳过 pattern=%s", pattern)
        return

    if not _can_trigger(session_id, pattern):
        return  # 冷却 → 静默

    draft = _judge(pattern, count, llm_caller)
    if not draft:
        # 不值得 / 非工作流 / 精判失败 → 记当日冷却，静默（owner 红线：不打扰）
        _mark_triggered(session_id, pattern, sedimented=False)
        logger.info("skill_sedimenter: 模式不沉淀（静默） session=%s pattern=%s count=%d",
                    session_id, pattern, count)
        return
    try:
        name = save_custom_skill(draft, pattern)
        _mark_triggered(session_id, pattern, sedimented=True)
        _emit_skill_card(name)
        logger.info("skill_sedimenter: 已沉淀 skill=%s session=%s pattern=%s",
                    name, session_id, pattern)
    except OSError as e:
        logger.warning("skill_sedimenter: 沉淀写入失败（静默）: %s", e, exc_info=True)


def maybe_sediment_skill(session_id: str, llm_caller, delay: float = _TRIGGER_DELAY) -> None:
    """异步入口（engine_adapter 回合收尾调用）：daemon 线程执行，不阻塞主流程。

    与 PROFILE-5 同款模式：主线程 message.complete 后零调用由异步线程承担，
    delay 错开收尾写盘；任何失败只留痕不上抛。
    """

    def _run():
        try:
            time.sleep(delay)
            _sediment_skill(session_id, llm_caller)
        except Exception:
            logger.exception("skill_sedimenter: 异步沉淀失败 session=%s", session_id)

    t = threading.Thread(target=_run, daemon=True, name="skill-sediment")
    t.start()
