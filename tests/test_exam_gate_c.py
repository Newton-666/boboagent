"""Gate C 保真考卷单元测试（出题人 Kimi；全程 mock，不打真实 API）。

覆盖：埋点池随机性与结构 / 判卷全分支 / 陷阱词否定语境 / 压缩计数 / 成绩单判定。
"""

import json
import random
from pathlib import Path

import pytest

from tools.exam.seeds import (
    Seed, make_exam_set, filler_prompts,
    gen_fact_seed, gen_pref_seed, gen_detail_seed, gen_color_seed,
)
from tools.exam.judge import (
    rule_score, llm_score, final_verdict, is_honest_unknown, trap_violated,
)
from tools.exam.runner import count_compressions
from tools.exam.report import ExamResult, ExamRecord, render_markdown, save_report


# ── 埋点池 ─────────────────────────────────────────────

class TestSeeds:
    def test_exam_set_structure(self):
        seeds = make_exam_set(random.Random(42))
        assert len(seeds) == 4
        kinds = [s.kind for s in seeds]
        assert kinds.count("fact") == 2 and kinds.count("pref") == 1 and kinds.count("detail") == 1
        assert len({s.seed_id for s in seeds}) == 4
        for s in seeds:
            assert s.inject and s.question and s.must_have

    def test_two_sets_differ(self):
        a = make_exam_set(random.Random(1))
        b = make_exam_set(random.Random(2))
        assert [s.inject for s in a] != [s.inject for s in b]

    def test_answers_not_from_real_documents(self):
        """埋点答案不得引用真实项目/笔记内容（抽查关键串）。"""
        seeds = make_exam_set(random.Random(7))
        banned = ["熵减", "TICKET", "bobo", "Obsidian", "压缩体系", "Raman"]
        for s in seeds:
            for b in banned:
                assert b.lower() not in s.inject.lower()
                assert b.lower() not in "".join(s.must_have).lower()

    def test_detail_seed_has_trap(self):
        s = gen_detail_seed(random.Random(3))
        assert len(s.traps) == 1
        assert "不是" in s.inject  # 限定词陷阱在注入语中明示

    def test_filler_no_repeat_and_on_topic(self):
        fs = filler_prompts(random.Random(5), 20)
        assert len(fs) == len(set(fs))
        for f in fs:  # 杂谈不得含埋点相关内容
            assert "代号" not in f and "规矩" not in f


# ── 判卷：规则判分全分支 ────────────────────────────────

FACT = Seed(kind="fact", inject="定名叫「灯塔-47」计划",
            question="内部代号叫什么？", must_have=["灯塔-47"])
DETAIL = Seed(kind="detail", inject="猫叫年糕，是领养的，不是买的",
              question="猫叫什么？怎么来的？", must_have=["年糕", "领养"], traps=["买"])


class TestRuleScore:
    def test_perfect_hit(self):
        v = rule_score(FACT, "内部代号是「灯塔-47」计划。", "C1")
        assert v.score == 1.0 and not v.hallucination

    def test_partial_hit(self):
        v = rule_score(DETAIL, "猫叫年糕。", "C2")
        assert v.score == 0.5 and not v.hallucination and v.misses == ["领养"]

    def test_trap_without_negation_is_hallucination(self):
        v = rule_score(DETAIL, "猫叫年糕，是买的。", "C2")
        assert v.score == 0.0 and v.hallucination

    def test_trap_with_negation_is_fine(self):
        v = rule_score(DETAIL, "猫叫年糕，是领养的，不是买的。", "C2")
        assert v.score == 1.0 and not v.hallucination

    def test_total_miss_is_hallucination(self):
        v = rule_score(FACT, "代号叫「熔炉-63」。", "C1")
        assert v.score == 0.0 and v.hallucination

    def test_honest_unknown_c3_scores_full(self):
        v = rule_score(FACT, "我不记得了，让我查一下笔记。", "C3")
        assert v.score == 1.0 and v.honest_unknown

    def test_honest_unknown_c1_scores_zero(self):
        v = rule_score(FACT, "我不确定。", "C1")
        assert v.score == 0.0 and v.honest_unknown and not v.hallucination

    def test_quoted_rule_content_not_misjudged_as_unknown(self):
        """冒烟考实录回归：答卷引用规则原文中的「不确定」不得误判为坦承不知道。"""
        pref = Seed(kind="pref", inject="进度汇报不许用「大概」「可能」这类词",
                    question="规矩是什么？", must_have=["进度汇报"])
        answer = "规矩是：进度汇报中禁止使用「大概」「可能」等不确定措辞，必须用确定语言。"
        v = rule_score(pref, answer, "C2")
        assert not v.honest_unknown and v.score >= 0.5

    def test_trap_violated_pure(self):
        assert trap_violated("买", "是买的") is True
        assert trap_violated("买", "不是买的") is False
        assert trap_violated("买", "没买过") is False


