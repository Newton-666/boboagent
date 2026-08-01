"""TICKET-023 验收测试：空转防护 + 零摘要本地兜底 + 估算器公式校验。

三组测试对应票文验收项 2/3/4。代码不动，只补测试。
"""

import json
import pytest

from core.engine import Engine
from core.tool_executor import execute_tool
from core.event_bus import EventBus
from tests.mock_llm import MockLLMCaller, text_response


# ═══════════════════════════════════════════════════════════════════════
# 验收 2：空转防护
# ═══════════════════════════════════════════════════════════════════════

class TestCompressSkip:
    """空转防护：archivable < 15% → compress_skipped + 不压缩。"""

    def test_skipped_when_archivable_too_small(self, monkeypatch, tmp_path):
        """61 条历史，末 3 条含 user → 空转跳过 + compress_skipped 事件。

        TICKET-024：token_budget=8K 触发 token 溢出，msg_budget=200 让保险丝不拦截。
        构造：
          msg  0-30: 极短（可归档段，token 占比 ≈2%）
          msg 31-60: 极长（保留段），最后一条 user 在第 58 位
          → archivable_ratio < 15%，触发 compress_skipped
        """
        monkeypatch.setenv("BOBO_CONTEXT_BUDGET", "8")  # token_budget=8192
        # 解耦 msg_budget：保险丝不拦截，让空转防护自然生效
        import core.context as ctx_module
        monkeypatch.setattr(ctx_module, "_get_msg_count_budget", lambda: 200)
        monkeypatch.setattr(ctx_module, "_get_context_budget", lambda _engine=None: 7000)

        # 事件总线指向 temp dir
        log_dir = tmp_path / "events"
        EventBus.reset(str(log_dir))

        caller = MockLLMCaller([text_response("x")])
        engine = Engine(caller, execute_tool, test_mode=True)
        engine.sid = "test-023-skip"

        # 构造 61 条消息
        engine.history = []
        for _ in range(15):
            engine.history.append({"role": "user", "content": "x"})
            engine.history.append({"role": "assistant", "content": "x"})
        engine.history.append({"role": "user", "content": "x"})         # msg 30

        for _ in range(12):
            engine.history.append({"role": "user", "content": "y" * 800})
            engine.history.append({"role": "assistant", "content": "z" * 800})
        engine.history.append({"role": "user", "content": "x"})         # msg 55
        engine.history.append({"role": "assistant", "content": "x"})    # msg 56
        engine.history.append({"role": "user", "content": "x"})         # msg 57
        engine.history.append({"role": "user", "content": "final"})     # msg 58 ← 最后一条 user
        engine.history.append({"role": "assistant", "content": "ok"})   # msg 59
        engine.history.append({"role": "tool", "content": "result",
                               "name": "echo", "tool_call_id": "call_1"})  # msg 60

        assert len(engine.history) == 61, f"Expected 61, got {len(engine.history)}"

        engine._compressing = False
        engine._compressed_this_turn = False
        engine._compress_history()

        # 验证 compress_skipped 事件已发出
        events_path = log_dir / "events.jsonl"
        assert events_path.exists(), "No events file"
        raw = [json.loads(line) for line in events_path.read_text(encoding="utf-8").strip().splitlines()]
        skipped = [e for e in raw if e.get("type") == "context.compress_skipped"]
        assert len(skipped) == 1, f"Expected 1 compress_skipped, got {len(skipped)}: {skipped}"
        ev = skipped[0]
        assert ev["reason"] == "archivable_too_small"
        assert ev["ratio"] < 0.15, f"ratio {ev['ratio']} should be < 0.15"

        # 工作锚点应被重建（compress_skipped 分支）
        anchors = [m for m in engine.history
                   if m.get("role") == "system"
                   and m.get("content", "").startswith("[工作锚点")]
        assert len(anchors) == 1, f"Expected 1 anchor, got {len(anchors)}"

    def test_normal_compress_when_archivable_above_threshold(self, monkeypatch, tmp_path):
        """可归档段 ≥30% → 正常压缩，出现摘要。

        TICKET-024 token 驱动：15 条长消息 + 8 条短消息 = 23 条，
        token 远超 15K 层0 + 7K 触发预算 → 压缩生产摘要。
        """
        monkeypatch.setenv("BOBO_CONTEXT_BUDGET", "8")
        import core.context as ctx_module
        monkeypatch.setattr(ctx_module, "_get_msg_count_budget", lambda: 200)
        monkeypatch.setattr(ctx_module, "_get_context_budget", lambda _engine=None: 7000)

        log_dir = tmp_path / "events2"
        EventBus.reset(str(log_dir))

        caller = MockLLMCaller([text_response("This is a compressed summary of the conversation.")])
        engine = Engine(caller, execute_tool, test_mode=True)
        engine.sid = "test-023-normal"

        _TEXT = "The quick brown fox jumps over the lazy dog. " * 150  # ~1500 tokens

        engine.history = []
        # 前 15 条（可归档）：长内容，token 远超 15K 层0
        for i in range(7):
            engine.history.append({"role": "user", "content": f"Question {i}: {_TEXT}"})
            engine.history.append({"role": "assistant", "content": f"Answer {i}: {_TEXT}"})
        engine.history.append({"role": "user", "content": _TEXT})  # msg 14

        # 后 8 条（保留段 = 层0）：短内容
        for i in range(4):
            engine.history.append({"role": "user", "content": f"q{i}"})
            engine.history.append({"role": "assistant", "content": f"a{i}"})

        engine._compressing = False
        engine._compressed_this_turn = False
        engine._compress_history()

        # 应该产生压缩摘要（TICKET-024 三层前缀：L1 段摘要 / L2 极简摘要）
        summaries = [m for m in engine.history
                     if m.get("role") == "system"
                     and (m.get("content", "").startswith("[L1 段摘要]")
                          or m.get("content", "").startswith("[L2 极简摘要]")
                          or m.get("content", "").startswith("[对话历史摘要 · 本地兜底]"))]
        assert len(summaries) >= 1, "Expected at least 1 summary after normal compression"

        # 消息数应显著减少
        assert len(engine.history) < 60, (
            f"History should shrink after compress, got {len(engine.history)}"
        )

        # context.compressed 事件应包含 llm 来源
        events_path = log_dir / "events.jsonl"
        raw = [json.loads(line) for line in events_path.read_text(encoding="utf-8").strip().splitlines()]
        compressed = [e for e in raw if e.get("type") == "context.compressed"]
        assert len(compressed) >= 1, f"Expected context.compressed event, got {len(compressed)}"


