# -*- coding: utf-8 -*-
"""P0-3 缓存实测：尾部动态块变化对 DeepSeek 前缀缓存的影响。

纯实验票——零引擎改动，产出物是测量报告（P2 经济模型开门闸）。

四场景对照（每场景 ≥3 次取样取中位数，DeepSeek 自动缓存有随机性）：
  S0 基线      ：前缀 + 尾部块完全不变连发（验证探针可靠性，期望 ~100%）
  S1 尾部微调  ：尾部块改几个字（同主题微调，模拟 evolved 片段微变）
  S2 尾部替换  ：尾部块换不同主题（模拟注入内容彻底变化）
  S3 长度变化  ：尾部块 tokens 显著增删（模拟片段长度漂移）
  S4 中段对照  ：S2 同款变化插到中段（验证"尾部在前缀内/外"假设）

成本控制：base 前缀只构造一次，每轮只变尾部/中段变体（~2k tokens/轮 × 15 轮
≈ 30k input tokens，deepseek-chat 价格可忽略）；max_tokens=8（只要 usage 头）。

用法：.venv/bin/python scripts/probe_p0_3_cache.py [--rounds 3]
输出：data/logs/cache_probe_p03.json（原始值）+ 终端表格。
"""

import argparse
import json
import os
import statistics
import sys
import time

import requests
from dotenv import load_dotenv

load_dotenv()  # 加载仓库根 .env（DEEPSEEK_API_KEY）

API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com") + "/chat/completions"
MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

_OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "data", "logs", "cache_probe_p03.json")

# ── 固定前缀（模拟真实上下文，~1200 tokens；除尾部/中段变体外逐字节不变）──
SYSTEM = (
    "你是 Bobo，一个专业的个人智能助手。你在帮助用户处理代码项目任务。"
    "核心原则：跟踪用户的原始目标；工具调用失败时尝试替代方案；每次声称完成时提供具体证据。"
    "输出用 markdown 代码块包裹并标明语言。回答简洁专业，不使用 emoji。"
    "工作流程：多步任务先建台账；改动即 commit；收工汇报分条交底。"
    "代码评审意见的输出顺序：先讲风险，再讲优点。"
)

HISTORY = [
    {"role": "user", "content": "帮我看看这个项目的 git 状态，然后检查一下有没有未提交的改动。"},
    {"role": "assistant", "content": "好的，我先查看当前 git 状态。正在检查工作区是否有未提交的改动、当前所在分支以及远程同步情况，稍等片刻。"},
    {"role": "user", "content": "顺便把最近三个 commit 的信息列出来，我想回顾一下这几天的改动记录。"},
    {"role": "assistant", "content": "好的，我列出了最近三个 commit：最新一个是文档更新，前一个是功能修复，再往前是重构。整体看这几天的改动集中在票据施工和文档维护上。"},
    {"role": "user", "content": "好，接下来我们继续处理手头的票据。你先把相关的背景信息梳理一下。"},
    {"role": "assistant", "content": "明白了。票据的背景我已经梳理：核心诉求是量化尾部动态块对前缀缓存的影响，产出测量报告。我会按照实验设计逐步推进。"},
    {"role": "user", "content": "这次任务的验收标准很严格，测试必须全量跑，不能只挑子集。你要记住这个口径。"},
    {"role": "assistant", "content": "记住了：全量回归口径固定为 pytest tests/ 全量实跑，汇报里的零回归必须对应全量数字，挑子集跑就如实写仅跑了哪些文件集。环境跑不动先换对解释器，跑不动就如实交代，绝不改写结论。"},
    {"role": "user", "content": "还有一点：这次改动涉及核心引擎，收工前必须逐 hunk 自审 diff，发现的问题先修再汇报。"},
    {"role": "assistant", "content": "收到。声明完工前我会逐 hunk 自审一遍 git diff，自审发现的问题先修再汇报，不带已知 bug 收工。汇报数字必须可复现，贴本地实跑原话。"},
    {"role": "user", "content": "改动完成后先别急着 merge，等终审通过再走收编流程。分支和回滚标签都要准备好。"},
    {"role": "assistant", "content": "明白：施工完成停在分支上等终审，不自行 commit/merge/push 收编。回滚标签在动工前就打好了，每个阶段可回溯。"},
]

