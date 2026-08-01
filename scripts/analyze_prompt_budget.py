#!/usr/bin/env python3
"""analyze_prompt_budget.py — prompt.budget 事件数据分析脚本。

票 LN-5：读取 event_bus 落盘的 events.jsonl，对 prompt.budget 和
prompt.budget.decision 事件做汇总统计，输出 JSON/表格/CSV 报告。

用法：
    python scripts/analyze_prompt_budget.py
    python scripts/analyze_prompt_budget.py --days 7 --output report.json
    python scripts/analyze_prompt_budget.py --format csv
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean

DEFAULT_EVENTS_PATH = Path(__file__).resolve().parent.parent / "data" / "logs" / "events.jsonl"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze prompt.budget events.")
    parser.add_argument(
        "--input", "-i", type=Path, default=DEFAULT_EVENTS_PATH,
        help="Path to events.jsonl (default: data/logs/events.jsonl)",
    )
    parser.add_argument(
        "--days", "-d", type=int, default=None,
        help="Only consider events from the last N days",
    )
    parser.add_argument(
        "--output", "-o", type=Path, default=None,
        help="Write report to file instead of stdout",
    )
    parser.add_argument(
        "--format", "-f", choices=["json", "csv", "text"], default="text",
        help="Output format (default: text)",
    )
    return parser.parse_args()


def iter_events(path: Path, since: datetime | None = None):
    """读取 JSONL 文件，过滤 prompt.budget 和 prompt.budget.decision 事件。"""
    if not path.exists():
        raise FileNotFoundError(f"Events file not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") not in ("prompt.budget", "prompt.budget.decision"):
                continue
            ts = event.get("ts")
            if since is not None and ts:
                # ts 是 Unix 秒级浮点
                dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                if dt < since:
                    continue
            yield event


def analyze(events: list[dict]) -> dict:
    """对事件做统计。"""
    if not events:
        return {"error": "no prompt.budget events found"}

    # 只处理 prompt.budget 做 sections 统计
    budget_events = [e for e in events if e.get("type") == "prompt.budget"]
    decision_events = [e for e in events if e.get("type") == "prompt.budget.decision"]

    section_samples: dict[str, list[int]] = defaultdict(list)
    total_chars_samples: list[int] = []
    truncated_count = 0
    evicted_counts: dict[str, list[int]] = defaultdict(list)
    topic_counts: dict[str, int] = defaultdict(int)
    timestamps: list[float] = []

    for event in budget_events:
        sections = event.get("sections", {})
        total_chars = event.get("total_chars", 0)
        total_chars_samples.append(total_chars)
        timestamps.append(event.get("ts", 0))

        for section_name, stats in sections.items():
            if isinstance(stats, dict):
                chars = stats.get("chars", 0)
                if chars is not None:
                    section_samples[section_name].append(chars)
                if stats.get("truncated"):
                    truncated_count += 1
                evicted = stats.get("evicted", 0)
                if evicted:
                    evicted_counts[section_name].append(evicted)
                if section_name == "note_pointers":
                    for topic in stats.get("topics", []):
                        topic_counts[topic] += 1
            else:
                # identity 是整数
                section_samples[section_name].append(stats)

    # 从 decision 事件补充 allocated/used 对比
    allocated_samples: dict[str, list[int]] = defaultdict(list)
    used_samples: dict[str, list[int]] = defaultdict(list)
    total_pool_samples: list[int] = []
    for event in decision_events:
        total_pool_samples.append(event.get("total_pool", 0))
        allocated = event.get("allocated", {})
        used = event.get("used", {})
        for section_name, value in allocated.items():
            allocated_samples[section_name].append(value)
        for section_name, value in used.items():
            used_samples[section_name].append(value)

    def _stats(samples: list[int]) -> dict:
        if not samples:
            return {"count": 0, "mean": 0, "min": 0, "max": 0}
        return {
            "count": len(samples),
            "mean": round(mean(samples), 1),
            "min": min(samples),
            "max": max(samples),
        }

    report = {
        "summary": {
            "total_events": len(events),
            "budget_events": len(budget_events),
            "decision_events": len(decision_events),
            "time_range": {
                "from": min(timestamps) if timestamps else None,
                "to": max(timestamps) if timestamps else None,
            },
        },
        "total_chars": _stats(total_chars_samples),
        "sections": {
            name: {
                "chars": _stats(samples),
                "allocated": _stats(allocated_samples.get(name, [])),
                "used": _stats(used_samples.get(name, [])),
                "evicted": {
                    "count": len(evicted_counts.get(name, [])),
                    "total": sum(evicted_counts.get(name, [])) or 0,
                },
            }
            for name, samples in section_samples.items()
        },
        "truncation_events": truncated_count,
        "total_pool": _stats(total_pool_samples),
        "top_note_topics": sorted(
            topic_counts.items(), key=lambda x: x[1], reverse=True
        )[:10],
    }
    return report


def format_text(report: dict) -> str:
    lines = []
    summary = report.get("summary", {})
    lines.append("# Prompt Budget Analysis Report")
    lines.append(f"Total events: {summary.get('total_events', 0)}")
    lines.append(f"  prompt.budget: {summary.get('budget_events', 0)}")
    lines.append(f"  prompt.budget.decision: {summary.get('decision_events', 0)}")
    lines.append("")

    total = report.get("total_chars", {})
    lines.append(f"Total chars: mean={total.get('mean')} min={total.get('min')} max={total.get('max')} count={total.get('count')}")
    lines.append("")

    lines.append("## Per-section stats")
    for name, data in report.get("sections", {}).items():
        chars = data.get("chars", {})
        allocated = data.get("allocated", {})
        used = data.get("used", {})
        evicted = data.get("evicted", {})
        lines.append(f"### {name}")
        lines.append(f"  chars: mean={chars.get('mean')} min={chars.get('min')} max={chars.get('max')} count={chars.get('count')}")
        if allocated.get("count"):
            lines.append(f"  allocated: mean={allocated.get('mean')} min={allocated.get('min')} max={allocated.get('max')}")
        if used.get("count"):
            lines.append(f"  used: mean={used.get('mean')} min={used.get('min')} max={used.get('max')}")
        if evicted.get("count"):
            lines.append(f"  evicted events: {evicted.get('count')} total evicted: {evicted.get('total')}")
    lines.append("")

    lines.append(f"## Truncation events: {report.get('truncation_events', 0)}")
    top_topics = report.get("top_note_topics", [])
    if top_topics:
        lines.append("## Top note pointer topics")
        for topic, count in top_topics:
            lines.append(f"  {topic}: {count}")
    return "\n".join(lines)


def format_csv(report: dict) -> str:
    import io
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["section", "metric", "count", "mean", "min", "max"])
    total = report.get("total_chars", {})
    writer.writerow(["total", "chars", total.get("count"), total.get("mean"), total.get("min"), total.get("max")])
    for name, data in report.get("sections", {}).items():
        chars = data.get("chars", {})
        writer.writerow([name, "chars", chars.get("count"), chars.get("mean"), chars.get("min"), chars.get("max")])
        allocated = data.get("allocated", {})
        if allocated.get("count"):
            writer.writerow([name, "allocated", allocated.get("count"), allocated.get("mean"), allocated.get("min"), allocated.get("max")])
        used = data.get("used", {})
        if used.get("count"):
            writer.writerow([name, "used", used.get("count"), used.get("mean"), used.get("min"), used.get("max")])
    return out.getvalue()


def main() -> int:
    args = parse_args()

    since = None
    if args.days is not None:
        since = datetime.now(timezone.utc) - timedelta(days=args.days)

    events = list(iter_events(args.input, since=since))
    report = analyze(events)

    if args.format == "json":
        output = json.dumps(report, ensure_ascii=False, indent=2)
    elif args.format == "csv":
        output = format_csv(report)
    else:
        output = format_text(report)

    if args.output:
        args.output.write_text(output, encoding="utf-8")
        print(f"Report written to {args.output}")
    else:
        print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
