"""GitHub #11：loop_detect 只读调研误杀 vs 真绕圈（含变参）。

验收：
- 连续多轮只读/调研（不同文件、检索词、URL）不得判 stuck
- 同模式、两签名变参绕圈仍 stuck
- 写类工具 / 新工具种类仍算推进
- 漏杀降级：窗口内每次都换新参数的长绕圈会判 progressing，
  由撞线软收尾 + 深度/步数保险丝兜底（见 judge_loop_verdict 文档）
"""
from __future__ import annotations

import json

from core.loop_detect import (
    has_progress_signal,
    judge_loop_verdict,
    last_n_tool_rounds,
    round_sig,
)


def _round(tool_parts):
    tcs = [
        {"id": f"call_{i}", "type": "function",
         "function": {"name": name, "arguments": args}}
        for i, (name, args) in enumerate(tool_parts)
    ]
    return {"role": "assistant", "content": "thinking...", "tool_calls": tcs}


def _hist(rounds):
    return [_round(r) for r in rounds]


def _args(**kwargs):
    return json.dumps(kwargs)


class TestRoundSig:
    def test_key_order_normalized(self):
        a = [{"function": {"name": "read_local_file",
                           "arguments": '{"b":1,"a":2}'}}]
        b = [{"function": {"name": "read_local_file",
                           "arguments": '{"a":2,"b":1}'}}]
        assert round_sig(a) == round_sig(b)

    def test_dict_arguments_normalized(self):
        a = [{"function": {"name": "grep_code",
                           "arguments": {"pattern": "foo", "path": "src"}}}]
        b = [{"function": {"name": "grep_code",
                           "arguments": '{"path":"src","pattern":"foo"}'}}]
        assert round_sig(a) == round_sig(b)


class TestReadonlyResearchNotStuck:
    """只读/调研多轮：目标在扩展 → progressing。"""

    def test_five_distinct_files(self):
        history = _hist([
            [("read_local_file", _args(filepath=f"/tmp/f{i}"))]
            for i in range(5)
        ])
        verdict, reason = judge_loop_verdict(history)
        assert verdict == "progressing", reason
        assert "调研目标" in reason

    def test_mixed_research_tools(self):
        history = _hist([
            [("grep_code", _args(pattern="loop_detect", path="core"))],
            [("read_local_file", _args(filepath="core/loop_detect.py"))],
            [("web_search", _args(query="agent loop detection"))],
            [("web_fetch", _args(url="https://example.com/a"))],
            [("read_local_file", _args(filepath="core/engine.py"))],
        ])
        verdict, reason = judge_loop_verdict(history)
        assert verdict == "progressing", reason

    def test_grep_expanding_patterns(self):
        history = _hist([
            [("grep_code", _args(pattern=p, path="src"))]
            for p in ("foo", "bar", "baz", "qux", "quux")
        ])
        verdict, reason = judge_loop_verdict(history)
        assert verdict == "progressing", reason

    def test_pagination_same_file_is_progress(self):
        history = _hist([
            [("read_local_file", _args(filepath="/tmp/big.py", offset=i, limit=80))]
            for i in (0, 80, 160, 240, 320)
        ])
        verdict, reason = judge_loop_verdict(history)
        assert verdict == "progressing", reason

    def test_long_history_still_exploring(self):
        """更早轮次已用过 read_local_file，最近 5 轮仍在读新文件。"""
        earlier = [
            [("read_local_file", _args(filepath=f"/old/{i}"))]
            for i in range(10)
        ]
        recent = [
            [("read_local_file", _args(filepath=f"/new/{i}"))]
            for i in range(5)
        ]
        verdict, reason = judge_loop_verdict(_hist(earlier + recent))
        assert verdict == "progressing", reason


class TestRealLoopsStillStuck:
    def test_identical_signature(self):
        history = _hist([
            [("read_local_file", _args(filepath="/tmp/x.py"))]
            for _ in range(5)
        ])
        verdict, reason = judge_loop_verdict(history)
        assert verdict == "stuck", reason
        assert "同模式" in reason

    def test_two_file_arg_cycle(self):
        history = _hist([
            [("read_local_file", _args(filepath="/tmp/a.py" if i % 2 == 0 else "/tmp/b.py"))]
            for i in range(5)
        ])
        verdict, reason = judge_loop_verdict(history)
        assert verdict == "stuck", reason
        assert "变参绕圈" in reason

    def test_two_query_web_search_cycle(self):
        history = _hist([
            [("web_search", _args(query="alpha" if i % 2 == 0 else "beta"))]
            for i in range(5)
        ])
        verdict, reason = judge_loop_verdict(history)
        assert verdict == "stuck", reason
        assert "变参绕圈" in reason

    def test_grep_two_pattern_cycle(self):
        history = _hist([
            [("grep_code", _args(pattern="TODO" if i % 2 == 0 else "FIXME", path="src"))]
            for i in range(5)
        ])
        verdict, reason = judge_loop_verdict(history)
        assert verdict == "stuck", reason

    def test_offset_oscillation_same_file(self):
        """同一文件 offset 在 0/100 间振荡 → 变参绕圈，不是翻页推进。"""
        history = _hist([
            [("read_local_file",
              _args(filepath="/tmp/big.py", offset=0 if i % 2 == 0 else 100, limit=80))]
            for i in range(5)
        ])
        verdict, reason = judge_loop_verdict(history)
        assert verdict == "stuck", reason

    def test_write_still_progressing(self):
        history = _hist([
            [("read_local_file", _args(filepath="/a"))],
            [("grep_code", _args(pattern="foo"))],
            [("edit_file", _args(file_path="/a", old_string="x", new_string="y"))],
            [("list_directory", _args(path="/b"))],
            [("execute_terminal", _args(command="ls"))],
        ])
        verdict, reason = judge_loop_verdict(history)
        assert verdict == "progressing", reason
        assert "写类工具" in reason

    def test_new_tool_kind_is_progress(self):
        earlier = [
            [("read_local_file", _args(filepath=f"/old/{i}.py"))]
            for i in range(5)
        ]
        recent = [
            [("web_search", _args(query=q))]
            for q in ("alpha", "beta", "gamma", "alpha", "beta")
        ]
        # 最近 5 轮签名种数=3，不是 ≤2 绕圈；web_search 相对更早的 read 是新工具种类
        verdict, reason = judge_loop_verdict(_hist(earlier + recent))
        assert verdict == "progressing", reason
        assert "新工具种类" in reason


class TestDegradePathDocumented:
    def test_five_unique_args_same_tool_is_progress_not_hard_kill(self):
        """每次换全新参数的绕圈看起来像调研 → progressing（明确漏杀，靠软收尾降级）。"""
        history = _hist([
            [("read_local_file", _args(filepath=f"/tmp/never-repeat-{i}.py"))]
            for i in range(5)
        ])
        verdict, reason = judge_loop_verdict(history)
        assert verdict == "progressing", reason

    def test_has_progress_reports_diversity(self):
        history = _hist([
            [("read_local_file", _args(filepath=f"/tmp/f{i}"))]
            for i in range(5)
        ])
        recent = last_n_tool_rounds(history, 5)
        ok, why = has_progress_signal(history, recent)
        assert ok is True
        assert "调研目标" in why
