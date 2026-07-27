"""孤儿 tool_calls 清洗 + 会话加载损坏保护 测试。

feat/session-orphan-guard 分支。验证：
1. 含孤儿 tool_calls 的历史 → 清洗后每个 tool_call 都有配对
2. 游离 tool 消息 → 被删除
3. 干净历史 → 清洗前后逐字节一致（零误伤）
4. 损坏 JSON 文件 → 不抛异常、返回 None、原文件改名保留
5. 混合场景（孤儿调用 + 游离结果 + 正常配对）
"""

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ══════════════════════════════════════════════════════════════════
# 纯函数测试 — clean_orphan_tool_calls
# ══════════════════════════════════════════════════════════════════

from core.context import clean_orphan_tool_calls


class TestCleanOrphanToolCalls:
    """测试 clean_orphan_tool_calls 的三种孤儿形态。"""

    def test_orphan_assistant_tc_gets_placeholder(self):
        """assistant 发了 tool_calls 但没有 tool 结果 → 补占位。"""
        messages = [
            {"role": "user", "content": "帮我搜索"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"id": "call_abc", "type": "function",
                     "function": {"name": "web_search", "arguments": '{"q":"test"}'}},
                    {"id": "call_def", "type": "function",
                     "function": {"name": "read_file", "arguments": '{"path":"/x"}'}},
                ],
            },
            # tool 结果一条都没有 → 两个都是孤儿
        ]
        cleaned, report = clean_orphan_tool_calls(messages)

        assert report["inserted"] == 2
        assert report["removed"] == 0

        # 找到所有 tool 消息
        tool_msgs = [m for m in cleaned if m.get("role") == "tool"]
        assert len(tool_msgs) == 2

        # 每个占位 tool 消息应有正确的 tool_call_id 和内容
        tcs = {m["tool_call_id"]: m for m in tool_msgs}
        assert "call_abc" in tcs
        assert "call_def" in tcs
        assert tcs["call_abc"]["content"] == "[工具结果因中断丢失]"
        assert tcs["call_def"]["content"] == "[工具结果因中断丢失]"

        # 中继名前应正确记录
        assert tcs["call_abc"]["name"] == "web_search"
        assert tcs["call_def"]["name"] == "read_file"

    def test_orphan_tool_result_removed(self):
        """游离 tool 消息（无对应 assistant tool_calls）→ 删除。"""
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
            # 游离 tool 消息——没有 assistant 的 tool_calls 引用它
            {"role": "tool", "tool_call_id": "call_orphan", "content": "some result"},
            {"role": "user", "content": "next question"},
        ]
        cleaned, report = clean_orphan_tool_calls(messages)

        assert report["removed"] == 1
        assert report["inserted"] == 0

        tool_ids = [m.get("tool_call_id") for m in cleaned if m.get("role") == "tool"]
        assert "call_orphan" not in tool_ids

    def test_clean_history_untouched(self):
        """干净的完整配对历史 → 清洗前后一致（零误伤）。"""
        messages = [
            {"role": "user", "content": "search for Bobo"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"id": "call_1", "type": "function",
                     "function": {"name": "web_search", "arguments": '{"q":"Bobo"}'}},
                ],
            },
            {"role": "tool", "tool_call_id": "call_1", "content": "Bobo is an AI agent"},
            {"role": "assistant", "content": "Bobo 是一个 AI 助手"},
            {"role": "user", "content": "thanks"},
        ]
        cleaned, report = clean_orphan_tool_calls(messages)

        assert report["inserted"] == 0
        assert report["removed"] == 0
        assert len(cleaned) == len(messages)

        # 逐条目比对
        for i, (orig, clean) in enumerate(zip(messages, cleaned)):
            assert orig == clean, f"消息 {i} 不一致: orig={orig}, clean={clean}"

    def test_mixed_scenario(self):
        """混合场景：正常配对 + 孤儿调用 + 游离结果。"""
        messages = [
            {"role": "user", "content": "do things"},
            # 1. 正常配对
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"id": "call_ok", "type": "function",
                     "function": {"name": "get_time", "arguments": "{}"}},
                ],
            },
            {"role": "tool", "tool_call_id": "call_ok", "content": "2026-01-01"},
            # 2. 孤儿 assistant tool_call（无 tool 结果）
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"id": "call_bad", "type": "function",
                     "function": {"name": "crash_tool", "arguments": "{}"}},
                ],
            },
            # 3. 游离 tool 消息（无对应 assistant tool_calls）
            {"role": "tool", "tool_call_id": "call_stray", "content": "stray result"},
            {"role": "user", "content": "next"},
        ]
        cleaned, report = clean_orphan_tool_calls(messages)

        assert report["inserted"] == 1  # call_bad 补占位
        assert report["removed"] == 1   # call_stray 删除

        # 验证 call_ok 仍在且配对完整
        tool_msgs = [m for m in cleaned if m.get("role") == "tool"]
        tool_ids = {m["tool_call_id"]: m for m in tool_msgs}
        assert "call_ok" in tool_ids
        assert tool_ids["call_ok"]["content"] == "2026-01-01"

        # call_bad 应有占位
        assert "call_bad" in tool_ids
        assert tool_ids["call_bad"]["content"] == "[工具结果因中断丢失]"

        # call_stray 不应存在
        assert "call_stray" not in tool_ids

    def test_no_tool_messages_at_all(self):
        """纯文本对话无 tool → 清洗完全不改变。"""
        messages = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
            {"role": "user", "content": "how are you"},
            {"role": "assistant", "content": "fine"},
        ]
        cleaned, report = clean_orphan_tool_calls(messages)
        assert report["inserted"] == 0
        assert report["removed"] == 0
        assert cleaned == messages

    def test_partial_orphan_multiple_tcs_in_one_msg(self):
        """一个 assistant 有 3 个 tool_calls，其中 2 个有结果、1 个孤儿。"""
        messages = [
            {"role": "user", "content": "multi"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"id": "call_a", "type": "function",
                     "function": {"name": "tool_a", "arguments": "{}"}},
                    {"id": "call_b", "type": "function",
                     "function": {"name": "tool_b", "arguments": "{}"}},
                    {"id": "call_c", "type": "function",
                     "function": {"name": "tool_c", "arguments": "{}"}},
                ],
            },
            {"role": "tool", "tool_call_id": "call_a", "content": "result A"},
            {"role": "tool", "tool_call_id": "call_c", "content": "result C"},
            # call_b 无结果 → 孤儿
        ]
        cleaned, report = clean_orphan_tool_calls(messages)

        assert report["inserted"] == 1  # 只补 call_b
        assert report["removed"] == 0

        tool_msgs = [m for m in cleaned if m.get("role") == "tool"]
        tool_ids = {m["tool_call_id"]: m for m in tool_msgs}
        assert len(tool_msgs) == 3  # call_a + call_c + call_b 占位
        assert tool_ids["call_a"]["content"] == "result A"
        assert tool_ids["call_c"]["content"] == "result C"
        assert tool_ids["call_b"]["content"] == "[工具结果因中断丢失]"


