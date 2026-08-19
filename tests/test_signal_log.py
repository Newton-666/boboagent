# -*- coding: utf-8 -*-
"""票 P0-2 回归测试：信号日志化双通道（只记录不动作）。

覆盖（票施工项 4）：
1. 信号写入：构造"以后都用 diff 展示" → 写 signal_log.jsonl 且
   knowledge_base.json md5 零变化（零动作铁律）；
2. 普通对话零误写（无特征词不触发、LLM 判定为假不写）；
3. 同类信号去重：同会话重复 → 只 1 条；
4. 通道 B：临时 library 结构 → 统计正确、排除 agent开发/；
5. LLM 失败静默降级：mock 抛异常 → 不阻塞、logged=False、无残留。
"""

import hashlib
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools import signal_logger  # noqa: E402
from tools.signal_library_stats import compute_stats  # noqa: E402
from tests.mock_llm import text_response  # noqa: E402

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KB_PATH = os.path.join(PROJECT_ROOT, "data", "knowledge_base.json")


def _kb_md5() -> str:
    """knowledge_base.json 当前 md5（只读不改动）。"""
    with open(KB_PATH, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def _make_llm(judgement: str = "") -> callable:
    """构造返回指定 JSON 判定的 mock LLM。"""
    return lambda prompt, use_tools=False, max_tokens=150, **kw: (
        text_response(judgement))


@pytest.fixture
def signal_env(tmp_path, monkeypatch):
    """隔离的信号日志路径 + knowledge_base md5 快照。"""
    log_file = tmp_path / "signal_log.jsonl"
    monkeypatch.setattr(signal_logger, "_SIGNAL_LOG", str(log_file))
    monkeypatch.setattr(signal_logger, "_LOG_DIR", str(tmp_path))
    md5_before = _kb_md5()
    yield log_file
    # 零动作铁律：日志写入后 knowledge_base.json 必须零变化
    assert _kb_md5() == md5_before, "knowledge_base.json 被改动——零动作铁律违反"


def _read_log(log_file) -> list[dict]:
    if not os.path.exists(log_file):
        return []
    with open(log_file, "r", encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


# ── 1. 信号写入 + 零动作铁律 ──
def test_signal_written_and_kb_unchanged(signal_env):
    log_file = signal_env
    llm = _make_llm('{"is_signal": true, "signal_type": "workflow", '
                    '"judgement": "用户要求以后都用 diff 展示代码变更"}')
    result = signal_logger.judge_and_log_signal(
        "以后都用 diff 展示代码变更", "sess-1", llm)

    assert result["logged"] is True, result
    assert result["llm_called"] is True
    records = _read_log(log_file)
    assert len(records) == 1
    rec = records[0]
    assert rec["signal_type"] == "workflow"
    assert rec["session_id"] == "sess-1"
    assert rec["source"] == "conversation"
    assert "diff" in rec["judgement"]  # judgement 原话保留
    assert "ts" in rec and rec["user_text"]


# ── 2. 普通对话零误写 ──
def test_normal_conversation_no_keyword_no_write(signal_env):
    log_file = signal_env
    called = {"n": 0}

    def llm(prompt, use_tools=False, max_tokens=150, **kw):
        called["n"] += 1
        return text_response("{}")

    result = signal_logger.judge_and_log_signal(
        "今天天气不错，我们去吃火锅吧", "sess-2", llm)

    assert result["logged"] is False
    assert result["reason"] == "no_keyword"
    assert called["n"] == 0  # 零 LLM 成本
    assert _read_log(log_file) == []


def test_normal_conversation_llm_says_no(signal_env):
    log_file = signal_env
    llm = _make_llm('{"is_signal": false, "signal_type": "", '
                    '"judgement": "普通叙述不是信号"}')
    result = signal_logger.judge_and_log_signal(
        "以后的项目排期记得提前告诉我", "sess-3", llm)

    assert result["logged"] is False
    assert result["reason"] == "no_signal"
    assert _read_log(log_file) == []


# ── 3. 同类信号去重 ──
def test_dedup_same_session_same_type(signal_env):
    log_file = signal_env
    judgement = ('{"is_signal": true, "signal_type": "workflow", '
                 '"judgement": "工作流模式"}')
    llm = _make_llm(judgement)

    r1 = signal_logger.judge_and_log_signal(
        "以后都用 diff 展示", "sess-4", llm)
    assert r1["logged"] is True

    r2 = signal_logger.judge_and_log_signal(
        "以后都先跑测试再提交", "sess-4", llm)
    assert r2["logged"] is False
    assert r2["reason"] == "dup_type"

    assert len(_read_log(log_file)) == 1  # 只 1 条

    # 不同会话同类型 → 允许各自记录
    r3 = signal_logger.judge_and_log_signal(
        "以后都用中文回复", "sess-5", llm)
    assert r3["logged"] is True
    assert len(_read_log(log_file)) == 2


# ── 4. 通道 B：统计正确 + 排除 agent开发 ──
def test_channel_b_stats_exclude_agentdev(tmp_path):
    lib = tmp_path / "library"
    (lib / "生活").mkdir(parents=True)
    (lib / "技术研究").mkdir(parents=True)
    (lib / "agent开发").mkdir(parents=True)
    # 主题笔记
    (lib / "生活" / "早睡.md").write_text(
        "---\ntopic: 早睡\nversion: 2\n---\n内容", encoding="utf-8")
    (lib / "技术研究" / "向量化.md").write_text(
        "---\ntopic: 向量化\nversion: 1\n---\n内容", encoding="utf-8")
    # agent开发/ 施工报告（必须排除）
    (lib / "agent开发" / "TICKET-P0-1完成报告.md").write_text(
        "---\ntopic: TICKET-P0-1完成报告\nversion: 3\n---\n内容", encoding="utf-8")
    # 根级索引（排除）
    (lib / "index.md").write_text("# index", encoding="utf-8")

    stats = compute_stats(days=30, lib_root=str(lib))

    topics = {t["topic"]: t for t in stats["topics"]}
    assert "早睡" in topics and topics["早睡"]["files"] == 1
    assert "向量化" in topics and topics["向量化"]["writes_30d"] == 1
    assert "TICKET-P0-1完成报告" not in topics  # agent开发 已排除
    assert stats["total_files"] == 2
    assert stats["excluded_dirs"] == ["agent开发"]


# ── 5. LLM 失败静默降级 ──
def test_llm_failure_silent_degrade(signal_env):
    log_file = signal_env

    def broken_llm(prompt, use_tools=False, max_tokens=150, **kw):
        raise TimeoutError("simulated llm timeout")

    result = signal_logger.judge_and_log_signal(
        "以后都用 diff 展示", "sess-6", broken_llm)

    assert result["logged"] is False
    assert result["reason"] == "llm_error"
    assert result["llm_called"] is True
    assert _read_log(log_file) == []  # 无残留
