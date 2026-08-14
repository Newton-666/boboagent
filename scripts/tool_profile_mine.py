#!/usr/bin/env python3
"""COST-1a 第一步：bobo 工具画像挖矿（如实画像，零优化）。
数据源：data/logs/events.jsonl（4.1 万行真实事件）+ core 工具注册表 schema 成本。
产出：reports/tool_profile_report.md + 控制台摘要。
"""
import json, collections, statistics, sys, os

EV = "data/logs/events.jsonl"
OUT = "reports/tool_profile_report.md"

# ── 1. 日志挖矿 ──
calls = collections.Counter()            # tool → 调用次数
dur = collections.defaultdict(list)      # tool → [duration_ms]
blocked = collections.Counter()          # tool → 被硬拦次数
cancelled = collections.Counter()
llm_calls = 0
prompt_tokens_total = 0
completion_zero = 0
sessions = collections.Counter()         # session → tool 调用数
last_call = {}                           # session → (tool, args_summary) 上一条
dup = collections.Counter()              # tool → 重复调用次数（同会话紧邻同名同参数）
per_session_tools = collections.defaultdict(collections.Counter)

with open(EV) as f:
    for line in f:
        try:
            e = json.loads(line)
        except Exception:
            continue
        t = e.get("type")
        if t == "llm.call":
            llm_calls += 1
            prompt_tokens_total += e.get("prompt_tokens") or 0
            if not e.get("completion_tokens"):
                completion_zero += 1
        elif t == "tool.exec":
            name = e.get("name", "?")
            sid = e.get("session_id", "")
            calls[name] += 1
            sessions[sid] += 1
            per_session_tools[sid][name] += 1
            d = e.get("duration_ms")
            if isinstance(d, (int, float)):
                dur[name].append(d)
            if e.get("hard_blocked"):
                blocked[name] += 1
            if e.get("cancelled"):
                cancelled[name] += 1
            sig = (name, (e.get("args_summary") or "")[:200])
            if last_call.get(sid) == sig:
                dup[name] += 1
            last_call[sid] = sig

# ── 2. schema 成本（工具注册表定义大小，chars/4 ≈ tokens）──
schema_info = []
try:
    from core.tools_registry import TOOLS  # 尝试注册表
except Exception:
    TOOLS = None
if TOOLS is None:
    # 兜底：直接从 engine 的工具装配处找
    try:
        import importlib, pkgutil, core
    except Exception:
        pass
try:
    if TOOLS is None:
        from core import engine as _eng
        TOOLS = getattr(_eng, "TOOLS", None) or getattr(_eng, "TOOL_SCHEMAS", None)
except Exception:
    TOOLS = None

schema_tokens = {}
if TOOLS:
    items = TOOLS.items() if isinstance(TOOLS, dict) else [(t.get("function", {}).get("name", "?"), t) for t in TOOLS]
    for name, spec in items:
        s = json.dumps(spec, ensure_ascii=False)
        schema_tokens[name] = len(s) // 4

# ── 3. 汇总 ──
total_calls = sum(calls.values())
total_sessions = len(sessions)
total_dup = sum(dup.values())

lines = []
lines.append("# bobo 工具画像报告（COST-1a 第一步 · 如实画像零优化）\n")
lines.append(f"> 数据：data/logs/events.jsonl · 会话数 {total_sessions} · 工具调用总数 {total_calls} · LLM 调用 {llm_calls} 次\n")
lines.append("## 全局指标\n")
lines.append(f"- LLM 调用 prompt_tokens 总量：**{prompt_tokens_total:,}**（平均每轮 {prompt_tokens_total//max(llm_calls,1):,}）")
lines.append(f"- 空回复（completion_tokens=0）：**{completion_zero}** 次 / {llm_calls} 次（{completion_zero/max(llm_calls,1)*100:.1f}%）")
lines.append(f"- 重复调用（同会话紧邻同名同参数）：**{total_dup}** 次 / {total_calls} 次（{total_dup/max(total_calls,1)*100:.1f}%）\n")

lines.append("## 每工具画像（按调用次数降序）\n")
lines.append("| 工具 | 调用 | 占比 | 重复调用 | 硬拦截 | 被取消 | 平均耗时ms | P95耗时ms | schema≈tokens |")
lines.append("|---|---|---|---|---|---|---|---|---|")
rows = []
for name, cnt in calls.most_common():
    d = dur.get(name, [])
    avg = int(statistics.mean(d)) if d else 0
    p95 = int(sorted(d)[int(len(d)*0.95)]) if len(d) >= 20 else (max(d) if d else 0)
    rows.append((name, cnt, dup.get(name,0), blocked.get(name,0), cancelled.get(name,0), avg, p95, schema_tokens.get(name, "?")))
    lines.append(f"| {name} | {cnt} | {cnt/total_calls*100:.1f}% | {dup.get(name,0)} | {blocked.get(name,0)} | {cancelled.get(name,0)} | {avg} | {p95} | {schema_tokens.get(name,'?')} |")

lines.append("\n## 零调用工具（白交 schema 税）\n")
zero = [n for n in schema_tokens if n not in calls]
if zero:
    for n in sorted(zero):
        lines.append(f"- {n}（schema≈{schema_tokens[n]} tokens）")
else:
    lines.append("- （注册表未取到或未覆盖，见备注）")

lines.append("\## 备注\n")
lines.append("- schema tokens = json 定义字符数/4 估算；注册表取不到的工具标记 ?")
lines.append("- 耗时为工具自身执行时间，不含 LLM 等待")

os.makedirs("reports", exist_ok=True)
with open(OUT, "w") as f:
    f.write("\n".join(str(l) for l in lines))

# 控制台摘要
print(f"会话数 {total_sessions} · 工具调用 {total_calls} · LLM 调用 {llm_calls}")
print(f"prompt_tokens 总量 {prompt_tokens_total:,} · 空回复 {completion_zero} ({completion_zero/max(llm_calls,1)*100:.1f}%)")
print(f"重复调用 {total_dup} ({total_dup/max(total_calls,1)*100:.1f}%)")
print(f"\nTOP10 工具:")
for name, cnt in calls.most_common(10):
    print(f"  {name}: {cnt} 次 (dup {dup.get(name,0)})")
print(f"\n零调用工具 {len([n for n in schema_tokens if n not in calls])} 个")
print(f"\n报告 → {OUT}")