# ══════════════════════════════════════════════════════════════════
# 集成测试 — SessionManager.load_session 加载 + 清洗
# ══════════════════════════════════════════════════════════════════

from core.session_manager import SessionManager


@pytest.fixture
def session_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


class TestLoadSessionWithOrphanGuard:
    """测试 SessionManager.load_session 的端到端行为。"""

    def test_load_with_orphans_cleans_on_load(self, session_dir):
        """构造带孤儿的会话文件 → load_session 清洗后历史合法。"""
        mgr = SessionManager(session_dir=session_dir, author="test")

        # 直接写入带孤儿的会话文件
        sid = "20260101_120000"
        session_path = Path(session_dir) / f"{sid}.json"
        orphan_session = {
            "_version": 1,
            "id": sid,
            "created_at": "2026-01-01T12:00:00",
            "title": "orphan test",
            "messages": [
                {"role": "user", "content": "search"},
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {"id": "call_x", "type": "function",
                         "function": {"name": "web_search", "arguments": '{"q":"x"}'}},
                    ],
                },
                # 无 tool 结果 → 孤儿
                {"role": "user", "content": "next"},
            ],
            "summary": None,
        }
        session_path.write_text(json.dumps(orphan_session), encoding="utf-8")

        # 加载
        session = mgr.load_session(sid)
        assert session is not None

        messages = session["messages"]
        # 应该有 user + assistant + tool占位 + user
        tool_msgs = [m for m in messages if m.get("role") == "tool"]
        assert len(tool_msgs) == 1
        assert tool_msgs[0]["tool_call_id"] == "call_x"
        assert tool_msgs[0]["content"] == "[工具结果因中断丢失]"

    def test_clean_session_loads_unchanged(self, session_dir):
        """干净会话 load 后消息完全不改动。"""
        mgr = SessionManager(session_dir=session_dir, author="test")
        sid = "20260102_120000"
        original_msgs = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]
        session_path = Path(session_dir) / f"{sid}.json"
        clean_session = {
            "_version": 1,
            "id": sid,
            "created_at": "2026-01-02T12:00:00",
            "title": "clean",
            "messages": original_msgs,
            "summary": None,
        }
        session_path.write_text(json.dumps(clean_session), encoding="utf-8")

        session = mgr.load_session(sid)
        assert session is not None
        assert session["messages"] == original_msgs


