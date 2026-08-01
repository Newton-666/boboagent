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

        构造：
          msg  0-30: 极短（可归档段，token 占比 ≈2%）
          msg 31-60: 极长（保留段），最后一条 user 在第 58 位
          → archivable_ratio < 15%，触发 compress_skipped
        """
        monkeypatch.setenv("BOBO_CONTEXT_BUDGET", "60")

        # 事件总线指向 temp dir
        log_dir = tmp_path / "events"
        EventBus.reset(str(log_dir))

        caller = MockLLMCaller([text_response("x")])
        engine = Engine(caller, execute_tool, test_mode=True)
        engine.sid = "test-023-skip"

        # 构造 61 条消息
        # msg 0-30（31 条极短 = 可归档段）：15 对 user/assistant + 1 user
        # msg 31-54（24 条极长）：12 对 user/assistant
        # msg 55-60（6 条短尾）：末 3 条含 user（user 在 msg 58）
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

        构造：可归档段放大量长内容，保留段放短内容 → archivable_ratio ≈ 80%
        """
        monkeypatch.setenv("BOBO_CONTEXT_BUDGET", "60")

        log_dir = tmp_path / "events2"
        EventBus.reset(str(log_dir))

        # LLM 返回非空摘要
        caller = MockLLMCaller([text_response("This is a compressed summary of the conversation.")])
        engine = Engine(caller, execute_tool, test_mode=True)
        engine.sid = "test-023-normal"

        engine.history = []
        # 前 31 条（可归档）：长内容
        for i in range(15):
            engine.history.append({"role": "user", "content": f"Question {i}: " + "x" * 300})
            engine.history.append({"role": "assistant", "content": f"Answer {i}: " + "y" * 300})
        engine.history.append({"role": "user", "content": "x" * 300})  # msg 30

        # 后 30 条（保留段）：短内容
        for i in range(15):
            engine.history.append({"role": "user", "content": f"q{i}"})
            engine.history.append({"role": "assistant", "content": f"a{i}"})

        assert len(engine.history) == 61

        engine._compressing = False
        engine._compressed_this_turn = False
        engine._compress_history()

        # 应该产生压缩摘要
        summaries = [m for m in engine.history
                     if m.get("role") == "system"
                     and m.get("content", "").startswith("[对话历史摘要]")]
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
        """mock LLM 返回空 → history 出现本地兜底 + summary_source=local_fallback。"""
        monkeypatch.setenv("BOBO_CONTEXT_BUDGET", "60")

        log_dir = tmp_path / "events3"
        EventBus.reset(str(log_dir))

        # LLM 返回空 content
        caller = MockLLMCaller([{"choices": [{"message": {"content": ""}}]}])
        engine = Engine(caller, execute_tool, test_mode=True)
        engine.sid = "test-023-fallback"

        engine.history = []
        # 前 31 条（可归档，内容要足够大确保 ≥30% 占比；避免 tool_calls 触发孤儿保护）
        engine.history.append({"role": "user", "content": "帮我查一下今天的天气如何？" + "x" * 300})
        engine.history.append({"role": "assistant", "content": "让我帮你查询天气。" + "y" * 300})
        # tool 对（tool_calls + tool_result）放在可归档段但注意孤儿保护：
        # 孤儿保护只检查 kept 段是否有 result，两个都在 archivable 段时会误判。
        # 所以去掉 tool_calls，只保留纯文本对话。
        for i in range(14):
            engine.history.append({"role": "user", "content": f"问题 {i} " + "p" * 200})
            engine.history.append({"role": "assistant", "content": f"回答 {i} " + "q" * 200})
        engine.history.append({"role": "user", "content": "最后一个可归档问题" + "r" * 200})  # +1 → 31 条可归档

        # 后 30 条（保留段）：短内容，确保可归档段占大头
        for i in range(15):
            engine.history.append({"role": "user", "content": f"新问题 {i}"})
            engine.history.append({"role": "assistant", "content": f"新回答 {i}"})

        assert len(engine.history) == 61

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
        assert "帮我查一下" in content, "Should contain original user messages"

        # 验证事件 summary_source=local_fallback
        events_path = log_dir / "events.jsonl"
        raw = [json.loads(line) for line in events_path.read_text(encoding="utf-8").strip().splitlines()]
        compressed = [e for e in raw if e.get("type") == "context.compressed"]
        assert len(compressed) >= 1
        assert compressed[0].get("summary_source") == "local_fallback", (
            f"Expected summary_source=local_fallback, got {compressed[0].get('summary_source')}"
        )

    def test_no_user_text_produces_local_fallback(self, monkeypatch, tmp_path):
        """纯工具记录段（无 user/assistant 文本）→ 仍生成本地兜底而非丢弃。"""
        monkeypatch.setenv("BOBO_CONTEXT_BUDGET", "20")  # 小预算触发

        log_dir = tmp_path / "events3b"
        EventBus.reset(str(log_dir))

        caller = MockLLMCaller([{"choices": [{"message": {"content": ""}}]}])
        engine = Engine(caller, execute_tool, test_mode=True)
        engine.sid = "test-023-nouser"

        # 构造纯工具历史（前一半 tool 消息含大量文本，后一半短 user+assistant）
        engine.history = []
        for i in range(10):
            engine.history.append({"role": "tool", "content": f"result {i}: " + "d" * 200,
                                   "tool_call_id": f"tc{i}", "name": "echo"})
        for i in range(11):
            engine.history.append({"role": "user", "content": f"msg {i}"})
            engine.history.append({"role": "assistant", "content": f"reply {i}"})

        assert len(engine.history) == 10 + 22  # 32

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
    """_estimate_tokens 与公式期望误差 < 10%。"""

    def test_pure_english_precision(self):
        """纯英文 ~585 字符 → str(msg) 总 618 非 CJK → int(0 + 618/3) + 4 = 210。"""
        from core.context import _estimate_tokens

        text = "The quick brown fox jumps over the lazy dog. " * 13  # ~585 chars
        msgs = [{"role": "user", "content": text}]

        actual = _estimate_tokens(msgs)
        # str(msg) 含约 33 字符结构开销，总非 CJK ≈ 618，int(618/3) + 4 = 206 + 4 ≈ 210
        expected = 210
        assert abs(actual - expected) < 21, (
            f"Pure English: expected ~{expected}, got {actual}"
        )

    def test_pure_cjk_precision(self):
        """纯 CJK 330 字符 → str(msg) 含 315 CJK + 48 非CJK → int(315/1.2 + 48/3)+4 = int(262.5+16)+4 = 282。"""
        from core.context import _estimate_tokens

        text = "这是一段纯中文文本用于测试分词估算的准确性。" * 15  # 330 chars
        msgs = [{"role": "user", "content": text}]

        actual = _estimate_tokens(msgs)
        # CJK=315, non-CJK=48 → int(315/1.2 + 48/3) + 4 = int(262.5 + 16) + 4 = 282
        expected = 282
        assert abs(actual - expected) < 29, (
            f"Pure CJK: expected ~{expected}, got {actual}"
        )

    def test_mixed_cjk_english_precision(self):
        """混排：150 CJK + 33 结构（含 150CJK）→ CJK=150, non-CJK=333 → int(150/1.2+333/3)+4 = 240。"""
        from core.context import _estimate_tokens

        cjk = "中文" * 75   # 150 CJK chars
        eng = "abc" * 100   # 300 non-CJK chars
        text = cjk + eng    # 450 chars total
        msgs = [{"role": "user", "content": text}]

        actual = _estimate_tokens(msgs)
        # str 开销 33 非 CJK，内容 150 CJK + 300 非 CJK → total chars: 150 CJK + 333 non-CJK
        # int(150/1.2) = 125, int(333/3) = 111, +4 = 240
        expected = 240
        assert abs(actual - expected) < 24, (
            f"Mixed: expected ~{expected}, got {actual}"
        )

    def test_multiple_messages_overhead(self):
        """10 条消息：每条 str(msg) ~61 非 CJK → 610 总非 CJK → int(610/3) + 40 = 203+40 = 243。"""
        from core.context import _estimate_tokens

        msgs = [{"role": "user", "content": "hello" * 6} for _ in range(10)]
        # 每条 str(msg) = "{'role': 'user', 'content': 'hello...'}" ≈ 61 非 CJK chars
        actual = _estimate_tokens(msgs)
        expected = 243   # int(610/3) + 10*4 = 203 + 40
        assert abs(actual - expected) < 25, (
            f"Multi-msg: expected ~{expected}, got {actual}"
        )