# ── 判卷：LLM 阅卷官（mock）────────────────────────────

class TestLLMScore:
    def test_llm_judge_parses_and_wins(self):
        def judge(prompt):
            return '{"score": 1.0, "hallucination": false, "honest_unknown": false, "reason": "全对"}'
        v, src = final_verdict(FACT, "「灯塔-47」", "C1", judge_call=judge)
        assert v.score == 1.0 and "llm" in src

    def test_llm_divergence_recorded(self):
        def judge(prompt):
            return '{"score": 0.0, "hallucination": true, "honest_unknown": false, "reason": "编造"}'
        v, src = final_verdict(FACT, "「灯塔-47」", "C1", judge_call=judge)
        assert v.score == 0.0 and "diverged" in src and "rule 判" in v.reason

    def test_llm_failure_falls_back_to_rule(self):
        def judge(prompt):
            raise RuntimeError("api down")
        v, src = final_verdict(FACT, "「灯塔-47」", "C1", judge_call=judge)
        assert v.score == 1.0 and "rule" in src

    def test_llm_no_judge_uses_rule(self):
        v, src = final_verdict(FACT, "不知道", "C3")
        assert v.score == 1.0 and src == "rule"


# ── 压缩计数（events 证据）─────────────────────────────

class TestCompressionCount:
    def test_counts_only_compressed(self, tmp_path):
        p = tmp_path / "events.jsonl"
        p.write_text("\n".join([
            json.dumps({"type": "context.compressed"}),
            json.dumps({"type": "context.compress_skipped"}),
            json.dumps({"type": "context.compressed"}),
            json.dumps({"type": "llm.call"}),
            "not-json",
        ]))
        assert count_compressions(str(tmp_path)) == 2

    def test_missing_file_is_zero(self, tmp_path):
        assert count_compressions(str(tmp_path)) == 0


# ── 成绩单 ─────────────────────────────────────────────

def _rec(dim, score, halluc=False):
    return ExamRecord(dimension=dim, seed_id="x1", kind="fact", inject="i",
                      question="q", answer="a", score=score,
                      hallucination=halluc, honest_unknown=False,
                      reason="r", judge_source="rule")


class TestReport:
    def test_pass_logic(self):
        r = ExamResult("deepseek/chat", "rule-only", "now", 10,
                       records=[_rec("C1", 1.0), _rec("C2", 1.0), _rec("C3", 1.0)])
        assert r.passed()

    def test_fail_on_low_c2(self):
        r = ExamResult("m", "rule-only", "now", 10,
                       records=[_rec("C1", 1.0), _rec("C2", 0.5), _rec("C3", 1.0)])
        assert not r.passed()

    def test_fail_on_any_hallucination(self):
        r = ExamResult("m", "rule-only", "now", 10,
                       records=[_rec("C1", 1.0), _rec("C2", 1.0), _rec("C3", 0.0, halluc=True)])
        assert not r.passed()

    def test_markdown_contains_evidence(self, tmp_path):
        r = ExamResult("deepseek/chat", "rule-only", "2026-08-09", 7,
                       records=[_rec("C1", 1.0)],
                       seed_snapshot=[{"seed_id": "x1", "kind": "fact"}])
        md = render_markdown(r)
        assert "实测压缩次数" in md and "7" in md
        assert "埋点种子留档" in md
        p = save_report(r, out_dir=str(tmp_path))
        assert Path(p).exists() and "gate-c" not in p  # out_dir 自定义时直接落该目录