# ── 尾部动态块变体（模拟 P2 evolved 用户模型片段注入）──
TAIL_BASE = "用户偏好：代码评审时先讲风险再讲优点，变更用 diff 格式展示，commit message 用中文。"

# S1：同主题微调（改几个字，语义不变）
TAIL_S1_VARIANTS = [
    "用户偏好：代码评审时先讲风险再讲优点，变更用 diff 格式展示，commit 用中文。",
    "用户偏好：代码评审时先讲风险，再讲优点；变更用 diff 展示；commit message 用中文。",
    "用户偏好：代码评审先讲风险后讲优点，diff 展示变更，提交信息用中文。",
]

# S2：完全替换（不同主题，长度相近但内容完全不同）
TAIL_S2_VARIANTS = [
    "用户偏好：收工汇报正文给人看，原始证据落盘 library 完成报告或票据附录，不在聊天里糊超过五行的命令输出；"
    "台账状态、待人工清单只能作为附属段落跟在答复之后，禁止以台账代替答复；"
    "每回合结束时最后一条回复必须是简短的收工汇报，用自然的语言逐条交底。",
    "用户偏好：工作流先建台账再动工，完成一项立即销账；遇到多步施工任务主动建账防丢；"
    "简单问答一两步能做完的事不建账直接回答；自建的账必须认真销，每项带 verify 与 evidence 字段；"
    "完成一项立即用 update 销账，标 done 时带证据。",
    "用户偏好：多步任务先做视觉方向探索，用户确认后才写完整页面；"
    "不接受 AI 默认输出，不接受默认紫色渐变，不使用 emoji 装饰；"
    "每个内容单元都是独立可访问的入口，不是视觉装饰；页面必须包含 Logo。",
]

# S3：长度变化（6 chars → 50 → 800 chars，拉大 miss 占比差异）
TAIL_S3_VARIANTS = [
    "偏好：简洁。",
    TAIL_BASE,
    "用户偏好（综合）：代码评审时先讲风险再讲优点，变更用 diff 格式展示，commit message 用中文；"
    "收工汇报分条人话摘要，原始证据落盘不进聊天；多步任务先建台账再动工，完成一项立即销账；"
    "遇到工具失败尝试替代方案，不编造结果；输出代码用 markdown 代码块标明语言；"
    "所有改动必须在 feature 分支上进行，不带回滚标签不 merge；每次操作前先 fetch 确认远程状态；"
    "测试汇报必须贴本地实跑原话输出，跑不动就如实说跑不动；"
    "修改提交历史是被禁止的，push 过的 commit 就是历史不要改；"
    "merge 前必须先确认当前分支，避免误 merge 到错误的分支；"
    "每次 merge 到 main 后必须 push main 和回滚标签，确认远程同步；"
    "施工票收工汇报必须含改动文件清单、行数、专项和全量测试原话输出、md5 三值、git 状态；"
    "汇报里的每个数字都要贴本地实跑的原话输出，跑不动就如实说跑不动；"
    "全量回归口径固定为全量 pytest 实跑，挑子集跑就如实写仅跑了哪些文件集；"
    "环境跑不动先换对解释器，跑不动就如实交代，不得改写结论。",
]

# S4：中段对照（同 S2 的"完全替换"内容，但插到 system 之后、历史之前）
TAIL_S4_VARIANTS = [
    "【注入】用户偏好：收工汇报正文给人看，原始证据落盘 library 完成报告或票据附录，不在聊天里糊命令输出；台账只能作为附属段落跟在答复之后。",
    "【注入】用户偏好：工作流先建台账再动工，完成一项立即销账；自建的账必须认真销，每项带 verify 与 evidence 字段。",
    "【注入】用户偏好：多步任务先做视觉方向探索，用户确认后才写完整页面；不接受 AI 默认输出。",
]


