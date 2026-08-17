"""token 趋势报告：rounds.jsonl + events.jsonl 实测聚合（一次性，交互运行）。"""
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(sys.executable).parent.parent.parent))
from daimon_runtime import setup_plot
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt

REPO = Path("/Users/niuqingwei/Desktop/boboagent_main")
OUT = REPO / "reports"
OUT.mkdir(exist_ok=True)

setup_plot()

# ── 数据装载 ──
rows = []
with open(REPO / "data/metrics/rounds.jsonl", encoding="utf-8") as f:
    for line in f:
        try:
            rows.append(json.loads(line))
        except Exception:
            pass

recs = []
for r in rows:
    u = r.get("usage") or {}
    pt = u.get("prompt_tokens")
    hit = u.get("cache_hit_tokens")
    if not pt:
        continue
    recs.append({
        "ts": datetime.fromtimestamp(r["ts"]),
        "branch": r.get("branch", "?"),
        "round": r.get("round"),
        "prompt_tokens": pt,
        "hit": hit,
        "hit_rate": (hit / pt * 100) if isinstance(hit, (int, float)) and pt else None,
        "duration_s": (r.get("duration_ms") or 0) / 1000,
        "repeat_reads": len(r.get("repeat_reads") or []),
    })
df = pd.DataFrame(recs).sort_values("ts").reset_index(drop=True)

# llm.call 耗时分布（近两天）
durs = []
with open(REPO / "data/logs/events.jsonl", encoding="utf-8") as f:
    for line in f:
        try:
            e = json.loads(line)
        except Exception:
            continue
        if e.get("type") == "llm.call" and e.get("duration_ms"):
            durs.append(e["duration_ms"] / 1000)
durs = pd.Series(durs)

# 时代分界（实测轮次时间锚点）
t_cost2 = datetime(2026, 8, 16, 18, 0)   # COST-2 前缀稳定化生效
t_cost3 = datetime(2026, 8, 17, 8, 0)    # COST-3 长会话修复 e2e

# ── 图：2×2 面板 ──
fig, axes = plt.subplots(2, 2, figsize=(13, 8))

# 1. 缓存命中率趋势
ax = axes[0][0]
d = df.dropna(subset=["hit_rate"])
ax.scatter(d["ts"], d["hit_rate"], s=22, alpha=0.7, color="#2d2d2d")
ax.axvline(t_cost2, color="#e8913a", lw=1, ls="--")
ax.axvline(t_cost3, color="#e8913a", lw=1, ls=":")
ax.text(t_cost2, 104, "COST-2", color="#e8913a", fontsize=9, ha="center")
ax.text(t_cost3, 104, "COST-3", color="#e8913a", fontsize=9, ha="center")
ax.axhline(85, color="#b8b4a8", lw=0.8, ls="-")
ax.set_ylim(-2, 108)
ax.set_title("缓存命中率趋势（真实 API 字段）")
ax.set_ylabel("命中率 %")

# 2. 每轮输入量
ax = axes[0][1]
ax.scatter(df["ts"], df["prompt_tokens"] / 1000, s=22, alpha=0.7, color="#777")
ax.axvline(t_cost2, color="#e8913a", lw=1, ls="--")
ax.axvline(t_cost3, color="#e8913a", lw=1, ls=":")
ax.set_title("每轮输入 prompt tokens")
ax.set_ylabel("K tokens")

# 3. llm.call 耗时分布
ax = axes[1][0]
sns.histplot(durs, bins=60, ax=ax, color="#2d2d2d", alpha=0.75)
med, p90 = durs.median(), durs.quantile(0.9)
ax.axvline(med, color="#e8913a", lw=1.2, ls="--", label=f"中位 {med:.1f}s")
ax.axvline(p90, color="#f48771", lw=1.2, ls="--", label=f"p90 {p90:.1f}s")
ax.legend(fontsize=9)
ax.set_title(f"单次 LLM 调用耗时分布（n={len(durs)}）")
ax.set_xlabel("秒")
ax.set_xlim(0, 60)

# 4. 每轮耗时 vs 命中率
ax = axes[1][1]
d2 = df.dropna(subset=["hit_rate"])
d2 = d2[d2["duration_s"] > 0]
ax.scatter(d2["hit_rate"], d2["duration_s"], s=22, alpha=0.6, color="#2d2d2d")
ax.set_title("回合时长 vs 缓存命中率")
ax.set_xlabel("命中率 %")
ax.set_ylabel("回合时长 秒")

fig.suptitle("bobo token 消耗趋势报告 · 数据截至 " + datetime.now().strftime("%Y-%m-%d %H:%M"), fontsize=13)
fig.tight_layout()
path = OUT / "token_trend_report.png"
fig.savefig(path, dpi=200, bbox_inches="tight")
print("saved:", path)

# ── 关键统计输出 ──
pre = df[(df["ts"] < t_cost2) & df["hit_rate"].notna()]
mid = df[(df["ts"] >= t_cost2) & (df["ts"] < t_cost3) & df["hit_rate"].notna()]
post = df[(df["ts"] >= t_cost3) & df["hit_rate"].notna()]
for name, seg in [("COST-2 前", pre), ("COST-2 后/COST-3 前", mid), ("COST-3 后", post)]:
    if len(seg):
        print(f"{name}: n={len(seg)} 命中率均值 {seg['hit_rate'].mean():.1f}% 中位 {seg['hit_rate'].median():.1f}% 输入均值 {seg['prompt_tokens'].mean()/1000:.1f}K")
print(f"llm.call: n={len(durs)} 中位 {med:.1f}s p90 {p90:.1f}s max {durs.max():.1f}s >10s 占比 {(durs>10).mean()*100:.1f}%")
rep = df[df["repeat_reads"] > 0]
print(f"含重复读取警示的轮次: {len(rep)}/{len(df)}")
