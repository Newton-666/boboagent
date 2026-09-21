"""core/loop_detect.py — 死循环检测（E4b：从 engine 搬出，骨干通信"观察部"雏形）。

纯函数 + history 参数化，不持有 engine 引用。engine 侧保留薄壳委托。

判定目标（issue #11）：
- 只读/调研多轮（目标在扩展）≠ stuck
- 连续同模式、或少数签名循环（变参绕圈）= stuck
- 宁可 progressing（软着陆）也不误掐仍在推进的回合；
  漏杀的降级路径是撞轮次上限的 progressing 软收尾 + 200 深度硬断 + 500 步保险丝。
"""
import json

_WRITE_TOOLS = {"edit_file", "file_operation", "file_writer", "task_ledger"}

# 从工具参数里抽出"调研目标"（路径/检索/URL/命令）+ 切片，忽略其余噪声键。
_TARGET_KEYS = (
    "filepath", "file_path", "path", "filename", "file",
    "pattern", "query", "url", "command",
)
_SLICE_KEYS = ("offset", "limit", "start_line", "end_line")

_LOOP_WINDOW = 5
# 窗口内不同 round_sig ≤ 此值 → 同模式或 A/B 变参循环。
_CYCLE_UNIQUE_MAX = 2
# 窗口内不同调研目标 ≥ 此值 → 只读探索仍在扩展。
_DIVERSITY_MIN = 3


def _args_dict(raw) -> dict:
    """tool arguments → dict（字符串 JSON 或已是 dict）。"""
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        return {}
    try:
        parsed = json.loads(raw or "{}")
    except Exception:
        return {"_raw": raw}
    return parsed if isinstance(parsed, dict) else {"_raw": raw}


def _call_fingerprint(name: str, raw_args) -> str:
    """单次调用的调研目标指纹：工具名 + 目标键 + 切片。

    无目标键时回退到规范化 arguments，避免未知工具无法区分。
    """
    args = _args_dict(raw_args)
    parts = []
    for k in _TARGET_KEYS:
        v = args.get(k)
        if v is not None and v != "":
            parts.append(f"{k}={v}")
    for k in _SLICE_KEYS:
        v = args.get(k)
        if v is not None and v != "":
            parts.append(f"{k}={v}")
    if not parts:
        try:
            parts.append(json.dumps(args, sort_keys=True, ensure_ascii=False))
        except Exception:
            parts.append(str(args))
    return f"{name}|{'|'.join(parts)}"


def round_sig(tool_calls: list) -> str:
    """规范化一轮工具调用的签名（同名同参 → 相同签名）。

    arguments 做 json 规范化（键序无关），排序后连接——顺序不同但
    工具集相同视为同模式（pattern 签名）。
    """
    _parts = []
    for _tc in tool_calls:
        _fn = _tc.get("function", {})
        _name = _fn.get("name", "")
        _args = _fn.get("arguments", "{}")
        if isinstance(_args, dict):
            try:
                _args = json.dumps(_args, sort_keys=True, ensure_ascii=False)
            except Exception:
                _args = str(_args)
        else:
            try:
                _args = json.dumps(json.loads(_args), sort_keys=True, ensure_ascii=False)
            except Exception:
                pass
        _parts.append(f"{_name}|{_args}")
    return "::".join(sorted(_parts))


def _round_record(tool_calls: list) -> dict:
    """一轮 tool_calls → sig / 工具名 / 调研目标指纹。"""
    _names = []
    _targets = []
    for _tc in tool_calls:
        _fn = _tc.get("function", {})
        _name = _fn.get("name", "")
        if not _name:
            continue
        _names.append(_name)
        _targets.append(_call_fingerprint(_name, _fn.get("arguments", "{}")))
    return {
        "sig": round_sig(tool_calls),
        "name_sig": "::".join(sorted(_names)),
        "names": _names,
        "targets": _targets,
    }


def last_n_tool_rounds(history: list, n: int = 5) -> list:
    """从 history 取最近 n 轮（带 tool_calls 的 assistant 消息）的签名与工具名。"""
    _rounds = []
    for _m in reversed(history):
        if _m.get("role") == "assistant" and _m.get("tool_calls"):
            _rounds.append(_round_record(_m["tool_calls"]))
            if len(_rounds) >= n:
                break
    return _rounds


