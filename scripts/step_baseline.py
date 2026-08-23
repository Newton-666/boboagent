"""step_baseline.py — _step() 行为基线录制与比对（票 TICKET-DEMOLISH-OFFICE-DUO 批 D0）。

用法：
    python scripts/step_baseline.py record    # 录制当前行为 → data/eval/step_baseline/pre_demolish/
    python scripts/step_baseline.py compare    # 重跑同剧本，与已录基线 diff（退出码 0=一致）

基线内容（每场景一份 JSON）：
  - events: 事件序列（仅 type + 关键字段，剥离 ts/session_id 等时序噪音）
  - history: 完整对话历史（role + content 摘要化）
  - final: 终稿文本

录制条件（前后必须一致）：
  - MockLLMCaller（无网络）；test_mode=False（走 _confirm 全流程）
  - proactive.mode = "off"（沉淀线程为后台 daemon，时序不确定——本基线不含沉淀行为；
    沉淀路径由 E4a 系测试守护，不在本基线职责内）
  - confirm_callback 恒 False（模拟用户拒绝弹窗）

场景覆盖（auto 与 office 拆除相关的全部路径）：
  N1 普通模式纯聊天          N2 普通模式工具轮
  N3 普通模式写命令被拒      A1 auto 纯读 git 放行
  A2 auto 写命令走弹窗被拒   P1 承诺检测闸回注（普通模式）
"""
import json
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASELINE_DIR = os.path.join("data", "eval", "step_baseline", "pre_demolish")

# 时序噪音归一化：真实时钟/耗时等每次必变的值 → 占位符（diff=0 判定只针对行为，不针对钟表）
_NOISE_PATTERNS = [
    (re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}"), "<DATETIME>"),
    (re.compile(r"耗时: [\d.]+s"), "耗时: <N>s"),
    # 票 L1 工作区对账注入：内容 = 施工现场的 git status，本质是环境快照非行为——
    # 基线录制与拆除施工共用一个工作区时必变，剥离（D1 施工中实证发现）
    (re.compile(r"\n\n── 工作区实况（收工对账，只读）──.*", re.S), "\n\n<RECON>"),
]


def _norm(text: str) -> str:
    for pat, rep in _NOISE_PATTERNS:
        text = pat.sub(rep, text)
    return text

# 事件字段中需要保留的键（其余如 ts/session_id 为时序或环境噪音，剥离）
_EVENT_KEYS = ("type", "from", "to", "reason", "tool", "name", "status", "error")


def _slim_event(raw: dict) -> dict:
    out = {}
    for k in _EVENT_KEYS:
        if k in raw and raw[k] not in ("", None):
            out[k] = raw[k]
    return out


def _slim_history(history: list) -> list:
    out = []
    for m in history:
        role = m.get("role")
        content = m.get("content") or ""
        tc = m.get("tool_calls")
        entry = {"role": role}
        if isinstance(content, str) and content:
            entry["content"] = _norm(content)[:200]
        elif isinstance(content, list):
            entry["content"] = " ".join(
                str(c.get("text", ""))[:80] for c in content if isinstance(c, dict)
            )[:200]
        if tc:
            entry["tool_calls"] = [t.get("function", {}).get("name") for t in tc]
        if m.get("tool_call_id"):
            entry["tool_call_id"] = m["tool_call_id"]
        out.append(entry)
    return out


def _build_engine(auto: bool):
    from core.engine import Engine
    from core.tool_executor import execute_tool
    from tests.mock_llm import MockLLMCaller

    caller = MockLLMCaller([])
    eng = Engine(caller, execute_tool, test_mode=False)
    eng.test_mode = False
    eng.proactive.mode = "off"
    eng._auto_mode_getter = (lambda: True) if auto else (lambda: False)
    eng.confirm_callback = lambda *a, **k: False  # 模拟用户恒拒弹窗
    return eng


