# tools/health_report.py — 夜班体检报告（票 HR-1）
#
# 每天一份 bobo 健康日报：挖前一天 events.jsonl + 扫描 library/ 治理状态，
# 生成人话 markdown 报告，落盘 library/健康日报/YYYY-MM-DD.md。
#
# MVP 铁律：
#   - 零 LLM 调用：纯统计，确定性、零成本；叙事化总结以后再说。
#   - 幂等：同日重复生成 → 全量覆盖重写（内容一致）。
#   - 事件解析容错：坏行跳过不炸；events.jsonl 不存在 → 板块 1 标"无数据"。
#   - 失败静默降级：报告生成失败记 WARNING，不影响启动。
#   - 事件埋点：health.reported（date、sections ok）。
#
# 触发：
#   1. 启动补报：engine_adapter 初始化时 ensure_report()（缺昨天才生成）。
#   2. 手动：python -m tools.health_report [YYYY-MM-DD]（默认昨天）。

import json
import logging
import os
import re
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger("bobo.health_report")

# ── 库址 ──
_REPO_ROOT = Path(__file__).resolve().parent.parent
LIBRARY_DIR = _REPO_ROOT / "library"
EVENTS_PATH = _REPO_ROOT / "data" / "logs" / "events.jsonl"
KB_PATH = _REPO_ROOT / "data" / "knowledge_base.json"
HEALTH_DIR_NAME = "健康日报"


def _emit(event_type: str, data: dict):
    """事件埋点。写失败静默，绝不影响主流程。"""
    try:
        from core.event_bus import event_bus as _ebus
        _ebus.write(event_type, data)
    except Exception:
        pass


def _local_date(ts: float) -> str:
    """Unix 时间戳 → 本地日期 YYYY-MM-DD。"""
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")


def _day_range(date_str: str) -> tuple[float, float]:
    """给定日期 YYYY-MM-DD → [当日 00:00, 次日 00:00) 的 Unix 区间。"""
    d = datetime.strptime(date_str, "%Y-%m-%d")
    start = d.timestamp()
    end = (d + timedelta(days=1)).timestamp()
    return start, end


def _iter_events(events_path: Path, date_str: str):
    """按日过滤事件。坏行跳过不炸。返回迭代器 (event, ts)。"""
    start, end = _day_range(date_str)
    try:
        f = open(events_path, encoding="utf-8")
    except (OSError, IOError):
        return
    with f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            ts = e.get("ts")
            if not isinstance(ts, (int, float)):
                continue
            if start <= ts < end:
                yield e, ts


# ── 板块 1：引擎健康 ───────────────────────────────

