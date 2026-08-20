"""skill_sedimenter.py — skill 自动沉淀流水线（票 TICKET-SKILL-ACTIVE-3，B 票）。

【COST-3 守卫登记】core/ 新增模块，TICKET-SKILL-ACTIVE-3 owner 授权；
挂载点 engine_adapter.run_engine 的 message.complete 异步收尾（与
TICKET-PROFILE-5 的 signal_detector 同款 daemon 线程模式，主线程零阻塞）；
二级 LLM 精判复用 signal_detector 的 thinking_disabled 冷调用（P5-400 修复
同款——独立冷调用关 thinking，避免 DeepSeek 400）。

三级流水线（完全自动、零用户确认、零打扰——owner 红线：不值得就静默）：
  一级 数量门卫（确定性，零成本）：读 data/logs/events.jsonl 的 tool.exec
    事件，同一"任务模式"（工具名 + 参数模式指纹，如 execute_terminal +
    "pytest tests/"）≥3 次 → 进二级。每会话/每日限一次触发（防刷屏）。
  二级 LLM 精判（命中才 +1 次短调用）：三问——①可复用？②用户受益？
    ③值得沉淀？→ 值得 → 生成草案（name/triggers/steps）；不值得 → 静默。
  三级 自动沉淀：写 data/skills/custom/<name>/standard.md（格式对齐
    core/skill_manager.save_from_recording）+ emit skill.activate（前端 Skill
    卡，TICKET-SKILL-ACTIVE-2 已有渲染，零前端改动）→ SKILL-PANEL Custom 组
    扫描 data/skills/custom/ 自动可见。默认 enabled=true（治理机制零改动）。
"""

import json
import logging
import os
import re
import threading
import time
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)

# ── 路径（测试可 monkeypatch 模块级常量隔离）──────────────────────────
_BASE = Path(__file__).resolve().parent.parent
_EVENTS_FILE = _BASE / "data" / "logs" / "events.jsonl"
_SKILLS_DIR = _BASE / "data" / "skills"
_CUSTOM_DIR = _SKILLS_DIR / "custom"
_SEDIMENTED_FILE = _SKILLS_DIR / "sedimented.json"

# 一级门卫参数
_MIN_COUNT = 3            # 同模式 ≥3 次进二级
_SCAN_LIMIT = 800         # 最近 N 条 tool.exec 事件（控制扫描成本）
_TRIGGER_DELAY = 0.8      # 异步线程延迟（错开 message.complete 收尾，ENG-1）

# 二级精判参数（短调用：小上下文、少 token，thinking_disabled 防 400）
_JUDGE_MAX_TOKENS = 300
_JUDGE_PROMPT = """你是技能沉淀裁判。bobo 最近重复执行了以下工具调用模式（已 ≥3 次）：
工具: {tool}
参数样例: {sample}

三问判断是否值得沉淀为 skill：
① 可复用？流程固定、有明确触发条件（不是一次性任务）
② 用户受益？省时/少犯错（不是用户享受手动的过程）
③ 值得沉淀？值得 → 生成 skill 草案

- 值得 → 只输出 JSON：{{"worth": true, "name": "短横线英文名（如 pytest-runner）",
  "triggers": ["触发词1", "触发词2"], "steps": ["步骤1", "步骤2"]}}
- 不值得（一次性任务 / 用户偏好手动操作 / 没有固定流程）→ 只输出 JSON：{{"worth": false}}
只输出 JSON 对象，不要任何其他文字。"""

# 进程内 session 冷却（每会话限一次；防多轮重复触发）
_session_done: set = set()


# ── 一级：数量门卫（确定性）──────────────────────────────────────────

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


def count_patterns(min_count: int = _MIN_COUNT, limit: int = _SCAN_LIMIT) -> dict:
    """扫 events.jsonl 最近 limit 条 tool.exec → {模式: 次数}，只返回 ≥min_count。

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
    return {p: c for p, c in counts.items() if c >= min_count}


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

def _judge(pattern: str, llm_caller) -> dict | None:
    """三问精判 → 草案 dict 或 None（静默）。任何失败 → None（不打扰）。"""
    tool, _, sample = pattern.partition("|")
    prompt = _JUDGE_PROMPT.format(tool=tool, sample=sample or "（无参数样例）")
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
    """解析裁判输出：找 JSON 对象；worth=false 或无 JSON → None。"""
    if not content:
        return None
    m = re.search(r"\{.*\}", content, re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except ValueError:
        return None
    if not isinstance(data, dict) or not data.get("worth"):
        return None
    name = str(data.get("name", "")).strip()
    if not name or not re.match(r"^[a-z0-9][a-z0-9-]{1,49}$", name):
        return None
    return {
        "name": name,
        "triggers": [str(t).strip() for t in (data.get("triggers") or []) if str(t).strip()][:8],
        "steps": [str(s).strip() for s in (data.get("steps") or []) if str(s).strip()][:12],
    }


# ── 三级：自动沉淀（零确认）──────────────────────────────────────────

def save_custom_skill(draft: dict, pattern: str) -> str:
    """写 data/skills/custom/<name>/standard.md（格式对齐 save_from_recording）。

    返回沉淀的 skill 名。写失败上抛（由调用方留痕）。
    """
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


def _emit_skill_card(name: str) -> None:
    """emit skill.activate → 前端 Skill 卡（SKILL-ACTIVE-2 渲染，零改动）。"""
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
        return  # 无 ≥3 次模式 → 一级静默
    pattern, count = max(patterns.items(), key=lambda kv: kv[1])
    if not _can_trigger(session_id, pattern):
        return  # 冷却 → 静默
    draft = _judge(pattern, llm_caller)
    if not draft:
        # 不值得 / 精判失败 → 记当日冷却，静默（owner 红线：不打扰）
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
