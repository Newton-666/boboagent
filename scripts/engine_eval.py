"""engine_eval.py — 重构前后评估（token / 速度 / 准确度）

用法（在任一代码状态下运行）：
    python3 scripts/engine_eval.py > /tmp/eval_<state>.json

输出：每场景 {call_count, total_tokens, elapsed_ms, finals_content}。
比较：两次输出逐场景对比——finals 内容一致 = 准确度不变；
      call_count/total_tokens 变化 = 重构对消耗的影响；elapsed 变化 = 速度。
"""
import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_FIXED_USAGE = {"prompt_tokens": 120, "completion_tokens": 80, "total_tokens": 200}


class EvalCaller:
    """计数 + 固定 usage 的 mock caller（两个代码状态用同一实现，公平对比）。"""

    def __init__(self, responses: list):
        self.responses = list(responses)
        self.call_count = 0

    def __call__(self, messages, use_tools=True, stream_callback=None,
                 retry_callback=None, tools_override=None, **kwargs):
        idx = self.call_count
        self.call_count += 1
        if idx >= len(self.responses):
            return {"choices": [{"message": {"content": ""}}], "usage": _FIXED_USAGE}
        resp = self.responses[idx]
        if isinstance(resp, dict) and resp.get("choices"):
            resp.setdefault("usage", _FIXED_USAGE)
        return resp


def text_response(text: str) -> dict:
    return {"choices": [{"message": {"content": text}}], "usage": _FIXED_USAGE}


def tool_response(name: str, args: dict = None) -> dict:
    return {"choices": [{"message": {"content": "", "tool_calls": [
        {"id": "c1", "type": "function",
         "function": {"name": name, "arguments": str(args or {})}}
    ]}}], "usage": _FIXED_USAGE}


def _build_engine(auto: bool):
    from core.engine import Engine
    from core.tool_executor import execute_tool

    eng = Engine(EvalCaller([]), execute_tool, test_mode=False)
    eng.test_mode = False
    eng.proactive.mode = "off"
    eng._auto_mode_getter = (lambda: True) if auto else (lambda: False)
    eng.confirm_callback = lambda *a, **k: False
    return eng


def run_scenario(spec: dict) -> dict:
    from core.event_bus import event_bus

    tmpdir = tempfile.mkdtemp(prefix="bobo_eval_")
    event_bus.reset(tmpdir)
    event_bus._log_path = type(event_bus._log_path)(tmpdir) / "events.jsonl"

    caller = EvalCaller(spec["responses"])
    from core.tool_executor import execute_tool
    from core.engine import Engine

    eng = Engine(caller, execute_tool, test_mode=False)
    eng.test_mode = False
    eng.proactive.mode = "off"
    eng._auto_mode_getter = (lambda: True) if spec["auto"] else (lambda: False)
    eng.confirm_callback = lambda *a, **k: False

    finals = []
    eng.callback = lambda etype, data: finals.append(
        data.get("content") or ""
    ) if etype == "complete" else None

    t0 = time.time()
    eng.run(spec["input"])
    elapsed_ms = int((time.time() - t0) * 1000)

    return {
        "name": spec["name"],
        "call_count": caller.call_count,
        "total_tokens": caller.call_count * 200,  # 固定 usage 换算
        "elapsed_ms": elapsed_ms,
        "finals": finals,
        "state": eng.state,
    }


SCENARIOS = [
    dict(name="N1_plain_chat", auto=False, input="你好",
         responses=[text_response("你好！我是 Bobo。")]),
    dict(name="N2_tool_round", auto=False, input="现在几点了",
         responses=[tool_response("get_current_time"),
                    text_response("现在是下午3点。")]),
    dict(name="N3_write_denied", auto=False, input="帮我提交代码",
         responses=[tool_response("execute_terminal", {"command": "git push origin main"}),
                    text_response("命令未获批准，已取消操作。")]),
    dict(name="A1_auto_readonly", auto=True, input="看下仓库状态",
         responses=[tool_response("execute_terminal", {"command": "git status"}),
                    text_response("仓库状态已查看。")]),
    dict(name="A2_auto_write_denied", auto=True, input="推送代码",
         responses=[tool_response("execute_terminal", {"command": "git push origin main"}),
                    text_response("推送被用户拒绝。")]),
    dict(name="P1_promise_reinject", auto=False, input="修一下这个bug",
         responses=[text_response("好的，我会继续修复这个问题。"),
                    text_response("已完成修复，测试通过。")]),
]


def main():
    results = []
    for spec in SCENARIOS:
        # 跑 3 次取中位耗时（降噪），调用数/token 取第 1 次
        first = run_scenario(spec)
        times = [first["elapsed_ms"]]
        for _ in range(2):
            times.append(run_scenario(spec)["elapsed_ms"])
        times.sort()
        first["elapsed_ms_median"] = times[1]
        results.append(first)
        print(json.dumps({k: v for k, v in first.items() if k != "finals"},
                         ensure_ascii=False), flush=True)
    with open("/tmp/engine_eval_finals.json", "w", encoding="utf-8") as f:
        json.dump({r["name"]: r["finals"] for r in results}, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