# ══════════════════════════════════════════════════════════════════
# 损坏 JSON 文件保护
# ══════════════════════════════════════════════════════════════════

class TestCorruptedSessionFile:
    """测试损坏 JSON 文件的优雅降级。"""

    def test_corrupted_json_returns_none(self, session_dir):
        """损坏 JSON → load_session 返回 None，不抛异常。"""
        mgr = SessionManager(session_dir=session_dir, author="test")
        sid = "20260103_120000"
        session_path = Path(session_dir) / f"{sid}.json"
        # 写一半崩溃的 JSON
        session_path.write_text('{"id": "broken", "messages": [{"role": "user", "con', encoding="utf-8")

        result = mgr.load_session(sid)
        assert result is None

    def test_corrupted_json_renames_original(self, session_dir):
        """损坏 JSON 的原文件被保留为 .corrupted 副本。"""
        mgr = SessionManager(session_dir=session_dir, author="test")
        sid = "20260104_120000"
        session_path = Path(session_dir) / f"{sid}.json"
        original_content = '{"broken": true garbage here'
        session_path.write_text(original_content, encoding="utf-8")

        result = mgr.load_session(sid)
        assert result is None

        # 原文件应还在（未被删除）
        assert session_path.exists()
        assert session_path.read_text(encoding="utf-8") == original_content

        # .corrupted 副本应存在
        corrupted_path = Path(session_dir) / f"{sid}.json.corrupted"
        assert corrupted_path.exists()
        assert corrupted_path.read_text(encoding="utf-8") == original_content

    def test_valid_json_after_corruption(self, session_dir):
        """损坏的保护不影响后续正常加载。"""
        mgr = SessionManager(session_dir=session_dir, author="test")

        # 先写损坏的
        bad_path = Path(session_dir) / "bad.json"
        bad_path.write_text("not json", encoding="utf-8")
        assert mgr.load_session("bad") is None

        # 再写正常的
        good_path = Path(session_dir) / "good.json"
        good_path.write_text(json.dumps({
            "_version": 1, "id": "good",
            "created_at": "2026-01-01T12:00:00",
            "title": "good", "messages": [], "summary": None,
        }), encoding="utf-8")
        session = mgr.load_session("good")
        assert session is not None
        assert session["id"] == "good"

    def test_nonexistent_session_returns_none(self, session_dir):
        """不存在的会话 ID → 返回 None，不 crash。"""
        mgr = SessionManager(session_dir=session_dir, author="test")
        result = mgr.load_session("nonexistent_999")
        assert result is None
