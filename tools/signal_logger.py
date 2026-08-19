# -*- coding: utf-8 -*-
"""票 P0-2 通道 A：对话信号日志（只记录不动作）。

对话回合沉淀路径的信号判定 hook：
- 用户消息按 guidance 四条（DISCUSSION 8.5）判定：
  1. "以后/下次/从今往后" + 期望行为 → workflow（工作流模式信号）
  2. "不要/别/别再/别用" + 不喜欢行为 → negative（负强化信号）
  3. 重复要求同类事 ≥N 次 → implicit（隐含偏好信号）
  4. "记住/以后都这样" → strong（强信号）
- 命中 → 追加写 data/logs/signal_log.jsonl（含 judgement 原话）；
- 零动作铁律：绝不写 knowledge_base / 不改 memory / 不注入任何提示；
- 频控：同一会话内同类信号去重（防一条偏好刷 10 条日志）；
- 失败静默降级：LLM 超时/报错 → 跳过本回合，不阻塞对话、不留异常。

用法：
  通道 A hook:  judge_and_log_signal(user_text, sid, llm_call)
  CLI 查看:     python -m tools.signal_logger list [--limit 20] [--session SID]
"""

import json
import os
import time

# 信号日志固定落 data/logs/（与 Obsidian 无关）
_LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "data", "logs")
_SIGNAL_LOG = os.path.join(_LOG_DIR, "signal_log.jsonl")

# 预筛关键词（四条判据的语言特征；命中才送 LLM 判定，普通对话零 LLM 成本）
_PREFILTER = {
    "workflow": ["以后", "下次", "从今往后", "以后都", "以后用", "以后先", "以后要"],
    "negative": ["不要", "别用", "别在", "别再", "以后不要", "不用", "别给", "别做"],
    "implicit": ["每次都", "每次都要", "又是", "再说一遍", "重复", "还是老"],
    "strong": ["记住", "以后都这样", "永远", "记住了", "记一下"],
}

_SYSTEM_PROMPT = (
    "你是用户偏好信号判定器。判断用户消息是否包含以下四种信号之一：\n"
    "1. workflow（工作流模式）：用户说'以后/下次/从今往后'并指定期望做法；\n"
    "2. negative（负强化）：用户说'不要/别/别用'表达不喜欢的行为；\n"
    "3. implicit（隐含偏好）：用户重复要求同类事（含历史消息暗示）；\n"
    "4. strong（强信号）：用户明确说'记住/以后都这样'。\n"
    "只输出一行 JSON，格式："
    '{"is_signal": true|false, "signal_type": "workflow|negative|implicit|strong", '
    '"judgement": "一句话说明判定理由"}。'
    "普通对话、问候、项目进展叙述不是信号，is_signal 必须为 false。"
)