def _engine_section(events_path: Path, date_str: str) -> list[str]:
    """引擎健康：events.jsonl 按日聚合。events 不存在 → ['- 无数据']。"""
    lines = []
    if not Path(events_path).exists():
        return ["- 无数据（events.jsonl 不存在）"]

    exit_reason = Counter()
    fuse_sessions = []
    gate = Counter()
    llm_calls = 0
    llm_err = Counter()
    stream_stall = 0
    headers_stall = 0
    tool_total = 0
    tool_failed = 0
    tool_has_status = False
    comp_count = 0
    comp_pre = 0
    comp_post = 0

    for e, ts in _iter_events(events_path, date_str):
        t = e.get("type", "")
        if t == "engine.thread.exit":
            exit_reason[e.get("reason", "unknown")] += 1
        elif t == "engine.step_fuse":
            fuse_sessions.append(e.get("session_id", "?"))
        elif t.startswith("goal_gate."):
            gate[t] += 1
        elif t == "llm.call":
            llm_calls += 1
            et = e.get("error_type")
            if et:
                llm_err[et] += 1
        elif t == "llm.stream_stall":
            stream_stall += 1
        elif t == "llm.headers_stall":
            headers_stall += 1
        elif t == "tool.exec":
            tool_total += 1
            if "status" in e:
                tool_has_status = True
                if e.get("status") != "ok" and e.get("status") != "success":
                    tool_failed += 1
        elif t == "context.compressed":
            comp_count += 1
            comp_pre += int(e.get("pre_msg_count", 0) or 0)
            comp_post += int(e.get("post_msg_count", 0) or 0)

    total_exits = sum(exit_reason.values())
    completed = exit_reason.get("completed", 0)
    max_steps = exit_reason.get("max_steps", 0)
    abnormal = total_exits - completed - max_steps
    if total_exits:
        lines.append(f"- 回合 {total_exits} 次：completed {completed} / "
                     f"max_steps {max_steps} / 异常 {abnormal}")
    else:
        lines.append("- 回合 0 次（当日无引擎线程）")

    if fuse_sessions:
        uniq = sorted(set(fuse_sessions))
        lines.append(f"- 步数熔断 {len(fuse_sessions)} 次：{', '.join(uniq[:5])}"
                     + (" 等" if len(uniq) > 5 else ""))

    if gate:
        parts = []
        if gate.get("goal_gate.no_ledger_detected"):
            parts.append(f"无账检测 {gate['goal_gate.no_ledger_detected']} 次")
        if gate.get("goal_gate.promise_detected"):
            parts.append(f"承诺检测 {gate['goal_gate.promise_detected']} 次")
        if gate.get("goal_gate.released"):
            parts.append(f"熔断放行 {gate['goal_gate.released']} 次 ⚠️")
        if parts:
            lines.append("- 收工闸：" + "，".join(parts))

    llm_line = f"- LLM 调用 {llm_calls} 次"
    err_parts = []
    if llm_err:
        err_parts.append("错误分类 " + " ".join(f"{k}×{v}" for k, v in llm_err.most_common()))
    if stream_stall:
        err_parts.append(f"stream_stall {stream_stall} 次")
    if headers_stall:
        err_parts.append(f"headers_stall {headers_stall} 次")
    if err_parts:
        llm_line += "：" + "；".join(err_parts)
    lines.append(llm_line)

    if tool_total:
        tool_line = f"- 工具调用 {tool_total} 次"
        if tool_has_status:
            tool_line += f"（失败 {tool_failed}）"
        lines.append(tool_line)

    if comp_count:
        lines.append(f"- 上下文压缩 {comp_count} 次："
                     f"{comp_pre} 条 → {comp_post} 条")

    return lines


# ── 板块 2：知识库治理 ──────────────────────────────

def _lev(a: str, b: str) -> int:
    """编辑距离（剪枝：长度差 >2 直接返回大值）。"""
    if abs(len(a) - len(b)) > 2:
        return 99
    dp = list(range(len(b) + 1))
    for i, c1 in enumerate(a, 1):
        prev = dp[0]
        dp[0] = i
        for j, c2 in enumerate(b, 1):
            tmp = dp[j]
            dp[j] = min(dp[j] + 1, dp[j - 1] + 1, prev + (c1 != c2))
            prev = tmp
    return dp[-1]


def _norm_topic(name: str) -> str:
    """主题名规范化：去空白/下划线/连字符，小写。"""
    return re.sub(r"[\s_\-]+", "", name or "").lower()


def _read_fm(path: Path) -> dict:
    """读取 frontmatter（无则返回空 dict）。"""
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return {}
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    fm = {}
    for line in text[3:end].splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip()
    return fm


def _scan_notes(library_dir: Path) -> list[dict]:
    """扫描主题笔记（排除 MEMORY.md / index.md / 健康日报目录）。"""
    notes = []
    if not Path(library_dir).exists():
        return notes
    for domain_dir in sorted(p for p in Path(library_dir).iterdir() if p.is_dir()):
        if domain_dir.name == HEALTH_DIR_NAME:
            continue
        for f in sorted(domain_dir.glob("*.md")):
            if f.stem in ("MEMORY", "index"):
                continue
            notes.append({
                "domain": domain_dir.name,
                "topic": f.stem,
                "path": f,
                "fm": _read_fm(f),
            })
    return notes


