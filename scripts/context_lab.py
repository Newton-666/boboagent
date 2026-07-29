#!/usr/bin/env python3
"""上下文实验台 — 用事件总线数据找压缩最优解。

只读分析脚本，不动任何引擎代码。

用法:
    python scripts/context_lab.py
    python scripts/context_lab.py --since 2026-07-29
    python scripts/context_lab.py --session abc123
    python scripts/context_lab.py --json
    python scripts/context_lab.py --compare --group-by-file A.jsonl B.jsonl
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

# ── 路径 ──
DEFAULT_EVENTS_PATH = Path(__file__).resolve().parent.parent / "data" / "logs" / "events.jsonl"


# ── IO ──


def load_events(path, since=None):
    """加载 events.jsonl 到 DataFrame，可选 --since 过滤时间。"""
    path = Path(path)
    if not path.exists():
        print(f"[context_lab] 错误: 文件不存在 {path}")
        sys.exit(1)

    records = []
    parse_errors = 0
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
                records.append(ev)
            except json.JSONDecodeError:
                parse_errors += 1

    if parse_errors:
        print(f"[context_lab] 警告: 跳过 {parse_errors} 行 JSON 解析错误")

    if not records:
        print("[context_lab] 事件文件为空")
        return pd.DataFrame()

    df = pd.DataFrame(records)
    df["ts"] = pd.to_numeric(df["ts"], errors="coerce")
    df["ts_dt"] = pd.to_datetime(df["ts"], unit="s", utc=True)

    if since:
        since_dt = pd.to_datetime(since, utc=True)
        df = df[df["ts_dt"] >= since_dt]

    df.sort_values("ts", inplace=True)
    return df


def _safe_int(val, default=0):
    try:
        return int(val) if pd.notna(val) else default
    except (ValueError, TypeError):
        return default


def _validate_thresholds(results, budget):
    """验证指定压缩预算阈值是否合理。"""
    total_tokens = sum(r.get("prompt_tokens", 0) for r in results.values())
    total_rounds = sum(r.get("rounds", 0) for r in results.values())
    avg_per_round = round(total_tokens / max(total_rounds, 1))
    ratio = round(avg_per_round / budget, 2) if budget > 0 else 0

    verdict = "合适" if ratio > 0.3 else "偏大（可考虑调低）"
    if ratio > 1.0:
        verdict = "偏小（压缩触发太频繁）"

    return {
        "budget": budget,
        "avg_token_per_round": avg_per_round,
        "budget_ratio": ratio,
        "verdict": verdict,
    }


# ── 指标计算 ──


def _calc_basic_stats(df, session_id):
    """基础统计。"""
    sdf = df[df["session_id"] == session_id].copy()
    if sdf.empty:
        return {}

    calls = sdf[sdf["type"] == "llm.call"]
    tools = sdf[sdf["type"] == "tool.exec"]
    exits = sdf[sdf["type"] == "engine.thread.exit"]

    total_prompt = _safe_int(calls["prompt_tokens"].sum())
    total_completion = _safe_int(calls["completion_tokens"].sum())
    total_tokens = _safe_int(calls["total_tokens"].sum())
    llm_count = len(calls)
    tool_count = len(tools)

    start_ts = sdf["ts"].min()
    end_ts = sdf["ts"].max()
    duration_sec = end_ts - start_ts if end_ts > start_ts else 0
    exit_reasons = exits["reason"].value_counts().to_dict() if not exits.empty else {}

    return {
        "session_id": session_id,
        "start_ts": start_ts,
        "end_ts": end_ts,
        "duration_sec": int(duration_sec),
        "llm_calls": llm_count,
        "tool_calls": tool_count,
        "prompt_tokens": int(total_prompt),
        "completion_tokens": int(total_completion),
        "total_tokens": int(total_tokens),
        "avg_prompt_per_call": round(total_prompt / llm_count, 1) if llm_count else 0,
        "exit_reasons": exit_reasons,
    }


def _calc_token_curve(sdf):
    """token 增长曲线。"""
    calls = sdf[sdf["type"] == "llm.call"].copy()
    if calls.empty:
        return []
    calls = calls.sort_values("ts")
    calls["cumsum_tokens"] = calls["prompt_tokens"].fillna(0).cumsum()
    return [
        {"ts": row["ts"], "cumsum": int(row["cumsum_tokens"]), "msg_count": int(row.get("msg_count", 0))}
        for _, row in calls.iterrows()
    ]


def _calc_compression_stats(sdf):
    """压缩统计。若无 context.compressed 事件，返回空。"""
    comp = sdf[sdf["type"] == "context.compressed"].copy()
    if comp.empty:
        return {"compression_count": 0}

    comp = comp.sort_values("ts")
    ratios = []
    for _, row in comp.iterrows():
        pre = _safe_int(row.get("pre_tokens", 0))
        post = _safe_int(row.get("post_tokens", 0))
        if pre > 0:
            ratios.append(round(post / pre, 3))
        else:
            ratios.append(None)

    return {"compression_count": len(comp), "efficiency_ratios": ratios}


def _calc_amnesia_signals(sdf):
    """失忆信号。"""
    comp = sdf[sdf["type"] == "context.compressed"].copy()
    tools = sdf[sdf["type"] == "tool.exec"].copy()
    calls = sdf[sdf["type"] == "llm.call"].copy()

    load_result_after_compress = 0
    msg_surges = 0

    if not comp.empty and not tools.empty:
        for _, crow in comp.iterrows():
            post_ts = crow["ts"]
            post_tools = tools[tools["ts"] > post_ts].head(10)
            load_result_after_compress += len(post_tools[post_tools["name"] == "load_result"])

    if not comp.empty and not calls.empty:
        for _, crow in comp.iterrows():
            post_calls = calls[calls["ts"] > crow["ts"]].head(5)
            if len(post_calls) >= 2:
                pre_msg = _safe_int(post_calls.iloc[0].get("msg_count", 0))
                post_msg = _safe_int(post_calls.iloc[-1].get("msg_count", 0))
                if post_msg > pre_msg * 1.5 and post_msg - pre_msg > 5:
                    msg_surges += 1

    return {
        "load_result_after_compress": load_result_after_compress,
        "msg_surges": msg_surges,
    }


def _calc_duration_dist(calls_df):
    """回合耗时分布。"""
    if calls_df.empty:
        return {"p50": 0, "p95": 0, "mean": 0, "count": 0}
    durations = calls_df["duration_ms"].dropna().astype(float)
    if durations.empty:
        return {"p50": 0, "p95": 0, "mean": 0, "count": 0}
    return {
        "p50": round(durations.quantile(0.5), 1),
        "p95": round(durations.quantile(0.95), 1),
        "mean": round(durations.mean(), 1),
        "count": int(len(durations)),
    }


def _calc_fault_stats(df):
    """故障统计。"""
    exits = df[df["type"] == "engine.thread.exit"]
    if exits.empty:
        return {"total_exits": 0, "reasons": {}}
    reasons = exits["reason"].value_counts().to_dict()
    return {"total_exits": int(len(exits)), "reasons": {k: int(v) for k, v in reasons.items()}}


# ── 会话分析 ──


def analyze_session(df, session_id):
    """分析单个会话。"""
    sdf = df[df["session_id"] == session_id]
    if sdf.empty:
        return {}

    basic = _calc_basic_stats(df, session_id)
    token_curve = _calc_token_curve(sdf)
    comp_stats = _calc_compression_stats(sdf)
    amnesia = _calc_amnesia_signals(sdf)
    calls = sdf[sdf["type"] == "llm.call"]
    durations = _calc_duration_dist(calls)
    fault = _calc_fault_stats(sdf)
    state_changes = sdf[sdf["type"] == "state.change"]
    round_count = len(state_changes[state_changes["to"] == "done"])

    return {
        **basic,
        "rounds": round_count,
        "token_curve": token_curve,
        "compression": comp_stats,
        "amnesia": amnesia,
        "duration": durations,
        "fault": fault,
    }


def analyze_all(df):
    """分析全部数据，按会话分组。"""
    sessions = df[df["session_id"].notna() & (df["session_id"] != "")]["session_id"].unique()
    results = {}
    for sid in sessions:
        result = analyze_session(df, sid)
        if result:
            results[sid] = result
    return results


# ── 终端报表 ──


def _ascii_bar(val, max_val, width=30):
    if max_val <= 0:
        return " " * width
    bar_len = int((val / max_val) * width)
    return "█" * max(1, bar_len) if val > 0 else "▏"


def _plot_token_curve(curve, width=40):
    """ASCII 折线图。"""
    if not curve:
        return "  (无数据)"
    cumsums = [p["cumsum"] for p in curve]
    msg_counts = [p.get("msg_count", 0) for p in curve]
    max_val = max(cumsums) or 1
    lines = ["  token 累积增长曲线（每 8 回合标注一次）:"]
    step = max(1, len(curve) // 8)
    for i, (cs, mc) in enumerate(zip(cumsums, msg_counts)):
        if i % step != 0 and i != len(curve) - 1:
            continue
        bar_len = max(1, int((cs / max_val) * width))
        marker = "█" * bar_len
        lines.append(f"  {cs:>7} {marker}  #{i+1}(mc={mc})")
    return "\n".join(lines)


def print_report(results, title="上下文实验台 — 会话级分析报告"):
    """打印完整终端报表。"""
    n_sessions = len(results)
    print("=" * 72)
    print(f"  {title}")
    print(f"  会话数: {n_sessions}")
    print("=" * 72)

    if n_sessions == 0:
        print("  (无会话数据)")
        print("=" * 72)
        return

    # 汇总表
    rows = []
    for sid, r in results.items():
        sid_short = sid[:16] + "..." if len(sid) > 16 else sid
        rows.append({
            "会话": sid_short,
            "LLM调用": r.get("llm_calls", 0),
            "工具调用": r.get("tool_calls", 0),
            "回合数": r.get("rounds", 0),
            "prompt_tk": r.get("prompt_tokens", 0),
            "avg_tk/轮": round(r.get("prompt_tokens", 0) / max(r.get("rounds", 1), 1)),
            "p50(ms)": r.get("duration", {}).get("p50", 0),
            "p95(ms)": r.get("duration", {}).get("p95", 0),
            "压缩": r.get("compression", {}).get("compression_count", 0),
            "失忆信号": r.get("amnesia", {}).get("load_result_after_compress", 0),
        })
    df_report = pd.DataFrame(rows)
    if not df_report.empty:
        print("\n  ▎会话摘要")
        print("-" * 72)
        print(df_report.to_string(index=False))
        print()

    # 全局汇总
    total_llm = sum(r.get("llm_calls", 0) for r in results.values())
    total_tool = sum(r.get("tool_calls", 0) for r in results.values())
    total_tokens = sum(r.get("prompt_tokens", 0) for r in results.values())
    total_rounds = sum(r.get("rounds", 0) for r in results.values())
    total_duration_sec = max(r.get("duration_sec", 0) for r in results.values())

    print("  ▎全局汇总")
    print(f"    总 LLM 调用:       {total_llm}")
    print(f"    总工具调用:        {total_tool}")
    print(f"    总 prompt_tokens:  {total_tokens}")
    print(f"    总回合数:          {total_rounds}")
    print(f"    平均 token/回合:   {round(total_tokens / max(total_rounds, 1))}")
    print(f"    平均 LLM 调用/轮:  {round(total_llm / max(total_rounds, 1), 1)}")
    print(f"    会话跨度(秒):      {total_duration_sec}")

    # 故障统计
    all_faults = defaultdict(int)
    for r in results.values():
        for reason, count in r.get("exit_reasons", {}).items():
            all_faults[reason] += count
    if all_faults:
        print("  ▎故障统计 (engine.thread.exit)")
        max_c = max(all_faults.values())
        for reason, count in sorted(all_faults.items(), key=lambda x: -x[1]):
            bar = _ascii_bar(count, max_c)
            print(f"    {reason:<15} {count:>4} {bar}")

    # 回合耗时
    all_p50s = [r.get("duration", {}).get("p50", 0) for r in results.values() if r.get("duration", {}).get("p50", 0) > 0]
    all_p95s = [r.get("duration", {}).get("p95", 0) for r in results.values() if r.get("duration", {}).get("p95", 0) > 0]
    if all_p50s:
        print("  ▎回合耗时 (ms)")
        print(f"    会话级 p50 中位数: {round(pd.Series(all_p50s).median(), 1)}")
        print(f"    会话级 p95 均值:   {round(pd.Series(all_p95s).mean(), 1)}")

    # 压缩活动
    comp_sessions = [(sid, r) for sid, r in results.items() if r.get("compression", {}).get("compression_count", 0) > 0]
    if comp_sessions:
        print("  ▎压缩活动")
        for sid, r in comp_sessions:
            comp = r["compression"]
            amn = r.get("amnesia", {})
            effs = [e for e in comp.get("efficiency_ratios", []) if e is not None]
            eff_str = f"均值 {pd.Series(effs).mean():.2%}" if effs else "N/A"
            print(f"    {sid[:20]:<20} 压缩{comp['compression_count']}次 | 效率 {eff_str} | load_result 后 {amn.get('load_result_after_compress', 0)}次")

    # token 曲线
    for sid, r in results.items():
        curve = r.get("token_curve", [])
        if curve:
            print(f"  ▎会话 {sid[:20]} token 增长曲线:")
            print(_plot_token_curve(curve))

    # 预算验证
    print("  ▎压缩预算验证")
    budget = 60
    validation = _validate_thresholds(results, budget)
    print(f"    当前 budget={budget}: avg_token_per_round={validation['avg_token_per_round']}, ratio={validation['budget_ratio']}, {validation['verdict']}")
    avg_tk = validation['avg_token_per_round']
    if avg_tk > 0:
        recommended_min = max(round(avg_tk * 0.5), 20)
        recommended_max = max(round(avg_tk * 2), 80)
        print(f"    推荐 budget 区间: {recommended_min} ~ {recommended_max} (avg_per_round * 0.5~2.0)")

    print("=" * 72)


def export_json(results, path=None):
    """导出 JSON 报表。"""
    output = json.dumps(results, indent=2, ensure_ascii=False, default=str)
    if path:
        Path(path).write_text(output, encoding="utf-8")
        print(f"[context_lab] JSON 已导出: {path}")
    return output


# ── 入口 ──


def main():
    parser = argparse.ArgumentParser(description="上下文实验台 — 用事件总线数据找压缩最优解")
    parser.add_argument("--path", default=str(DEFAULT_EVENTS_PATH),
                        help=f"events.jsonl 路径（默认 {DEFAULT_EVENTS_PATH}）")
    parser.add_argument("--since", help="过滤起始日期，如 2026-07-29")
    parser.add_argument("--session", help="分析单个会话 ID")
    parser.add_argument("--json", action="store_true", help="JSON 导出")
    parser.add_argument("--json-path", help="JSON 导出路径")
    parser.add_argument("--compare", action="store_true", help="对比模式")
    parser.add_argument("--group-by-file", nargs="+", help="多文件对比")
    args = parser.parse_args()

    if args.compare and args.group_by_file:
        print(f"[context_lab] 对比模式: {args.group_by_file}")
        labels = [Path(f).stem for f in args.group_by_file]
        dataframes = [load_events(f, args.since) for f in args.group_by_file]
        results = {}
        for label, df in zip(labels, dataframes):
            results[label] = analyze_all(df)
        for label in labels:
            print()
            print_report(results.get(label, {}), title=f"对比: {label}")
        if args.json or args.json_path:
            export_json(results, args.json_path)
        return

    df = load_events(args.path, args.since)
    if df.empty:
        print("[context_lab] 无活动事件数据")
        return

    print(f"[context_lab] 加载 {len(df)} 事件，{df['type'].nunique()} 种类型")

    if args.session:
        result = analyze_session(df, args.session)
        if result:
            print_report({args.session: result})
            if args.json or args.json_path:
                export_json({args.session: result}, args.json_path)
        else:
            print(f"[context_lab] 未找到会话 {args.session}")
    else:
        results = analyze_all(df)
        print_report(results)
        if args.json or args.json_path:
            export_json(results, args.json_path)


if __name__ == "__main__":
    main()
