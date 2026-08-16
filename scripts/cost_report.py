"""scripts/cost_report.py — COST-1b 每票消耗报告（纯读聚合，零写 metrics）。

用法（托管 Python = 项目 .venv/bin/python）：
  .venv/bin/python scripts/cost_report.py --branch feat/xxx
  .venv/bin/python scripts/cost_report.py --ticket TICKET-XXX
  .venv/bin/python scripts/cost_report.py --since 2026-08-16

从 data/metrics/rounds.jsonl 聚合该票总消耗：
  总 tokens（prompt+completion）、用户 prompt 剥离后的"调度层消耗"、
  缓存命中率、工具调用分布、repeat_reads Top 5。
输出 Markdown 表（stdout）+ 一张图 reports/cost_<branch>.png。

铁律：只读聚合，禁止修改 metrics 数据；字段缺失如实标注（缺=null 口径，禁止编造）。
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from config import BOBO_DATA_DIR  # noqa: E402

_ROUNDS_PATH = Path(BOBO_DATA_DIR) / "metrics" / "rounds.jsonl"
_REPORTS_DIR = _PROJECT_ROOT / "reports"


def load_rounds(path: Path | None = None) -> list[dict]:
    rows = []
    p = path or _ROUNDS_PATH
    if not p.exists():
        return rows
    with open(p, "r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            try:
                rows.append(json.loads(raw))
            except Exception:
                continue
    return rows


def filter_rows(rows: list[dict], branch: str = "", ticket: str = "", since: str = "") -> list[dict]:
    out = []
    for r in rows:
        if branch and r.get("branch") != branch:
            continue
        if ticket:
            r_t = (r.get("ticket") or "")
            r_b = (r.get("branch") or "")
            if ticket.upper() not in r_t.upper() and ticket.upper() not in r_b.upper():
                continue
        if since:
            ts = r.get("ts") or 0
            if ts < _since_ts(since):
                continue
        out.append(r)
    return out


def _since_ts(since: str) -> float:
    import time
    try:
        return time.mktime(time.strptime(since, "%Y-%m-%d"))
    except Exception:
        return 0.0


def aggregate(rows: list[dict]) -> dict:
    agg = {
        "rounds": len(rows),
        "prompt_tokens": 0, "completion_tokens": 0,
        "user_chars": 0, "user_chars_n": 0,
        "cache_hit": 0, "cache_miss": 0, "cache_n": 0,
        "tool_counter": Counter(),
        "tool_fail": 0,
        "repeat_counter": Counter(),
        "per_round": [],
    }
    for r in rows:
        u = r.get("usage") or {}
        pt = u.get("prompt_tokens")
        ct = u.get("completion_tokens")
        agg["prompt_tokens"] += pt if isinstance(pt, (int, float)) else 0
        agg["completion_tokens"] += ct if isinstance(ct, (int, float)) else 0
        uc = u.get("user_prompt_chars")
        if isinstance(uc, (int, float)):
            agg["user_chars"] += uc
            agg["user_chars_n"] += 1
        ch = u.get("cache_hit_tokens")
        cm = u.get("cache_miss_tokens")
        if isinstance(ch, (int, float)) and isinstance(cm, (int, float)):
            agg["cache_hit"] += ch
            agg["cache_miss"] += cm
            agg["cache_n"] += 1
        for t in r.get("tools") or []:
            name = t.get("name") or "?"
            agg["tool_counter"][name] += 1
            if t.get("error"):
                agg["tool_fail"] += 1
        for rr in r.get("repeat_reads") or []:
            agg["repeat_counter"][rr.get("target")] += rr.get("count", 0)
        agg["per_round"].append({
            "round": r.get("round"),
            "prompt": pt if isinstance(pt, (int, float)) else 0,
            "user": uc if isinstance(uc, (int, float)) else 0,
            "budget": r.get("budget") or {},
            "ts": r.get("ts"),
        })
    return agg


def render_markdown(agg: dict, rows: list[dict], branch: str, ticket: str) -> str:
    total = agg["prompt_tokens"] + agg["completion_tokens"]
    sched = agg["prompt_tokens"] - agg["user_chars"]
    cache_pct = None
    if agg["cache_n"] > 0:
        cache_pct = round(agg["cache_hit"] / (agg["cache_hit"] + agg["cache_miss"]) * 100, 1)
    lines = []
    lines.append(f"# Cost Report — {branch or ticket or '(全部)'}")
    lines.append("")
    lines.append("| 指标 | 值 |")
    lines.append("| --- | --- |")
    lines.append(f"| 轮数 | {agg['rounds']} |")
    lines.append(f"| 总 prompt tokens | {agg['prompt_tokens']} |")
    lines.append(f"| 总 completion tokens | {agg['completion_tokens']} |")
    lines.append(f"| 总 tokens | {total} |")
    if agg["user_chars_n"]:
        lines.append(f"| 用户输入（字符，不计入优化口径） | {agg['user_chars']}（{agg['user_chars_n']}/{agg['rounds']} 轮有值） |")
        lines.append(f"| 调度层消耗（总 prompt − 用户输入） | {sched} |")
    else:
        lines.append("| 用户输入 / 调度层消耗 | 未采集（user_prompt_chars 缺，链路未带） |")
    if cache_pct is not None:
        lines.append(f"| 缓存命中率 | {cache_pct}%（hit {agg['cache_hit']} / miss {agg['cache_miss']}，{agg['cache_n']} 轮有值） |")
    else:
        lines.append("| 缓存命中率 | 链路未透传 DeepSeek cache 字段（本轮取不到，落 null） |")
    lines.append("")
    lines.append("## 工具调用分布")
    lines.append("")
    lines.append("| 工具 | 次数 | 失败 |")
    lines.append("| --- | --- | --- |")
    for name, cnt in agg["tool_counter"].most_common(12):
        lines.append(f"| {name} | {cnt} | — |")
    lines.append("")
    lines.append("## 重复劳动 Top 5（read 类工具同 target 重复调用）")
    lines.append("")
    if agg["repeat_counter"]:
        lines.append("| target | 重复次数 |")
        lines.append("| --- | --- |")
        for tgt, cnt in agg["repeat_counter"].most_common(5):
            lines.append(f"| `{tgt}` | {cnt} |")
    else:
        lines.append("无（同 target 重复读取 count≥2 未出现）")
    lines.append("")
    return "\n".join(lines)


def setup_plot():
    """托管 matplotlib：Agg 后端 + 中文字体 fallback 链（macOS→Linux→Win）。"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    for name in ["PingFang SC", "Hiragino Sans GB", "Arial Unicode MS",
                 "Songti SC", "Noto Sans CJK SC", "Microsoft YaHei"]:
        try:
            font_manager.findfont(name, fallback_to_default=False)
            plt.rcParams["font.sans-serif"] = [name, "DejaVu Sans"]
            break
        except Exception:
            continue
    plt.rcParams["axes.unicode_minus"] = False
    return plt