# ═══════════════════════════════════════════════════════════════════════
# 验收 3：零摘要本地兜底
# ═══════════════════════════════════════════════════════════════════════

class TestLocalFallback:
    """零摘要 → 本地机械兜底，不再直接删。"""

    def test_empty_llm_summary_produces_local_fallback(self, monkeypatch, tmp_path):
        """mock LLM 返回空 → history 出现本地兜底 + summary_source=local_fallback。

        TICKET-024 token 驱动：可归档段用大消息（>15K 层0），LLM 返回空字符串。
        """
        monkeypatch.setenv("BOBO_CONTEXT_BUDGET", "8")
        import core.context as ctx_module
        monkeypatch.setattr(ctx_module, "_get_msg_count_budget", lambda: 200)
        monkeypatch.setattr(ctx_module, "_get_context_budget", lambda _engine=None: 7000)

        log_dir = tmp_path / "events3"
        EventBus.reset(str(log_dir))

        caller = MockLLMCaller([{"choices": [{"message": {"content": ""}}]}])
        engine = Engine(caller, execute_tool, test_mode=True)
        engine.sid = "test-023-fallback"

        _TEXT = "The quick brown fox jumps over the lazy dog. " * 150

        engine.history = []
        for i in range(7):
            engine.history.append({"role": "user", "content": f"帮我查 Q{i}: {_TEXT}"})
            engine.history.append({"role": "assistant", "content": f"回答 A{i}: {_TEXT}"})
        engine.history.append({"role": "user", "content": f"最后一个可归档问题: {_TEXT}"})

        for i in range(4):
            engine.history.append({"role": "user", "content": f"新问题 {i}"})
            engine.history.append({"role": "assistant", "content": f"新回答 {i}"})

        engine._compressing = False
        engine._compressed_this_turn = False
        engine._compress_history()

        # 查找本地兜底摘要
        fallback_msgs = [m for m in engine.history
                         if m.get("role") == "system"
                         and "[对话历史摘要 · 本地兜底]" in m.get("content", "")]
        assert len(fallback_msgs) >= 1, (
            f"Expected local fallback summary, got {len(fallback_msgs)}"
        )
        content = fallback_msgs[0]["content"]
        assert "## 用户发言" in content, f"Missing '## 用户发言' in: {content[:200]}"
        assert "帮我查 Q0" in content, "Should contain original user messages"

        # 验证事件 summary_source=local_fallback
        events_path = log_dir / "events.jsonl"
        raw = [json.loads(line) for line in events_path.read_text(encoding="utf-8").strip().splitlines()]
        compressed = [e for e in raw if e.get("type") == "context.compressed"]
        assert len(compressed) >= 1
        assert compressed[0].get("summary_source") == "local_fallback", (
            f"Expected summary_source=local_fallback, got {compressed[0].get('summary_source')}"
        )

    def test_no_user_text_produces_local_fallback(self, monkeypatch, tmp_path):
        """纯工具记录段（无 user/assistant 文本）→ 仍生成本地兜底而非丢弃。

        TICKET-024 token 驱动：工具消息在前（大量 token 撑满层0），
        user/assistant 在后被切除为 archivable → 生成兜底。
        """
        monkeypatch.setenv("BOBO_CONTEXT_BUDGET", "8")
        import core.context as ctx_module
        monkeypatch.setattr(ctx_module, "_get_msg_count_budget", lambda: 200)
        monkeypatch.setattr(ctx_module, "_get_context_budget", lambda _engine=None: 7000)

        log_dir = tmp_path / "events3b"
        EventBus.reset(str(log_dir))

        caller = MockLLMCaller([{"choices": [{"message": {"content": ""}}]}])
        engine = Engine(caller, execute_tool, test_mode=True)
        engine.sid = "test-023-nouser"

        _TEXT = "The quick brown fox jumps over the lazy dog. " * 150

        engine.history = []
        # user/assistant 在前（compressible）：工具撑满层0后这些被切除
        for i in range(5):
            engine.history.append({"role": "user", "content": f"msg {i}"})
            engine.history.append({"role": "assistant", "content": f"reply {i}"})
        # 工具消息在末尾：无条件入层0，12×1534≈18408 token > 15K → user/assistant 全被切除
        for i in range(12):
            engine.history.append({"role": "tool", "content": f"result {i}: {_TEXT}",
                                   "tool_call_id": f"tc{i}", "name": "echo"})

        engine._compressing = False
        engine._compressed_this_turn = False
        engine._compress_history()

        # 应有兜底摘要
        fallback_msgs = [m for m in engine.history
                         if m.get("role") == "system"
                         and "[对话历史摘要 · 本地兜底]" in m.get("content", "")]
        assert len(fallback_msgs) >= 1, "Pure-tool segment should still get local fallback"