def _call(messages, label: str, scene: str, variant: str) -> dict:
    """单轮 API 调用，返回 usage 原始值。"""
    body = {"model": MODEL, "messages": messages, "max_tokens": 8, "stream": False}
    t0 = time.time()
    r = requests.post(URL, json=body, timeout=90, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}",
    })
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
    usage = r.json().get("usage", {})
    prompt_tokens = usage.get("prompt_tokens", 0)
    hit = usage.get("prompt_cache_hit_tokens", 0)
    miss = usage.get("prompt_cache_miss_tokens", prompt_tokens - hit)
    return {
        "scene": scene,
        "label": label,
        "variant": variant,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "duration_s": round(time.time() - t0, 2),
        "prompt_tokens": prompt_tokens,
        "cache_hit_tokens": hit,
        "cache_miss_tokens": miss,
        "hit_ratio": round(hit / prompt_tokens, 4) if prompt_tokens else 0.0,
    }


def build_messages(tail: str | None = None, mid: str | None = None,
                   long: bool = False) -> list:
    """构造 messages。tail=尾部动态块（默认注入），mid=中段注入（S4 对照），
    long=True 时历史 x3（模拟长会话，验证前缀占比效应）。"""
    msgs = [{"role": "system", "content": SYSTEM}]
    if mid:
        msgs.append({"role": "system", "content": mid})
    history = HISTORY * 3 if long else HISTORY
    msgs.extend(history)
    if tail:
        msgs.append({"role": "user", "content": tail})
    return msgs


def run_scenario(scene: str, variants: list[str], rounds: int,
                 mode: str = "tail", long: bool = False) -> list[dict]:
    """跑一个场景：每个变体跑 1 轮，共 rounds 个变体（或同变体重复 rounds 轮）。"""
    results = []
    if scene == "S0":
        # 基线：完全相同的请求连发 rounds 轮
        msgs = build_messages(tail=TAIL_BASE, long=long)
        for i in range(rounds):
            results.append(_call(msgs, f"S0-基线-{i+1}", scene, "tail_base"))
    else:
        for i in range(rounds):
            variant = variants[i % len(variants)]
            if mode == "tail":
                msgs = build_messages(tail=variant, long=long)
            else:
                msgs = build_messages(mid=variant, long=long)
            results.append(_call(msgs, f"{scene}-{i+1}", scene, variant[:40]))
    return results


def _median(rows: list[dict], key: str):
    vals = [r[key] for r in rows]
    return round(statistics.median(vals), 4)


