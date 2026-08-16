"""票 COST-1c 专项测试：缓存字段透传 + 每次 LLM 调用落账 + 工具 target 全抓取。

票面验收口径（全部实跑）：
- ① cache_hit_tokens / cache_miss_tokens：llm.usage 事件（API 原样）→ 透传落盘非 null
- ② 逐次累计：usage_calls / prompt_tokens_sum / completion_tokens_sum = 事件逐次累加真值；
   快照字段（prompt_tokens/completion_tokens）保留不动；其他会话事件不串账
- ③ 工具 target 全抓取：终端 command（截 120）/ 文件 filepath/path / grep pattern@path /
   obsidian filename；取不到落空串不编造
- repeat_reads 侦测：同 target ≥2 触发
- null 诚实口径：事件观测不到 → cache null、usage_calls 0（不编造）
"""

import json
import time
from pathlib import Path

from bobo_tui_gateway.metrics import MetricsSink, _tool_target


def _write_events(path: Path, events: list[dict]):
    with open(path, "w", encoding="utf-8") as f:
        for ev in events:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")


def _finalize(metrics_path: Path, events_path: Path, sid="s1",
              complete_usage=None, tool_events=None) -> dict:
    """驱动一轮事件流（message.start → tool.start* → message.complete），返回落盘行。"""
    sink = MetricsSink(metrics_path=metrics_path, events_path=events_path)
    sink.on_event("message.start", sid, {})
    for te in tool_events or []:
        sink.on_event("tool.start", sid, te)
    sink.on_event("message.complete", sid, {"usage": complete_usage or {}})
    with open(metrics_path, encoding="utf-8") as f:
        return json.loads(f.read().strip().splitlines()[-1])


def _usage_ev(sid: str, prompt: int, completion: int, cache_hit=None, cache_miss=None) -> dict:
    u = {"prompt_tokens": prompt, "completion_tokens": completion}
    if cache_hit is not None:
        u["prompt_cache_hit_tokens"] = cache_hit
    if cache_miss is not None:
        u["prompt_cache_miss_tokens"] = cache_miss
    return {"ts": time.time(), "type": "llm.usage", "session_id": sid, "usage": u}


def _call_ev(sid: str, prompt: int, completion: int) -> dict:
    """engine 逐次调用事件（llm.call，真实值）。"""
    return {"ts": time.time(), "type": "llm.call", "session_id": sid,
            "prompt_tokens": prompt, "completion_tokens": completion}


# ── ① 缓存字段透传 ──

def test_cache_fields_transparent(tmp_path):
    """① DeepSeek cache 字段经 llm.usage 事件原样透传到落盘行（非 null）。"""
    ev = tmp_path / "events.jsonl"
    _write_events(ev, [_usage_ev("s1", 100, 10, cache_hit=60, cache_miss=40)])
    row = _finalize(tmp_path / "rounds.jsonl", ev)
    assert row["usage"]["cache_hit_tokens"] == 60
    assert row["usage"]["cache_miss_tokens"] == 40


def test_cache_takes_latest_event(tmp_path):
    """① 多次调用取最近一次携带 cache 的事件值（API 原样，非首条）。"""
    ev = tmp_path / "events.jsonl"
    _write_events(ev, [
        _usage_ev("s1", 100, 10, cache_hit=50, cache_miss=50),
        _usage_ev("s1", 200, 20, cache_hit=150, cache_miss=50),
    ])
    row = _finalize(tmp_path / "rounds.jsonl", ev)
    assert row["usage"]["cache_hit_tokens"] == 150
    assert row["usage"]["cache_miss_tokens"] == 50


# ── ② 每次 LLM 调用逐次累计 ──

def test_per_call_accumulation(tmp_path):
    """② 三次调用（llm.call 事件）→ usage_calls=3、sums=逐次累加真值；快照保留末次。"""
    ev = tmp_path / "events.jsonl"
    _write_events(ev, [
        _call_ev("s1", 100, 10),
        _call_ev("s1", 200, 20),
        _call_ev("s1", 300, 30),
    ])
    row = _finalize(tmp_path / "rounds.jsonl", ev,
                    complete_usage={"prompt_tokens": 300, "completion_tokens": 30})
    u = row["usage"]
    assert u["usage_calls"] == 3
    assert u["prompt_tokens_sum"] == 600
    assert u["completion_tokens_sum"] == 60
    # 快照字段保留不动（末次调用快照）
    assert u["prompt_tokens"] == 300
    assert u["completion_tokens"] == 30


def test_cache_plus_calls_not_double_counted(tmp_path):
    """② llm.usage 只供 cache，不参与 usage_calls 计数（防同一调用双计）。"""
    ev = tmp_path / "events.jsonl"
    _write_events(ev, [
        _call_ev("s1", 100, 10),
        _usage_ev("s1", 100, 10, cache_hit=60, cache_miss=40),  # 同一次调用的 cache 透传
    ])
    row = _finalize(tmp_path / "rounds.jsonl", ev)
    u = row["usage"]
    assert u["usage_calls"] == 1          # 只数 llm.call
    assert u["prompt_tokens_sum"] == 100
    assert u["cache_hit_tokens"] == 60    # cache 从 llm.usage 取
    assert u["cache_miss_tokens"] == 40