def render_plot(agg: dict, branch: str, ticket: str, out_path: Path):
    plt = setup_plot()
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.6))

    # 左：最近 20 轮 prompt 拆解堆叠（用户灰 / 注入深灰 / 调度橙）
    per = agg["per_round"][-20:]
    ax = axes[0]
    if per:
        labels = [str(p.get("round", "")) for p in per]
        users = [p["user"] for p in per]
        injects = []
        for p in per:
            b = p["budget"] or {}
            inj = 0
            for k in ("system", "discipline", "memory", "pointers"):
                v = b.get(k)
                if isinstance(v, (int, float)):
                    inj += v
            injects.append(inj)
        prompts = [p["prompt"] for p in per]
        scheds = [max(0, pr - u - i) for pr, u, i in zip(prompts, users, injects)]
        ax.bar(labels, users, color="#b8b4a8", label="用户输入")
        ax.bar(labels, injects, bottom=users, color="#777", label="注入编排")
        ax.bar(labels, scheds, bottom=[u + i for u, i in zip(users, injects)], color="#e8913a", label="调度层")
        ax.set_title("每轮 prompt tokens 拆解（最近 20 轮）")
        ax.set_xlabel("Round")
        ax.set_ylabel("tokens / 字符（近似）")
        ax.legend(fontsize=8)
        plt.setp(ax.get_xticklabels(), rotation=45, fontsize=7)
    else:
        ax.text(0.5, 0.5, "无数据", ha="center", va="center")
        ax.set_title("每轮拆解（无数据）")

    # 右：repeat_reads Top 5（橙色，同警示色板）
    ax = axes[1]
    top = agg["repeat_counter"].most_common(5)
    if top:
        tgts = [t[:34] + "…" if len(t) > 34 else t for t, _ in top]
        cnts = [c for _, c in top]
        ax.barh(tgts[::-1], cnts[::-1], color="#e8913a")
        ax.set_title("重复劳动 Top 5（read 类同 target）")
        ax.set_xlabel("重复调用次数")
        plt.setp(ax.get_yticklabels(), fontsize=8)
    else:
        ax.text(0.5, 0.5, "无重复读取", ha="center", va="center")
        ax.set_title("重复劳动（无）")

    fig.suptitle(f"COST-1b · {branch or ticket or '全部'} · 轮数 {agg['rounds']}")
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=130)
    plt.close(fig)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="COST-1b 每票消耗报告")
    ap.add_argument("--branch", default="", help="按分支过滤（rounds.jsonl 的 branch 字段精确匹配）")
    ap.add_argument("--ticket", default="", help="按票号过滤（ticket 字段或分支名包含）")
    ap.add_argument("--since", default="", help="按时间过滤，如 2026-08-16")
    ap.add_argument("--rounds", default="", help="rounds.jsonl 路径覆盖（测试用）")
    ap.add_argument("--out", default="", help="图片输出路径覆盖（默认 reports/cost_<branch>.png）")
    args = ap.parse_args(argv)

    rows = load_rounds(Path(args.rounds) if args.rounds else None)
    rows = filter_rows(rows, branch=args.branch, ticket=args.ticket, since=args.since)
    if not rows:
        print("无匹配轮次（rounds.jsonl 为空或过滤条件无命中）")
        return 1
    agg = aggregate(rows)
    md = render_markdown(agg, rows, args.branch, args.ticket)
    print(md)
    name = args.branch or args.ticket or "all"
    name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
    out = Path(args.out) if args.out else (_REPORTS_DIR / f"cost_{name}.png")
    render_plot(agg, args.branch, args.ticket, out)
    print(f"\n图已落盘: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