def main():
    ap = argparse.ArgumentParser(description="P0-3 缓存实测（尾部动态块 vs 前缀缓存）")
    ap.add_argument("--rounds", type=int, default=3, help="每场景取样次数（默认 3）")
    ap.add_argument("--skip-s4", action="store_true", help="跳过 S4 中段对照（省 1 次前缀破坏）")
    ap.add_argument("--long", action="store_true",
                    help="长前缀模式：历史 x3（~3k tokens），只跑 S0L 基线 + S2L 尾部替换")
    ap.add_argument("--dry", action="store_true", help="只打印请求构造，不发 API（离线自测）")
    args = ap.parse_args()

    if not API_KEY and not args.dry:
        print("无 DEEPSEEK_API_KEY，无法实弹", file=sys.stderr)
        sys.exit(1)

    all_results = []
    if args.long:
        scenarios = [
            ("S0L", "长前缀基线（不变）", [TAIL_BASE], "tail"),
            ("S2L", "长前缀尾部替换", TAIL_S2_VARIANTS, "tail"),
        ]
        long = True
    else:
        scenarios = [
            ("S0", "基线（不变）", [TAIL_BASE], "tail"),
            ("S1", "尾部同主题微调", TAIL_S1_VARIANTS, "tail"),
            ("S2", "尾部完全替换", TAIL_S2_VARIANTS, "tail"),
            ("S3", "尾部长度变化", TAIL_S3_VARIANTS, "tail"),
        ]
        if not args.skip_s4:
            scenarios.append(("S4", "中段对照（同 S2 变化）", TAIL_S4_VARIANTS, "mid"))
        long = False

    if args.dry:
        for scene, name, variants, mode in scenarios:
            for i, v in enumerate(variants[:args.rounds]):
                msgs = build_messages(tail=v, long=long) if mode == "tail" \
                    else build_messages(mid=v, long=long)
                print(f"[{scene}] {name} v{i+1}: {len(json.dumps(msgs, ensure_ascii=False))} chars, "
                      f"{len(msgs)} msgs, tail_len={len(v)}")
        print("dry-run OK（未发 API）")
        return

    for scene, name, variants, mode in scenarios:
        print(f"── {scene} {name}（{args.rounds} 轮）──", flush=True)
        try:
            rows = run_scenario(scene, variants, args.rounds, mode, long=long)
        except Exception as e:
            print(f"  {scene} 失败: {e}", file=sys.stderr)
            continue
        all_results.extend(rows)
        for r in rows:
            print(f"  {r['label']:<16} prompt={r['prompt_tokens']:>5} "
                  f"hit={r['cache_hit_tokens']:>5} miss={r['cache_miss_tokens']:>5} "
                  f"ratio={r['hit_ratio']*100:6.1f}%  ({r['duration_s']}s)")
        print(f"  → {scene} 中位命中率: {_median(rows, 'hit_ratio')*100:.1f}%", flush=True)

    # 落盘：long 模式合并追加（不覆盖主实验数据），按 scene+ts 去重
    os.makedirs(os.path.dirname(_OUT), exist_ok=True)
    existing_raw = []
    if os.path.exists(_OUT):
        try:
            with open(_OUT, "r", encoding="utf-8") as f:
                existing_raw = json.load(f).get("raw", [])
        except (OSError, json.JSONDecodeError):
            existing_raw = []
    seen = {(r.get("scene"), r.get("ts")) for r in all_results}
    merged = existing_raw + [r for r in all_results
                             if (r.get("scene"), r.get("ts")) not in
                             {(e.get("scene"), e.get("ts")) for e in existing_raw}]
    # 按 scene 重建汇总（含历史数据）
    scene_order = [s[0] for s in scenarios]
    summary_scenes = {}
    for s in sorted({r["scene"] for r in merged}, key=lambda x: scene_order.index(x)
                    if x in scene_order else 99):
        rows = [r for r in merged if r["scene"] == s]
        summary_scenes[s] = {
            "name": next((n for sc, n, _, _ in scenarios if sc == s), s),
            "n": len(rows),
            "median_hit_ratio": _median(rows, "hit_ratio"),
            "min_hit_ratio": round(min(r["hit_ratio"] for r in rows), 4),
            "max_hit_ratio": round(max(r["hit_ratio"] for r in rows), 4),
        }
    summary = {
        "probe": "P0-3 cache probe",
        "model": MODEL,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "rounds_per_scene": args.rounds,
        "scenarios": summary_scenes,
    }
    with open(_OUT, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "raw": merged}, f,
                  ensure_ascii=False, indent=2)
    print(f"\n已落盘: {_OUT}（本轮 {len(all_results)} 条，累计 {len(merged)} 条原始值）")

    print("\n=== 命中率中位数汇总 ===")
    for scene, name, variants, mode in scenarios:
        s = summary["scenarios"].get(scene)
        if s:
            print(f"  {scene} {name:<14} {s['median_hit_ratio']*100:6.1f}%  "
                  f"（min {s['min_hit_ratio']*100:.1f}% / max {s['max_hit_ratio']*100:.1f}%）")


if __name__ == "__main__":
    main()
