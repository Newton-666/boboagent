"""TICKET-PROFILE-PARADIGM-VALIDATE 专项测试 — 约束框架 vs 词眼判断对比验证。

纯验证：不改 signal_detector 主流程、不改写入、不污染 USER.md。
路 A（旧/词眼）：现有 detect_profile_signal（keyword_gate + LLM 判断），
    用 mock llm_caller 模拟词眼宽松 LLM、monkeypatch write_user_profile 记录（不真写）。
路 B（新/约束框架）：_judge_by_constraints 7 维打分 → 判定。

对比表：样本 | 路A判定 | 路B判定 | 期望 | 路A对错 | 路B对错。
统计：路 A 判对数 vs 路 B 判对数；话题细节阻挡率。
"""

import logging
import sys

import pytest

from core import signal_detector as sd

# ── 样本集（5 类，每类 2-3 条）──
# (类别, 样本, 期望classify)  期望写USER.md 由 classify 推导：profile/instruction=写，其余=不写
SAMPLES = [
    # 真范式（应为 USER.md）
    ("真范式", "记住我以后都用 Obsidian 记录", "instruction"),
    ("真范式", "我偏好任何文档都先讲风险再讲优点", "profile"),
    ("真范式", "每次回复都先说结论再给细节", "profile"),
    # 话题细节（应为 memory，不入 USER.md）
    ("话题细节", "在数学里我喜欢微积分", "memory"),
    ("话题细节", "我偏好用 K3 做评测", "memory"),
    ("话题细节", "以后做数学题我都喜欢先画图", "memory"),
    # 一次性（应丢弃）
    ("一次性", "这次先用 K3 测一下", "discard"),
    ("一次性", "先定评测集再调 API", "discard"),
    # 纠正信号（应修正旧条目）
    ("纠正信号", "别再用上次那种方案", "correction"),
    ("纠正信号", "不要每次都先解释", "correction"),
    # 显式指令（应直接进）
    ("显式指令", "记住这个工作流", "instruction"),
]

_EXPECT_WRITE = {"profile", "instruction"}


def _make_llm():
    """模拟词眼宽松 LLM：凡含画像类词即判 is_signal（不区分话题细节/真范式）。"""
    def _llm(messages, **kw):
        user_text = ""
        for m in messages:
            if m["role"] == "user":
                user_text = m["content"].replace("用户消息：", "")
        signal = any(k in user_text for k in ("以后", "喜欢", "偏好", "记住", "每次", "不要", "别", "先"))
        if signal:
            content = '{"is_signal": true, "category": "preference", "candidate": "偏好 ' + user_text[:12] + '"}'
        else:
            content = '{"is_signal": false}'
        return {"choices": [{"message": {"content": content}}]}
    return _llm


def _road_A(sd_mod, user_text, llm, writes):
    """路 A：现有 detect_profile_signal。返回（写USER.md?, 依据）。"""
    result = sd_mod.detect_profile_signal(user_text, llm, sid="test")
    if result is None or result.get("write") is None:
        return ("不写", "gate_miss_or_rejected")
    if result["write"].get("ok"):
        return ("写", "write_ok")
    return ("不写", "write_rejected")


def test_paradigm_validate(monkeypatch, capsys):
    """核心：路 A vs 路 B 对比 + 统计 + 话题细节阻挡率。"""
    # 路 A 的 write_user_profile 记录版（不真写 USER.md）
    writes = []

    def _mock_write(candidate, category, signal_source=""):
        writes.append(candidate)
        return {"ok": True, "candidate": candidate, "category": category}

    monkeypatch.setattr("core.profile_writer.write_user_profile", _mock_write)
    llm = _make_llm()

    rows = []
    stats = {"A_correct": 0, "A_wrong": 0, "B_correct": 0, "B_wrong": 0,
             "A_topic_block": 0, "B_topic_block": 0}
    topic_total = 0

    for cat, sample, expect in SAMPLES:
        # 路 A
        a_write, a_reason = _road_A(sd, sample, llm, writes)
        # 路 B
        b_res = sd._judge_by_constraints(sample)
        b_classify = b_res["classify"]
        b_write = "写" if b_classify in _EXPECT_WRITE else "不写"

        # 判定对错（按"是否写 USER.md"统一）
        expect_write = "写" if expect in _EXPECT_WRITE else "不写"
        a_ok = (a_write == expect_write)
        b_ok = (b_write == expect_write)

        if a_ok:
            stats["A_correct"] += 1
        else:
            stats["A_wrong"] += 1
        if b_ok:
            stats["B_correct"] += 1
        else:
            stats["B_wrong"] += 1

        # 话题细节阻挡：期望不写（memory/discard），实际不写 = 挡对
        if expect not in _EXPECT_WRITE:
            topic_total += 1
            if a_write == "不写":
                stats["A_topic_block"] += 1
            if b_write == "不写":
                stats["B_topic_block"] += 1

        rows.append((cat, sample, a_write, b_classify, expect, "✔" if a_ok else "✘", "✔" if b_ok else "✘"))

    # 打印对比表
    out = []
    out.append("=" * 86)
    out.append("TICKET-PROFILE-PARADIGM-VALIDATE 对比表")
    out.append("=" * 86)
    out.append(f"{'类别':<6} | {'样本':<26} | {'路A(词眼)':>9} | {'路B(约束)':>8} | {'期望':>8} | 路A | 路B")
    out.append("-" * 86)
    for cat, sample, a_write, b_classify, expect, a_ok, b_ok in rows:
        out.append(f"{cat:<6} | {sample:<26} | {a_write:>9} | {b_classify:>8} | {expect:>8} |  {a_ok} |  {b_ok}")
    out.append("-" * 86)
    out.append(f"路A 判对 {stats['A_correct']}/{len(SAMPLES)}，判错 {stats['A_wrong']}")
    out.append(f"路B 判对 {stats['B_correct']}/{len(SAMPLES)}，判错 {stats['B_wrong']}")
    out.append(f"话题细节/一次性阻挡率：路A {stats['A_topic_block']}/{topic_total}，路B {stats['B_topic_block']}/{topic_total}")
    report = "\n".join(out)
    print(report)
    sys.stdout.flush()

    # 断言：路 B 显著优于路 A，且话题细节全挡
    assert stats["B_correct"] > stats["A_correct"], "路 B 应显著优于路 A"
    assert stats["A_wrong"] >= 1, "路 A 应有误判（词眼痛症）"
    assert stats["B_wrong"] == 0, "路 B 在本批样本应全对"
    assert stats["B_topic_block"] == topic_total, "路 B 应全挡话题细节/一次性"
    assert stats["A_topic_block"] < topic_total, "路 A 应未能全挡话题细节（有误写）"
