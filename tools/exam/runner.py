"""tools/exam/runner.py — 考试驱动器（考场）

流程（TICKET-GC1 框架已定）：
  1. 装配真实考生：resolve_provider + create_llm_caller + Engine（真实压缩管道）
  2. EventBus 重定向到临时目录，压缩次数只认 context.compressed 事件（非估算）
  3. 剧本：埋点以"随口一说"注入 → C1（3 轮内提问）→ 杂谈填轮 →
     C2（实测满 5 次压缩后提问）→ C3（实测满 10 次压缩后提问）
  4. 阅卷 + 成绩单落盘

用法：
  python -m tools.exam.runner --provider deepseek --rounds 40 \
      --c2-at 5 --c3-at 10 --judge-provider gemini
  冒烟：python -m tools.exam.runner --provider deepseek --smoke
"""

from __future__ import annotations

import argparse
import random
import sys
import tempfile
import time
from dataclasses import asdict
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


def count_compressions(log_dir: str) -> int:
    """从隔离事件日志数 context.compressed 事件（实测，非估算）。"""
    import json
    p = Path(log_dir) / "events.jsonl"
    if not p.exists():
        return 0
    n = 0
    for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
        try:
            if json.loads(line).get("type") == "context.compressed":
                n += 1
        except Exception:
            continue
    return n


def build_examinee(provider_name: str, model: str | None = None):
    """装配真实考生（与 TUI 同款管道）。"""
    from core.provider import resolve_provider
    from core.llm_caller import create_llm_caller
    from core.tool_executor import execute_tool
    from core.engine import Engine
    from tools import TOOLS_SCHEMA
    from config import API_KEY, API_BASE_URL, API_MODEL_NAME

    if provider_name:
        prov = resolve_provider(provider_name)
        api_key = prov["api_key"] or API_KEY
        base_url = prov["base_url"] or API_BASE_URL
        model_name = model or prov["model"] or API_MODEL_NAME
    else:
        api_key, base_url, model_name = API_KEY, API_BASE_URL, API_MODEL_NAME
    caller = create_llm_caller(api_key, base_url, model_name, TOOLS_SCHEMA)
    engine = Engine(caller, execute_tool)
    return engine, model_name


def make_judge_call(judge_provider: str | None):
    """装配独立阅卷官 LLM（与考生不同 provider）。失败返回 None（降级 rule 判分）。"""
    if not judge_provider:
        return None
    try:
        from core.provider import resolve_provider
        prov = resolve_provider(judge_provider)
        if not prov["api_key"]:
            return None
        import urllib.request
        import json as _json

        def judge_call(prompt: str) -> str:
            body = _json.dumps({
                "model": prov["model"],
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
            }).encode("utf-8")
            req = urllib.request.Request(
                prov["base_url"].rstrip("/") + "/chat/completions", data=body,
                headers={"Content-Type": "application/json",
                         "Authorization": f"Bearer {prov['api_key']}"})
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = _json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"]

        return judge_call
    except Exception:
        return None


