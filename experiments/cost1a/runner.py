#!/usr/bin/env python3
"""最小 agent loop 打真实 API（TICKET-COST-1A-SANDBOX）。

- 直接调 DeepSeek API（复用 core.llm_caller 的成熟调用链，只读不改）
- API key 只从 data/.env 读（经 config.py 加载）
- 记录每轮 usage（prompt_tokens / prompt_cache_hit_tokens）、首 token 延迟、总耗时、
  工具调用次数、成功率、B 档 action 选错率
- 每档×每题×5 次取中位数，结果 JSON 落盘 experiments/cost1a/results/
"""

from __future__ import annotations

import json
import os
import shutil
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from config import API_KEY, API_BASE_URL, API_MODEL_NAME  # noqa: E402
from core.llm_caller import create_llm_caller  # noqa: E402

from experiments.cost1a import configs, tasks, tools_impl  # noqa: E402

RESULTS_DIR = Path(__file__).resolve().parent / "results"
MAX_STEPS = 8

SYSTEM_PROMPT = (
    "你是沙盒实验助手，在一个受限工作区里完成任务。"
    "可用工具见 schema。工具调用后你会收到真实结果。"
    "完成任务后在最终回复中简要说明。不要编造工具结果。"
)


def _sum_usage(acc: dict, usage: dict | None):
    usage = usage or {}
    for k in ("prompt_tokens", "completion_tokens", "prompt_cache_hit_tokens",
              "prompt_cache_miss_tokens", "total_tokens"):
        acc[k] = acc.get(k, 0) + int(usage.get(k, 0) or 0)


def run_once(cfg_key: str, task_id: str, run_idx: int = 0) -> dict:
    """跑单次（一档一题一次），返回指标 dict。"""
    sandbox_root = RESULTS_DIR / cfg_key / task_id / f"run{run_idx}"
    if sandbox_root.exists():
        shutil.rmtree(sandbox_root)
    sandbox_root.mkdir(parents=True)
    tools_impl.set_sandbox(sandbox_root)
    tasks.SETUPS[task_id](sandbox_root)

    schema = configs.CONFIGS[cfg_key]()
    caller = create_llm_caller(API_KEY, API_BASE_URL, API_MODEL_NAME, schema)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": tasks.TASK_PROMPTS[task_id]},
    ]

    usage_acc = {}
    ttfts: list[float] = []
    calls: list[dict] = []
    tool_call_count = 0
    repeated: set[tuple] = set()
    repeat_count = 0
    final_reply = ""
    start = time.time()

    for step in range(MAX_STEPS):
        first_chunk_at: float | None = None

        def _cb(chunk: str):
            nonlocal first_chunk_at
            if first_chunk_at is None:
                first_chunk_at = time.time()

        t0 = time.time()
        try:
            resp = caller(messages, use_tools=True, stream_callback=_cb,
                          max_tokens=2048)
        except Exception as e:
            return {
                "cfg": cfg_key, "task": task_id, "run": run_idx,
                "error": f"LLM 调用异常: {type(e).__name__}: {e}",
                "success": False, "tool_calls": tool_call_count,
                "prompt_tokens": usage_acc.get("prompt_tokens", 0),
                "prompt_cache_hit_tokens": usage_acc.get("prompt_cache_hit_tokens", 0),
                "total_ms": int((time.time() - start) * 1000),
                "ttft_ms": None,
            }
        if first_chunk_at is not None:
            ttfts.append((first_chunk_at - t0) * 1000)

        _sum_usage(usage_acc, resp.get("usage"))
        if "error" in resp or not resp.get("choices"):
            # API 返回错误（限流/超时/无效请求）→ 记 error 结束本次
            err = resp.get("error", "choices 缺失")
            return {
                "cfg": cfg_key, "task": task_id, "run": run_idx,
                "error": f"LLM 返回异常: {err}", "success": False,
                "tool_calls": tool_call_count,
                "prompt_tokens": usage_acc.get("prompt_tokens", 0),
                "prompt_cache_hit_tokens": usage_acc.get("prompt_cache_hit_tokens", 0),
                "total_ms": int((time.time() - start) * 1000),
                "ttft_ms": round(statistics.median(ttfts), 1) if ttfts else None,
            }
        choice = (resp.get("choices") or [{}])[0]
        msg = choice.get("message", {})
        content = msg.get("content") or ""
        tc_list = msg.get("tool_calls") or []

        if not tc_list:
            final_reply = content.strip()
            break

        for tc in tc_list:
            fn = tc.get("function", {})
            name = fn.get("name", "")
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            result_text, action = tools_impl.dispatch(name, args)
            tool_call_count += 1
            key = (name, json.dumps(args, sort_keys=True, ensure_ascii=False))
            if key in repeated:
                repeat_count += 1
            repeated.add(key)
            calls.append({"tool": name, "args": args, "action": action})
            # DeepSeek 推理模式硬性要求：assistant 消息必须原样回传 reasoning_content
            messages.append({"role": "assistant",
                             "content": content or None,
                             "reasoning_content": resp.get("reasoning", ""),
                             "tool_calls": [tc]})
            messages.append({"role": "tool", "tool_call_id": tc.get("id", ""),
                             "content": result_text})
    else:
        # 达到步数上限未收尾
        final_reply = final_reply or "（步数上限，未给出最终回复）"

    passed, detail = tasks.judge(task_id, sandbox_root, final_reply, calls)

    # B 档 action 选错率（任务 5：期望 write/append）
    action_errors = 0
    family_calls = [c for c in calls if c["tool"].endswith("_tool")]
    expected = tasks.EXPECTED_ACTIONS.get(task_id)
    if expected:
        for c in family_calls:
            if c.get("action") not in expected:
                action_errors += 1

    return {
        "cfg": cfg_key, "task": task_id, "run": run_idx,
        "success": passed, "judge_detail": detail,
        "tool_calls": tool_call_count,
        "repeat_calls": repeat_count,
        "family_calls": len(family_calls),
        "action_errors": action_errors,
        "prompt_tokens": usage_acc.get("prompt_tokens", 0),
        "prompt_cache_hit_tokens": usage_acc.get("prompt_cache_hit_tokens", 0),
        "total_ms": int((time.time() - start) * 1000),
        "ttft_ms": round(statistics.median(ttfts), 1) if ttfts else None,
        "steps": min(len([m for m in messages if m["role"] == "assistant"]), MAX_STEPS),
    }


