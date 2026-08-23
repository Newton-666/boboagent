"""core/loop_detect.py — 死循环检测（E4b：从 engine 搬出，骨干通信"观察部"雏形）。

纯函数 + history 参数化，不持有 engine 引用。engine 侧保留薄壳委托（行为不变）。
保守方向：宁可判 progressing（软提醒）也不误掐正在推进的回合。
"""
import json

_WRITE_TOOLS = {"edit_file", "file_operation", "file_writer", "task_ledger"}


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
        try:
            _args = json.dumps(json.loads(_args), sort_keys=True, ensure_ascii=False)
        except Exception:
            pass
        _parts.append(f"{_name}|{_args}")
    return "::".join(sorted(_parts))


def last_n_tool_rounds(history: list, n: int = 5) -> list:
    """从 history 取最近 n 轮（带 tool_calls 的 assistant 消息）的签名与工具名。"""
    _rounds = []
    for _m in reversed(history):
        if _m.get("role") == "assistant" and _m.get("tool_calls"):
            _names = [_tc.get("function", {}).get("name", "")
                      for _tc in _m["tool_calls"]
                      if _tc.get("function", {}).get("name")]
            _rounds.append({"sig": round_sig(_m["tool_calls"]), "names": _names})
            if len(_rounds) >= n:
                break
    return _rounds


def has_progress_signal(history: list, recent: list) -> tuple[bool, str]:
    """最近 n 轮是否有推进信号：文件写入/diff、台账变更、新工具种类。

    轮级判定全部从 history 最近 n 轮取（recent 参数）——tracker._change_log
    是会话累计列表，不能直接判"本轮有写入"（累计非空 ≠ 最近 n 轮有推进）。
    """
    # 1) 文件写入/diff / 台账变更：最近 n 轮内出现写类工具调用
    for _r in recent:
        for _name in _r["names"]:
            if _name in _WRITE_TOOLS:
                return True, f"写类工具调用: {_name}"
    # 2) 新工具种类：最近 n 轮用过的工具名集合 ⊄ 更早轮次集合
    _recent_names = {n for r in recent for n in r["names"]}
    _earlier = set()
    _count = 0
    for _m in reversed(history):
        if _m.get("role") == "assistant" and _m.get("tool_calls"):
            if _count >= len(recent):
                for _tc in _m["tool_calls"]:
                    _nm = _tc.get("function", {}).get("name", "")
                    if _nm:
                        _earlier.add(_nm)
            _count += 1
    _new = _recent_names - _earlier
    # 更早轮次为空（会话刚开始即撞线，无从对比）→ 不判"新工具种类"推进
    if _earlier and _new:
        return True, f"新工具种类: {sorted(_new)[:3]}"
    return False, ""


def judge_loop_verdict(history: list) -> tuple[str, str]:
    """死循环判定：连续 5 轮同模式 或 无推进信号 → stuck，否则 progressing。"""
    _recent = last_n_tool_rounds(history, 5)
    _reasons: list[str] = []
    _same = False
    if len(_recent) >= 5:
        _sigs = [r["sig"] for r in _recent]
        _same = all(s == _sigs[0] for s in _sigs)
        if _same:
            _reasons.append(f"连续{len(_recent)}轮同模式({_sigs[0][:60]})")
    _progress, _p_reason = has_progress_signal(history, _recent)
    if not _progress:
        _reasons.append("最近5轮无推进信号（无文件写入/台账变更/新工具种类）")
    if _same or not _progress:
        return ("stuck", "；".join(_reasons) or "连续同模式/无推进")
    return ("progressing", f"仍在推进（{_p_reason}）")