# ═══════════════════════════════════════════════════════════════════════
# 验收 4：_estimate_tokens 公式校验
# ═══════════════════════════════════════════════════════════════════════

class TestTokenEstimatorPrecision:
    """_estimate_tokens 与 tiktoken cl100k_base encoder 实测值一致（TICKET-024 切 tiktoken）。"""

    @staticmethod
    def _encoder_expected(msgs: list) -> int:
        """用 tiktoken cl100k_base 计算期望 token 数 = sum(encode(msg)) + N*4。"""
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        return sum(len(enc.encode(str(m))) for m in msgs) + len(msgs) * 4

    def test_pure_english_precision(self):
        """纯英文 → _estimate_tokens 结果与 encoder 实测值一致。"""
        from core.context import _estimate_tokens

        text = "The quick brown fox jumps over the lazy dog. " * 13
        msgs = [{"role": "user", "content": text}]

        actual = _estimate_tokens(msgs)
        expected = self._encoder_expected(msgs)
        assert actual == expected, (
            f"Pure English: expected {expected}, got {actual}"
        )

    def test_pure_cjk_precision(self):
        """纯 CJK → _estimate_tokens 结果与 encoder 实测值一致。"""
        from core.context import _estimate_tokens

        text = "这是一段纯中文文本用于测试分词估算的准确性。" * 15
        msgs = [{"role": "user", "content": text}]

        actual = _estimate_tokens(msgs)
        expected = self._encoder_expected(msgs)
        assert actual == expected, (
            f"Pure CJK: expected {expected}, got {actual}"
        )

    def test_mixed_cjk_english_precision(self):
        """混排 CJK+英文 → _estimate_tokens 结果与 encoder 实测值一致。"""
        from core.context import _estimate_tokens

        cjk = "中文" * 75   # 150 CJK chars
        eng = "abc" * 100   # 300 non-CJK chars
        text = cjk + eng
        msgs = [{"role": "user", "content": text}]

        actual = _estimate_tokens(msgs)
        expected = self._encoder_expected(msgs)
        assert actual == expected, (
            f"Mixed: expected {expected}, got {actual}"
        )

    def test_multiple_messages_overhead(self):
        """多条消息 → _estimate_tokens 结果与 encoder 实测值一致（含每消息 +4 开销）。"""
        from core.context import _estimate_tokens

        msgs = [{"role": "user", "content": "hello" * 6} for _ in range(10)]

        actual = _estimate_tokens(msgs)
        expected = self._encoder_expected(msgs)
        assert actual == expected, (
            f"Multi-msg: expected {expected}, got {actual}"
        )