def _earlier_tool_rounds(history: list, skip: int) -> list:
    """history 中跳过最近 skip 轮工具回合后的更早回合。"""
    _earlier = []
    _count = 0
    for _m in reversed(history):
        if _m.get("role") == "assistant" and _m.get("tool_calls"):
            if _count >= skip:
                _earlier.append(_round_record(_m["tool_calls"]))
            _count += 1
    return _earlier


def has_progress_signal(history: list, recent: list) -> tuple[bool, str]:
    """最近 n 轮是否有推进信号：写入、新工具种类、调研目标扩展。

    轮级判定全部从 history 最近 n 轮取（recent 参数）——tracker._change_log
    是会话累计列表，不能直接判"本轮有写入"（累计非空 ≠ 最近 n 轮有推进）。

    只读调研：窗口内不同目标足够多，或相对更早轮次出现新目标，算推进。
    不把"无写类工具"单独当成 stuck——那是 issue #11 的误杀源。
    """
    # 1) 文件写入/diff / 台账变更：最近 n 轮内出现写类工具调用
    for _r in recent:
        for _name in _r["names"]:
            if _name in _WRITE_TOOLS:
                return True, f"写类工具调用: {_name}"
    # 2) 新工具种类：最近 n 轮用过的工具名集合 ⊄ 更早轮次集合
    _recent_names = {n for r in recent for n in r["names"]}
    _earlier_rounds = _earlier_tool_rounds(history, len(recent))
    _earlier_names = {n for r in _earlier_rounds for n in r["names"]}
    _new = _recent_names - _earlier_names
    # 更早轮次为空（会话刚开始即撞线，无从对比）→ 不判"新工具种类"推进
    if _earlier_names and _new:
        return True, f"新工具种类: {sorted(_new)[:3]}"
    # 3) 窗口内调研目标足够多样（只读探索：读不同文件 / 换检索词 / 换 URL）
    _recent_targets = {t for r in recent for t in r.get("targets") or []}
    if len(_recent_targets) >= _DIVERSITY_MIN:
        return True, f"调研目标扩展: {len(_recent_targets)}个不同目标"
    # 4) 相对更早轮次出现新目标（窗口多样性不足但方向在变）
    _earlier_targets = {t for r in _earlier_rounds for t in r.get("targets") or []}
    _new_targets = _recent_targets - _earlier_targets
    if _earlier_targets and _new_targets:
        preview = sorted(_new_targets)[:3]
        return True, f"新调研目标: {preview}"
    return False, ""


def judge_loop_verdict(history: list) -> tuple[str, str]:
    """死循环判定：同模式 / 变参绕圈 → stuck；有推进 → progressing；否则 stuck。

    变参绕圈：最近窗口内 round_sig 种数很少（≤2）且轮次足够，例如
    read(A)/read(B) 来回。同模式是其特例（种数=1）。

    权衡：窗口内 ≥3 个不同调研目标视为推进，会漏杀"每次换新参数的长绕圈"；
    降级靠撞线 progressing 软收尾 + 深度/步数保险丝，避免把纯调研误掐。
    """
    _recent = last_n_tool_rounds(history, _LOOP_WINDOW)
    _reasons: list[str] = []
    _same = False
    _cycling = False
    if len(_recent) >= _LOOP_WINDOW:
        _sigs = [r["sig"] for r in _recent]
        _unique_sigs = set(_sigs)
        _same = len(_unique_sigs) == 1
        if _same:
            _reasons.append(f"连续{len(_recent)}轮同模式({_sigs[0][:60]})")
        elif len(_unique_sigs) <= _CYCLE_UNIQUE_MAX:
            _cycling = True
            _reasons.append(
                f"连续{len(_recent)}轮变参绕圈（{len(_unique_sigs)}种签名循环）"
            )
    _progress, _p_reason = has_progress_signal(history, _recent)
    # 同模式 / 小集合循环优先于推进信号：A/B 来回即使目标相对更早是新的，仍是绕圈。
    if _same or _cycling:
        return ("stuck", "；".join(_reasons) or "连续同模式/变参绕圈")
    if not _progress:
        _reasons.append("最近5轮无推进信号（无写入/新工具种类/新调研目标）")
        return ("stuck", "；".join(_reasons) or "连续同模式/无推进")
    return ("progressing", f"仍在推进（{_p_reason}）")
