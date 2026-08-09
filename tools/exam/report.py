"""tools/exam/report.py — 成绩单渲染（Markdown，全部留档入 git）"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ExamRecord:
    """一道题的全部留档。"""
    dimension: str           # C1 / C2 / C3
    seed_id: str
    kind: str
    inject: str              # 埋点原文
    question: str
    answer: str              # 考生答卷原文
    score: float
    hallucination: bool
    honest_unknown: bool
    reason: str
    judge_source: str


@dataclass
class ExamResult:
    """整场考试的成绩单数据。"""
    examinee: str                       # 考生模型（如 deepseek/deepseek-chat）
    judge: str                          # 阅卷官（provider/model 或 rule-only）
    started_at: str
    compressions_observed: int          # 实测压缩次数（events 证据）
    records: list[ExamRecord] = field(default_factory=list)
    seed_snapshot: list[dict] = field(default_factory=list)  # 埋点种子留档

    PASS_LINES = {"C1": 1.0, "C2": 0.8, "C3": 0.6}

    def dim_scores(self) -> dict:
        out = {}
        for dim in ("C1", "C2", "C3"):
            rs = [r for r in self.records if r.dimension == dim]
            if rs:
                out[dim] = sum(r.score for r in rs) / len(rs)
        return out

    def hallucinations(self) -> list[ExamRecord]:
        return [r for r in self.records if r.hallucination]

    def passed(self) -> bool:
        scores = self.dim_scores()
        for dim, line in self.PASS_LINES.items():
            if dim in scores and scores[dim] < line:
                return False
        if self.hallucinations():
            return False  # 零幻觉是总及格前提
        return True


def render_markdown(result: ExamResult) -> str:
    """渲染成绩单 Markdown。"""
    lines = [
        f"# Gate C 保真考卷 · 成绩单",
        "",
        f"- 考生：**{result.examinee}**",
        f"- 阅卷官：{result.judge}",
        f"- 考试时间：{result.started_at}",
        f"- 实测压缩次数：**{result.compressions_observed}**（events.jsonl `context.compressed` 事件计数，非估算）",
        "",
        "## 总分",
        "",
        "| 维度 | 得分 | 及格线 | 判定 |",
        "|---|---|---|---|",
    ]
    scores = result.dim_scores()
    for dim in ("C1", "C2", "C3"):
        if dim in scores:
            s = scores[dim]
            line = result.PASS_LINES[dim]
            ok = "✅" if s >= line else "❌"
            lines.append(f"| {dim} | {s:.2f} | {line} | {ok} |")
    lines += [
        "",
        f"**总判定：{'✅ 通过' if result.passed() else '❌ 未通过'}**（幻觉 {len(result.hallucinations())} 次，零幻觉为总及格前提）",
        "",
        "## 每题回放",
        "",
    ]
    for i, r in enumerate(result.records, 1):
        emoji = "✅" if r.score == 1.0 else ("🟡" if r.score == 0.5 else "❌")
        lines += [
            f"### {i}. [{r.dimension}] {r.kind} · {emoji} {r.score}（{r.judge_source}）",
            "",
            f"- 埋点原文：{r.inject}",
            f"- 提问：{r.question}",
            f"- 考生答卷：{r.answer}",
            f"- 判分理由：{r.reason}",
            "",
        ]
    if result.hallucinations():
        lines += ["## 幻觉清单", ""]
        for r in result.hallucinations():
            lines.append(f"- [{r.dimension}] {r.question} → 答卷：{r.answer[:120]}")
        lines.append("")
    lines += [
        "## 埋点种子留档（防造假）",
        "",
        "```json",
        __import__("json").dumps(result.seed_snapshot, ensure_ascii=False, indent=2),
        "```",
        "",
    ]
    return "\n".join(lines)


def save_report(result: ExamResult, out_dir: str = "docs/exam/gate-c") -> str:
    """成绩单落盘，返回路径。"""
    from pathlib import Path
    d = Path(out_dir)
    d.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    safe_model = result.examinee.replace("/", "_")
    path = d / f"{stamp}-{safe_model}.md"
    path.write_text(render_markdown(result), encoding="utf-8")
    return str(path)