def test_other_sid_not_counted(tmp_path):
    """② 其他会话的调用事件不串账（按 session_id 过滤）。"""
    ev = tmp_path / "events.jsonl"
    _write_events(ev, [
        _call_ev("OTHER", 999, 99),
        _usage_ev("OTHER", 999, 99, cache_hit=1, cache_miss=2),
    ])
    row = _finalize(tmp_path / "rounds.jsonl", ev)
    assert row["usage"]["usage_calls"] == 0
    assert row["usage"]["prompt_tokens_sum"] == 0
    assert row["usage"]["cache_hit_tokens"] is None


def test_snapshot_fallback_input_output(tmp_path):
    """② 快照口径兼容 adapter 重构格式（input/output）——COST-1b 行为不回退。"""
    ev = tmp_path / "events.jsonl"  # 无事件
    row = _finalize(tmp_path / "rounds.jsonl", ev,
                    complete_usage={"input": 1234, "output": 567})
    assert row["usage"]["prompt_tokens"] == 1234
    assert row["usage"]["completion_tokens"] == 567


# ── ③ 工具 target 全抓取 ──

def test_tool_target_terminal_truncated():
    """③ 终端取 command，超 120 字符截断。"""
    assert _tool_target("execute_terminal", {"command": "x" * 200}) == "x" * 120
    assert _tool_target("execute_terminal", {"command": "ls -la"}) == "ls -la"
    assert _tool_target("execute_terminal", {}) == ""
    assert _tool_target("execute_terminal", None) == ""


def test_tool_target_file_grep_obsidian():
    """③ 文件类 filepath/path、grep 类 pattern@path、obsidian 类 filename。"""
    assert _tool_target("read_local_file", {"filepath": "/a/b.py"}) == "/a/b.py"
    assert _tool_target("edit_file", {"file_path": "/a/b.py", "old_string": "x"}) == "/a/b.py"
    assert _tool_target("file_operation", {"action": "read", "path": "/a/b.py"}) == "/a/b.py"
    assert _tool_target("file_writer", {"path": "/a/new.py"}) == "/a/new.py"
    assert _tool_target("grep_code", {"pattern": "def test", "path": "/a"}) == "def test@/a"
    assert _tool_target("grep_code", {"pattern": "def test"}) == "def test@"
    assert _tool_target("read_obsidian", {"filename": "notes/x.md"}) == "notes/x.md"
    assert _tool_target("write_obsidian", {"filename": "notes/y.md", "content": "c"}) == "notes/y.md"
    # 取不到 → 空串（不编造）
    assert _tool_target("unknown_tool", {"foo": "bar"}) == ""
    assert _tool_target("grep_code", {}) == ""


def test_targets_recorded_in_round(tmp_path):
    """③ tool.start 落账行 target 正确抓取。"""
    ev = tmp_path / "events.jsonl"
    row = _finalize(tmp_path / "rounds.jsonl", ev, tool_events=[
        {"name": "execute_terminal", "arguments": {"command": "cd /x && pwd"}},
        {"name": "grep_code", "arguments": {"pattern": "cache", "path": "core"}},
        {"name": "read_obsidian", "arguments": {"filename": "n.md"}},
    ])
    tgts = [t["target"] for t in row["tools"]]
    assert tgts == ["cd /x && pwd", "cache@core", "n.md"]


# ── repeat_reads 侦测（target 抓取后要真能触发）──

def test_repeat_reads_triggered(tmp_path):
    """③ repeat_reads：同 target 读 ≥2 次才列；单次不列。"""
    ev = tmp_path / "events.jsonl"
    row = _finalize(tmp_path / "rounds.jsonl", ev, tool_events=[
        {"name": "read_local_file", "arguments": {"filepath": "/a/x.py"}},
        {"name": "read_local_file", "arguments": {"filepath": "/a/x.py"}},
        {"name": "read_local_file", "arguments": {"filepath": "/b/y.py"}},
    ])
    assert row["repeat_reads"] == [{"target": "/a/x.py", "count": 2}]


def test_repeat_reads_grep_pattern_at_path(tmp_path):
    """③ grep 类按 pattern@path 计重复（新格式）。"""
    ev = tmp_path / "events.jsonl"
    row = _finalize(tmp_path / "rounds.jsonl", ev, tool_events=[
        {"name": "grep_code", "arguments": {"pattern": "def ", "path": "core/"}},
        {"name": "grep_code", "arguments": {"pattern": "def ", "path": "core/"}},
    ])
    assert row["repeat_reads"] == [{"target": "def @core/", "count": 2}]


# ── null 诚实口径 ──

def test_null_honesty(tmp_path):
    """事件观测不到 → cache null、usage_calls 0（不编造）；target 取不到空串。"""
    ev = tmp_path / "events.jsonl"  # 不存在
    row = _finalize(tmp_path / "rounds.jsonl", ev)
    u = row["usage"]
    assert u["cache_hit_tokens"] is None
    assert u["cache_miss_tokens"] is None
    assert u["usage_calls"] == 0
    assert u["prompt_tokens_sum"] == 0
    assert u["completion_tokens_sum"] == 0