def run_exam(provider: str | None = None, model: str | None = None,
             rounds: int = 40, c2_at: int = 5, c3_at: int = 10,
             judge_provider: str | None = None,
             max_wait_rounds: int = 200) -> "ExamResult":
    """执行整场考试，返回 ExamResult。"""
    from core.event_bus import EventBus
    from tools.exam.seeds import make_exam_set, filler_prompts
    from tools.exam.judge import final_verdict
    from tools.exam.report import ExamResult, ExamRecord

    rng = random.Random()
    seeds = make_exam_set(rng)
    fillers = filler_prompts(rng, rounds)

    # 事件总线重定向到临时目录（隔离 + 压缩计数证据）
    tmp_events = tempfile.mkdtemp(prefix="bobo_exam_events_")
    EventBus.reset(log_dir=tmp_events)

    # 记忆库隔离（铁律：考试埋点是虚构事实，绝不许写进真实 knowledge_base）
    # 双通道都要封：v5_memory（JSON 写入）+ memory_mirror（MEMORY.md 镜像回灌）
    import tools.v5_memory as _v5
    import tools.memory_mirror as _mm
    tmp_kb = Path(tmp_events) / "knowledge_base.json"
    tmp_kb.write_text('{"entries": [], "folders": []}', encoding="utf-8")
    _v5._memory_db = lambda: str(tmp_kb)
    _v5._memory_backup = lambda: str(tmp_kb) + ".bak"
    _mm._memory_db = lambda: str(tmp_kb)
    _mm._memory_backup = lambda: str(tmp_kb) + ".bak"
    _mm._mirror_path = lambda: Path(tmp_events) / "MEMORY.md"

    # 笔记库隔离（同理：考试会话的"随手一记"不许污染真实 library/）
    import tools.living_notes as _ln
    tmp_lib = Path(tmp_events) / "library"
    tmp_lib.mkdir(exist_ok=True)
    _ln.LIBRARY_DIR = tmp_lib

    engine, model_name = build_examinee(provider, model)
    examinee = f"{provider or 'default'}/{model_name}"
    judge_call = make_judge_call(judge_provider)
    judge_name = judge_provider if judge_call else "rule-only"

    result = ExamResult(
        examinee=examinee, judge=judge_name,
        started_at=time.strftime("%Y-%m-%d %H:%M:%S"),
        compressions_observed=0,
        seed_snapshot=[asdict(s) for s in seeds],
    )

    def last_reply() -> str:
        """engine.run 无返回值（run() 不 return），答卷从 history 最后一条 assistant 取。"""
        for msg in reversed(engine.history):
            if msg.get("role") == "assistant" and str(msg.get("content") or "").strip():
                return str(msg["content"])
        return ""

    def ask(seed, dimension):
        engine.run(seed.question)
        reply = last_reply()
        if not reply:
            # 引擎无应答（history 中无 assistant 内容）：考试基础设施问题，记 0 分但不判幻觉
            from tools.exam.judge import Verdict
            verdict, source, reply = Verdict(
                0.0, False, False, "考生无应答（history 无 assistant 内容）"), "infra", "（考生无应答）"
        else:
            verdict, source = final_verdict(seed, reply, dimension, judge_call)
        result.records.append(ExamRecord(
            dimension=dimension, seed_id=seed.seed_id, kind=seed.kind,
            inject=seed.inject, question=seed.question, answer=reply,
            score=verdict.score, hallucination=verdict.hallucination,
            honest_unknown=verdict.honest_unknown, reason=verdict.reason,
            judge_source=source))

    # ── 第一幕：埋点注入（夹在第 1-2 条杂谈之间，随口一说）──
    engine.run(fillers[0])
    engine.run(seeds[0].inject)   # fact
    engine.run(seeds[1].inject)   # pref
    engine.run(seeds[2].inject)   # detail
    engine.run(seeds[3].inject)   # color

    # ── C1 即时回忆（3 轮内，不经历压缩）──
    ask(seeds[0], "C1")

    # ── 第二幕：杂谈填轮，等实测压缩次数达标 ──
    c3_enabled = c3_at < 10**8          # 冒烟模式禁用 C3 时不再傻等
    fi = 1
    asked_c2 = asked_c3 = False
    for _ in range(max_wait_rounds):
        n = count_compressions(tmp_events)
        result.compressions_observed = n
        if not asked_c2 and n >= c2_at:
            ask(seeds[1], "C2")   # pref
            ask(seeds[3], "C2")   # color
            asked_c2 = True
        if asked_c2 and c3_enabled and not asked_c3 and n >= c3_at:
            ask(seeds[2], "C3")   # detail 远期考古
            asked_c3 = True
        if asked_c2 and (asked_c3 or not c3_enabled):
            break
        if fi < len(fillers):
            engine.run(fillers[fi]); fi += 1
        else:
            # 话题用完后循环填充（保持上下文持续增长）
            engine.run(rng.choice(fillers))
    result.compressions_observed = count_compressions(tmp_events)
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description="Gate C 保真考卷")
    ap.add_argument("--provider", default="deepseek")
    ap.add_argument("--model", default=None)
    ap.add_argument("--rounds", type=int, default=40)
    ap.add_argument("--c2-at", type=int, default=5)
    ap.add_argument("--c3-at", type=int, default=10)
    ap.add_argument("--judge-provider", default=None)
    ap.add_argument("--smoke", action="store_true",
                    help="冒烟考：C1 + 提前 C2（c2-at=1），不跑 C3")
    args = ap.parse_args(argv)

    c2_at, c3_at = (1, 10**9) if args.smoke else (args.c2_at, args.c3_at)
    result = run_exam(provider=args.provider, model=args.model,
                      rounds=args.rounds, c2_at=c2_at, c3_at=c3_at,
                      judge_provider=args.judge_provider)

    from tools.exam.report import save_report
    path = save_report(result)
    scores = result.dim_scores()
    print(f"成绩单: {path}")
    print(f"实测压缩: {result.compressions_observed} 次 | 得分: {scores} "
          f"| 幻觉: {len(result.hallucinations())} | 总判定: {'通过' if result.passed() else '未通过'}")
    return 0 if result.passed() else 1


if __name__ == "__main__":
    sys.exit(main())