def _kb_stats(kb_path: Path) -> dict:
    """knowledge_base.json 统计：条目数 / 草稿数 / 信号<20 数。"""
    result = {"total": 0, "draft": 0, "signal_low": 0}
    try:
        with open(kb_path, encoding="utf-8") as f:
            kb = json.load(f)
        entries = kb.get("entries", []) if isinstance(kb, dict) else kb
        result["total"] = len(entries)
        for e in entries:
            if e.get("type") == "draft":
                result["draft"] += 1
            if (e.get("signal_score") or 0) < 20:
                result["signal_low"] += 1
    except Exception:
        pass
    return result


def _governance_section(library_dir: Path, kb_path: Path, date_str: str) -> list[str]:
    """知识库治理：library/ 扫描 + knowledge_base.json 统计。"""
    lines = []
    notes = _scan_notes(library_dir)

    # 主题笔记总数 + 昨日新增（created/last_touched == date_str）
    total = len(notes)
    new_today = sum(
        1 for n in notes
        if n["fm"].get("created") == date_str or n["fm"].get("last_touched") == date_str
    )
    line = f"- 主题笔记 {total} 篇"
    if new_today:
        line += f"（昨日 +{new_today}）"
    lines.append(line)

    # 疑似重复：规范化后编辑距离 ≤2 或互相包含
    dups = []
    for i in range(len(notes)):
        for j in range(i + 1, len(notes)):
            a = _norm_topic(notes[i]["topic"])
            b = _norm_topic(notes[j]["topic"])
            if not a or not b:
                continue
            if _lev(a, b) <= 2 or a in b or b in a:
                dups.append((notes[i]["topic"], notes[j]["topic"]))
    if dups:
        shown = "、".join(f"「{x}」~「{y}」" for x, y in dups[:3])
        lines.append(f"- 疑似重复：{shown}" + (" 等" if len(dups) > 3 else ""))

    # 孤儿笔记：无 frontmatter 或缺 topic 字段
    orphans = [n["topic"] for n in notes if not n["fm"] or not n["fm"].get("topic")]
    if orphans:
        lines.append(f"- 孤儿笔记 {len(orphans)} 篇：{'、'.join(orphans[:5])}"
                     + (" 等" if len(orphans) > 5 else ""))

    # 90 天未触达
    stale = []
    for n in notes:
        lt = n["fm"].get("last_touched")
        if lt:
            try:
                age = (datetime.strptime(date_str, "%Y-%m-%d")
                       - datetime.strptime(lt, "%Y-%m-%d")).days
                if age > 90:
                    stale.append(f"{n['topic']}（{age} 天）")
            except ValueError:
                pass
    if stale:
        lines.append(f"- 90 天未触达 {len(stale)} 篇：{'、'.join(stale[:5])}"
                     + (" 等" if len(stale) > 5 else ""))

    # MEMORY 统计
    kb = _kb_stats(kb_path)
    if kb["total"]:
        lines.append(f"- MEMORY 条目 {kb['total']} 条：草稿 {kb['draft']}，"
                     f"信号 <20 不再注入 {kb['signal_low']}")

    return lines


# ── 板块 3：异常关注 ────────────────────────────────

_ALERT_EVENT_PAT = re.compile(r"error|failed|stall|fuse|released", re.I)