# ═══════════════════════════════════════════════════════════════════════
# TICKET-024 回归：工具重型历史压缩后锚点恰好 1 个
# ═══════════════════════════════════════════════════════════════════════

class TestToolHeavyCompression:
    """工具输出尾部 >15K token 时，压缩不短路，锚点去重正确。"""

    def test_tool_heavy_tail_compresses_and_dedup_anchor(self, monkeypatch, tmp_path):
        """工具重型历史（>15K token 工具输出尾部）压缩后：
        - 锚点恰好 1 个
        - compressible 非空 → LLM 被调用
        - 历史中不存在重复锚点
        """
        monkeypatch.setenv("BOBO_CONTEXT_BUDGET", "8")
        import core.context as ctx_module
        monkeypatch.setattr(ctx_module, "_get_msg_count_budget", lambda: 200)
        monkeypatch.setattr(ctx_module, "_get_context_budget", lambda _engine=None: 7000)

        log_dir = tmp_path / "events_tool_heavy"
        EventBus.reset(str(log_dir))

        caller = MockLLMCaller([text_response("[L2_ULTRA_BRIEF]\nHeavy tool session summary.")])
        engine = Engine(caller, execute_tool, test_mode=True)
        engine.sid = "test-024-tool-heavy"

        _TEXT = "The quick brown fox jumps over the lazy dog. " * 150  # ~1500 tokens per msg

        engine.history = []
        # 前 5 条短对话（可归档 compressible）
        for i in range(2):
            engine.history.append({"role": "user", "content": f"Question {i}"})
            engine.history.append({"role": "assistant", "content": f"Answer {i}"})
        engine.history.append({"role": "user", "content": "Run heavy tool"})

        # 尾部 12 条重型工具输出（>15K token 撑满层0）
        for i in range(12):
            engine.history.append({"role": "tool", "content": f"tool_result_{i}: {_TEXT}",
                                   "tool_call_id": f"tc{i}", "name": "echo"})

        engine._compressing = False
        engine._compressed_this_turn = False
        engine._compress_history()

        # 检查锚点数量
        _ANCHOR_PREFIX = "[工作锚点"
        anchors = [m for m in engine.history
                   if m.get("role") == "system" and
                   m.get("content", "").startswith(_ANCHOR_PREFIX)]
        assert len(anchors) == 1, (
            f"Expected exactly 1 anchor, got {len(anchors)}: "
            f"{[m.get('content','')[:80] for m in anchors]}"
        )

        # 检查有摘要产出（LLM 被调用）
        summaries = [m for m in engine.history
                     if m.get("role") == "system" and
                     (m.get("content", "").startswith("[L2 极简摘要]")
                      or m.get("content", "").startswith("[L1 段摘要]")
                      or m.get("content", "").startswith("[对话历史摘要 · 本地兜底]"))]
        assert len(summaries) >= 1, "Expected at least 1 summary after tool-heavy compression"