def _run_scenario(spec: dict) -> dict:
    import logging
    logging.disable(logging.CRITICAL)

    from core.event_bus import event_bus
    from tests.mock_llm import MockLLMCaller

    tmpdir = tempfile.mkdtemp(prefix="bobo_baseline_")
    event_bus.reset(tmpdir)
    # reset 返回单例但 _log_path 已指 tmpdir；再显式确认（Windows 安全写法）
    event_bus._log_path = type(event_bus._log_path)(tmpdir) / "events.jsonl"

    eng = _build_engine(spec["auto"])
    eng.llm_caller.responses = list(spec["responses"])

    finals = []
    eng.callback = lambda etype, data: finals.append(
        {"event": etype, "content": (data.get("content") or "")[:300]}
    ) if etype == "complete" else None

    eng.run(spec["input"])

    events = []
    with open(event_bus._log_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    events.append(_slim_event(json.loads(line)))
                except ValueError:
                    events.append({"type": "UNPARSEABLE_LINE"})

    logging.disable(logging.NOTSET)
    return {
        "spec": {k: spec[k] for k in ("name", "auto", "input")},
        "events": events,
        "history": _slim_history(eng.history),
        "finals": finals,
        "final_state": eng.state,
    }


# ── 场景剧本（固定 responses = 固定行为）─────────────────────────────
from tests.mock_llm import text_response, tool_response

SCENARIOS = [
    dict(name="N1_normal_plain_chat", auto=False, input="你好",
         responses=[text_response("你好！我是 Bobo。")]),
    dict(name="N2_normal_tool_round", auto=False, input="现在几点了",
         responses=[tool_response("get_current_time"),
                    text_response("现在是下午3点。")]),
    dict(name="N3_normal_write_denied", auto=False, input="帮我提交代码",
         responses=[tool_response("execute_terminal",
                                  {"command": "git push origin main"}),
                    text_response("命令未获批准，已取消操作。")]),
    dict(name="A1_auto_readonly_git", auto=True, input="看下仓库状态",
         responses=[tool_response("execute_terminal", {"command": "git status"}),
                    text_response("仓库状态已查看，工作区有改动。")]),
    dict(name="A2_auto_write_popup_denied", auto=True, input="推送代码",
         responses=[tool_response("execute_terminal",
                                  {"command": "git push origin main"}),
                    text_response("推送被用户拒绝。")]),
    dict(name="P1_promise_gate_reinject", auto=False, input="修一下这个bug",
         responses=[text_response("好的，我会继续修复这个问题。"),
                    text_response("已完成修复，测试通过。")]),
]


def cmd_record():
    os.makedirs(BASELINE_DIR, exist_ok=True)
    for spec in SCENARIOS:
        result = _run_scenario(spec)
        path = os.path.join(BASELINE_DIR, spec["name"] + ".json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=1)
        print(f"recorded {spec['name']}: "
              f"{len(result['events'])} events, {len(result['history'])} history msgs")
    print(f"baseline dir: {BASELINE_DIR}")


def cmd_compare() -> int:
    import difflib
    failures = 0
    for spec in SCENARIOS:
        path = os.path.join(BASELINE_DIR, spec["name"] + ".json")
        if not os.path.exists(path):
            print(f"MISSING BASELINE: {spec['name']}")
            failures += 1
            continue
        with open(path, encoding="utf-8") as f:
            old = json.load(f)
        new = _run_scenario(spec)
        if old == new:
            print(f"OK    {spec['name']}")
            continue
        failures += 1
        print(f"DIFF  {spec['name']}")
        old_s = json.dumps(old, ensure_ascii=False, indent=1).splitlines()
        new_s = json.dumps(new, ensure_ascii=False, indent=1).splitlines()
        for line in difflib.unified_diff(old_s, new_s, "baseline", "current", lineterm=""):
            print("  " + line)
    if failures:
        print(f"\n{failures} scenario(s) DRIFTED — 行为漂移，禁止合入")
        return 1
    print("\nall scenarios match baseline — diff=0")
    return 0


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "record"
    if mode == "record":
        cmd_record()
    elif mode == "compare":
        sys.exit(cmd_compare())
    else:
        print(__doc__)
        sys.exit(2)