def _alerts_section(events_path: Path, date_str: str) -> list[str]:
    """异常关注：需要用户或开发者看一眼的事。"""
    lines = []
    if not Path(events_path).exists():
        return ["- 无数据（events.jsonl 不存在）"]

    alerts = []
    err_counter = Counter()
    for e, ts in _iter_events(events_path, date_str):
        t = e.get("type", "")
        # 熔断放行
        if t == "goal_gate.released":
            alerts.append(f"熔断放行发生（{_local_date(ts)} "
                          f"{datetime.fromtimestamp(ts).strftime('%H:%M')}）")
        # balance_error
        if t == "llm.call" and e.get("error_type") in ("balance", "insufficient_quota"):
            alerts.append(f"balance_error 出现（{datetime.fromtimestamp(ts).strftime('%H:%M')}）")
        if "balance" in t.lower():
            alerts.append(f"{t} 出现（{datetime.fromtimestamp(ts).strftime('%H:%M')}）")
        # mirror 导入失败
        if t == "memory.mirror_import_failed":
            alerts.append(f"mirror_import_failed（{datetime.fromtimestamp(ts).strftime('%H:%M')}）")
        # notes.error
        if t == "notes.error":
            alerts.append(f"notes.error（{datetime.fromtimestamp(ts).strftime('%H:%M')}）")
        # error 级事件 top5 计数
        if _ALERT_EVENT_PAT.search(t):
            err_counter[t] += 1

    # 去重保序
    seen = set()
    for a in alerts:
        if a not in seen:
            seen.add(a)
            lines.append(f"- ⚠️ {a}")

    # error 级事件 top 5（排除已单独列出的）
    shown_types = {"goal_gate.released", "memory.mirror_import_failed", "notes.error"}
    top = [(t, c) for t, c in err_counter.most_common(5)
           if t not in shown_types and not (t == "llm.call" and c == 0)]
    for t, c in top:
        lines.append(f"- ⚠️ {t} ×{c}")

    if not lines:
        lines.append("- 无异常")
    return lines


# ── 主入口 ──────────────────────────────────────────

def generate_report(date_str: str | None = None, *,
                    events_path: Path | str | None = None,
                    library_dir: Path | str | None = None,
                    kb_path: Path | str | None = None) -> Path:
    """生成指定日期（默认昨天）的健康日报，落盘 library/健康日报/YYYY-MM-DD.md。

    幂等：同日重复生成 → 全量覆盖重写（内容一致）。
    参数可注入（测试用 tmpdir）。失败静默降级：记 WARNING，不抛异常。
    """
    date_str = date_str or (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    ep = Path(events_path) if events_path else EVENTS_PATH
    ld = Path(library_dir) if library_dir else LIBRARY_DIR
    kp = Path(kb_path) if kb_path else KB_PATH

    try:
        s1 = _engine_section(ep, date_str)
        s2 = _governance_section(ld, kp, date_str)
        s3 = _alerts_section(ep, date_str)

        md = [f"# 夜班体检 · {date_str}", "", "## 引擎健康"]
        md.extend(s1 or ["- 无数据"])
        md += ["", "## 知识库治理"]
        md.extend(s2 or ["- 无数据"])
        md += ["", "## 异常关注"]
        md.extend(s3 or ["- 无异常"])
        md.append("")

        out_dir = ld / HEALTH_DIR_NAME
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{date_str}.md"
        out_path.write_text("\n".join(md), encoding="utf-8")

        _emit("health.reported", {
            "date": date_str,
            "sections": {"engine": bool(s1), "governance": bool(s2), "alerts": bool(s3)},
        })
        return out_path
    except Exception as e:
        logger.warning("health report generation failed (silent degrade): %s", e)
        _emit("health.reported", {"date": date_str, "error": str(e)})
        raise


def ensure_report(date_str: str | None = None, *,
                  events_path: Path | str | None = None,
                  library_dir: Path | str | None = None,
                  kb_path: Path | str | None = None) -> Path | None:
    """启动补报：缺指定日期（默认昨天）的报告才生成；已存在返回 None。"""
    date_str = date_str or (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    ld = Path(library_dir) if library_dir else LIBRARY_DIR
    out_path = ld / HEALTH_DIR_NAME / f"{date_str}.md"
    if out_path.exists():
        return None
    return generate_report(date_str, events_path=events_path,
                           library_dir=library_dir, kb_path=kb_path)


if __name__ == "__main__":
    import sys
    _date = sys.argv[1] if len(sys.argv) > 1 else None
    try:
        _p = generate_report(_date)
        print(f"报告已生成: {_p}")
    except Exception as _e:
        print(f"生成失败（已静默降级）: {_e}")
        sys.exit(1)