def _read_existing() -> list[dict]:
    """读现有 signal_log.jsonl（频控去重用；小文件，逐行读）。"""
    if not os.path.exists(_SIGNAL_LOG):
        return []
    out = []
    try:
        with open(_SIGNAL_LOG, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue  # 坏行跳过，不阻塞
    except OSError:
        return []
    return out


def _prefilter(user_text: str) -> bool:
    """预筛：文本含任一判据特征词才送 LLM。"""
    low = user_text.lower()
    return any(kw in low for kws in _PREFILTER.values() for kw in kws)


def _append_record(record: dict) -> None:
    """原子追加写日志（O_APPEND 单次写入，线程安全）。"""
    os.makedirs(_LOG_DIR, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False) + "\n"
    fd = os.open(_SIGNAL_LOG, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o644)
    try:
        os.write(fd, line.encode("utf-8"))
    finally:
        os.close(fd)


def judge_and_log_signal(user_text: str, sid: str, llm_call,
                         history: list | None = None) -> dict:
    """通道 A 入口：判定 + 写日志（零动作，失败静默）。

    参数：
      user_text: 最近一条用户消息（判定对象）
      sid: 会话 id
      llm_call: 可调用对象 llm_call(prompt, use_tools=False, max_tokens=...) → dict
      history: 最近用户消息列表（implicit 判据的重复上下文，可选）

    返回：
      {"logged": bool, "record": dict|None, "reason": str}
      logged=True 表示写入了 signal_log.jsonl；任何失败返回 logged=False。
    """
    _t0 = time.time()

    if not user_text or not user_text.strip():
        return {"logged": False, "reason": "empty_text",
                "llm_called": False, "duration_ms": 0}
    user_text = user_text.strip()
    if len(user_text) < 4:
        return {"logged": False, "reason": "too_short",
                "llm_called": False, "duration_ms": 0}

    # 预筛：无特征词 → 普通对话零误写、零 LLM 成本
    if not _prefilter(user_text):
        return {"logged": False, "reason": "no_keyword",
                "llm_called": False, "duration_ms": 0}

    # 频控预检：同会话同类信号已存在 → 跳过（防刷屏）
    existing = _read_existing()
    for rec in existing:
        if rec.get("session_id") == sid and rec.get("signal_type") in _PREFILTER:
            return {"logged": False, "reason": "dup_type",
                    "llm_called": False, "duration_ms": 0}

    # LLM 判定（guidance 四条）
    ctx_lines = []
    if history:
        ctx_lines.append("最近用户消息（用于'重复要求'判据）：")
        for h in history[-4:]:
            ctx_lines.append(f"- {h[:120]}")
    ctx_lines.append(f"本条用户消息：{user_text[:300]}")
    prompt = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": "\n".join(ctx_lines)},
    ]
    try:
        response = llm_call(prompt, use_tools=False, max_tokens=150)
        _llm_called = True
    except Exception:
        # 静默降级：LLM 失败跳过本回合，不阻塞对话
        return {"logged": False, "reason": "llm_error", "llm_called": True,
                "duration_ms": int((time.time() - _t0) * 1000)}
    if not isinstance(response, dict) or "error" in response:
        return {"logged": False, "reason": "llm_error", "llm_called": True,
                "duration_ms": int((time.time() - _t0) * 1000)}
    content = (response.get("choices", [{}])[0]
               .get("message", {}).get("content", "") or "").strip()
    # 提取第一行 JSON（容忍 LLM 输出多余前缀）
    parsed = None
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                parsed = json.loads(line)
                break
            except json.JSONDecodeError:
                continue
    if not parsed or not parsed.get("is_signal"):
        return {"logged": False, "reason": "no_signal", "llm_called": True,
                "duration_ms": int((time.time() - _t0) * 1000)}

    signal_type = parsed.get("signal_type", "")
    if signal_type not in _PREFILTER:
        signal_type = "workflow"  # 兜底归类
    judgement = str(parsed.get("judgement", "") or "")[:300]

    # 二次频控（写前再查一次，防并发竞态刷重复）
    existing = _read_existing()
    for rec in existing:
        if rec.get("session_id") == sid and rec.get("signal_type") == signal_type:
            return {"logged": False, "reason": "dup_type", "llm_called": True,
                    "duration_ms": int((time.time() - _t0) * 1000)}

    record = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "session_id": sid,
        "signal_type": signal_type,
        "user_text": user_text[:200],
        "judgement": judgement,
        "source": "conversation",
    }
    try:
        _append_record(record)
    except OSError:
        return {"logged": False, "reason": "write_error", "llm_called": True,
                "duration_ms": int((time.time() - _t0) * 1000)}
    return {"logged": True, "record": record, "reason": "logged",
            "llm_called": True, "duration_ms": int((time.time() - _t0) * 1000)}


def list_signals(limit: int = 20, session_id: str = "") -> list[dict]:
    """CLI 查看：读 signal_log.jsonl 倒序返回（人工评估用）。"""
    records = _read_existing()
    if session_id:
        records = [r for r in records if r.get("session_id") == session_id]
    records.sort(key=lambda r: r.get("ts", ""), reverse=True)
    return records[:limit]


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="信号日志查看（票 P0-2 通道 A）")
    sub = parser.add_subparsers(dest="cmd")
    list_p = sub.add_parser("list", help="列出信号日志")
    list_p.add_argument("--limit", type=int, default=20)
    list_p.add_argument("--session", default="")
    args = parser.parse_args()

    if args.cmd == "list":
        rows = list_signals(limit=args.limit, session_id=args.session)
        if not rows:
            print("（无信号记录）")
            sys.exit(0)
        for r in rows:
            print(f"[{r.get('ts')}] {r.get('signal_type')} sid={r.get('session_id')}")
            print(f"  用户: {r.get('user_text')}")
            print(f"  判定: {r.get('judgement')}")
    else:
        parser.print_help()