def _median(key: str, rows: list[dict]) -> float | None:
    vals = [r[key] for r in rows if isinstance(r.get(key), (int, float))]
    return round(statistics.median(vals), 1) if vals else None


def run_experiment(cfg_keys=None, task_ids=None, repeats: int = 5) -> dict:
    """全实验：每档×每题×5 次取中位数。返回汇总 JSON。"""
    cfg_keys = cfg_keys or list(configs.CONFIGS)
    task_ids = task_ids or tasks.TASKS
    summary = {}
    raw = {}
    for cfg in cfg_keys:
        for tid in task_ids:
            rows = []
            for i in range(repeats):
                r = run_once(cfg, tid, i)
                rows.append(r)
            raw[f"{cfg}/{tid}"] = rows
            success_rate = round(sum(1 for r in rows if r.get("success")) / len(rows), 3)
            summary[f"{cfg}/{tid}"] = {
                "cfg": cfg, "task": tid, "repeats": len(rows),
                "success_rate": success_rate,
                "prompt_tokens": _median("prompt_tokens", rows),
                "prompt_cache_hit_tokens": _median("prompt_cache_hit_tokens", rows),
                "total_ms": _median("total_ms", rows),
                "ttft_ms": _median("ttft_ms", rows),
                "tool_calls": _median("tool_calls", rows),
                "repeat_calls": _median("repeat_calls", rows),
                "action_errors": _median("action_errors", rows),
                "family_calls": _median("family_calls", rows),
            }
    os.makedirs(RESULTS_DIR, exist_ok=True)
    out = {"summary": summary, "raw": raw,
           "config_counts": configs.validate(),
           "api_model": API_MODEL_NAME}
    (RESULTS_DIR / "experiment_results.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def main():
    import argparse
    ap = argparse.ArgumentParser(description="COST-1A 沙盒实验")
    ap.add_argument("--cfg", default=None, help="逗号分隔档位 A,B,C,D")
    ap.add_argument("--task", default=None, help="逗号分隔任务 t1_bugfix,...")
    ap.add_argument("--repeats", type=int, default=5)
    args = ap.parse_args()
    cfgs = args.cfg.split(",") if args.cfg else None
    tids = args.task.split(",") if args.task else None
    out = run_experiment(cfgs, tids, args.repeats)
    print(f"完成: {len(out['summary'])} 组实验，结果 -> {RESULTS_DIR / 'experiment_results.json'}")
    for k, v in sorted(out["summary"].items()):
        print(f"  {k}: 成功率={v['success_rate']} prompt_tokens={v['prompt_tokens']} "
              f"cache_hit={v['prompt_cache_hit_tokens']} total_ms={v['total_ms']} "
              f"ttft_ms={v['ttft_ms']} calls={v['tool_calls']}")


if __name__ == "__main__":
    main()
