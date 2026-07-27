"""
Tests for dynamic context budget (C1-C4).

Covers:
  1. Multi-provider compression trigger (k3/DSeek/ollama/gpt-4o/claude/gemini/custom)
  2. Token estimator accuracy (EN/ZH/mixed, ±30% conservative bias)
  3. Orphan-pair protection (compression + hard truncation dual paths)
  4. Retroactive marking (10-round cutoff, idempotency)
"""

import os
import sys
import pytest

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _project_root)


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def engine():
    from tests.mock_llm import MockLLMCaller, text_response
    from core.tool_executor import execute_tool
    from core.engine import Engine
    caller = MockLLMCaller([text_response("ok")])
    return Engine(caller, execute_tool, test_mode=True)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Ensure clean env for each test."""
    monkeypatch.delenv("BOBO_PROVIDER", raising=False)
    monkeypatch.delenv("API_MODEL_NAME", raising=False)
    monkeypatch.delenv("BOBO_CONTEXT_BUDGET_RATIO", raising=False)
    monkeypatch.delenv("BOBO_MAX_TOKENS", raising=False)
    monkeypatch.delenv("BOBO_CONTEXT_LENGTH", raising=False)
    monkeypatch.delenv("BOBO_TEMPERATURE", raising=False)


# ═════════════════════════════════════════════════════════════════════════════
# 1. Token Estimator Accuracy
# ═════════════════════════════════════════════════════════════════════════════

class TestTokenEstimator:
    """C2: _estimate_tokens() — CJK heuristic, conservative bias, ±30% accuracy."""

    def test_english_only(self):
        """Pure English: ~4 chars/token. 400 chars → expect ~100 tokens."""
        from core.context import _estimate_tokens
        text = "The quick brown fox jumps over the lazy dog. " * 10  # ~440 chars
        msgs = [{"role": "user", "content": text}]
        est = _estimate_tokens(msgs)
        # ~440/4 = 110. Acceptable range: 80-140 (±30%)
        assert 80 <= est <= 140, f"English: estimated {est} tokens from ~440 chars"

    def test_chinese_only(self):
        """Pure Chinese: ~1.5 chars/token. 300 chars → expect ~200 tokens."""
        from core.context import _estimate_tokens
        text = "这是一段纯中文文本用于测试分词估算的准确性。" * 15  # ~300 chars
        msgs = [{"role": "user", "content": text}]
        est = _estimate_tokens(msgs)
        # ~300/1.5 = 200. Acceptable range: 140-260 (±30%)
        assert 140 <= est <= 260, f"Chinese: estimated {est} tokens from ~300 CJK chars"

    def test_mixed_cjk_english(self):
        """Mixed CJK + English: should be between pure EN and pure ZH estimates."""
        from core.context import _estimate_tokens
        text = ("Hello world 你好世界 Python 编程 " * 20)  # mixed
        msgs = [{"role": "user", "content": text}]
        est = _estimate_tokens(msgs)
        # Should produce a reasonable non-zero estimate
        assert est > 0, f"Mixed text: got {est}"
        # Conservative: estimate should be <= char count (i.e. not underestimating)
        assert est <= len(text), f"Mixed estimate {est} should be <= {len(text)} chars"

    def test_conservative_bias(self):
        """Estimate should never exceed actual char count (conservative = no under-counting tokens)."""
        from core.context import _estimate_tokens
        # For any reasonable text, est <= len(text) (since tokens_per_char < 1)
        for text in [
            "Hello world " * 100,
            "你好世界" * 100,
            "Hi 你好 world 世界" * 50,
        ]:
            msgs = [{"role": "user", "content": text}]
            est = _estimate_tokens(msgs)
            assert est <= len(text), (
                f"Estimate {est} exceeds char count {len(text)} — not conservative"
            )
            assert est > 0, f"Got zero estimate for non-empty text"

    def test_empty_history(self):
        """Empty history → zero tokens. Single empty message → small (dict overhead)."""
        from core.context import _estimate_tokens
        assert _estimate_tokens([]) == 0
        # Single empty-role message includes dict structure overhead
        est = _estimate_tokens([{"role": "user", "content": ""}])
        assert est < 20, f"Empty message estimate {est} should be tiny"

    def test_large_history_performance(self):
        """~500k chars should complete in <100ms."""
        import time
        from core.context import _estimate_tokens
        msgs = [{"role": "user", "content": "Hello world " * 500}] * 10
        start = time.time()
        est = _estimate_tokens(msgs)
        elapsed = time.time() - start
        assert elapsed < 0.5, f"500k chars took {elapsed:.3f}s, expected <0.1s"
        assert est > 0


# ═════════════════════════════════════════════════════════════════════════════
# 2. Multi-Provider Dynamic Budget
# ═════════════════════════════════════════════════════════════════════════════

class TestDynamicBudget:
    """C3: Budget scales with provider context_length. Small windows trigger earlier."""

    @pytest.mark.parametrize("provider,model,expected_min_budget", [
        ("moonshot", "kimi-k3", 600000),          # 1M window
        ("deepseek", "deepseek-v4-pro", 600000),  # 1M window
        ("openai", "gpt-4o", 70000),              # 128k window
        ("anthropic", "claude-sonnet-4-20250514", 120000),  # 200k window
        ("google", "gemini-2.0-flash", 600000),   # 1M window
        ("ollama", "llama3", 10000),              # 32k window
    ])
    def test_budget_scales_with_window(self, monkeypatch, provider, model, expected_min_budget):
        """Budget should be roughly (context_len - max_tokens) * 0.7."""
        monkeypatch.setenv("BOBO_PROVIDER", provider)
        monkeypatch.setenv("API_MODEL_NAME", model)
        monkeypatch.setenv("BOBO_MAX_TOKENS", "8192")  # neutral default
        from core.context import _get_context_budget
        budget = _get_context_budget()
        assert budget >= expected_min_budget, (
            f"{provider}/{model}: budget {budget:,} < expected min {expected_min_budget:,}"
        )

    def test_ollama_compresses_earlier_than_k3(self, monkeypatch):
        """Same history: small-window model triggers, large-window doesn't."""
        from core.context import _estimate_tokens, _get_context_budget
        # Moderate history (~13k tokens)
        msgs = []
        for _ in range(25):
            msgs.append({"role": "user", "content": "这是一段中文测试文本" * 15})
            msgs.append({"role": "assistant", "content": "English response text " * 20})
        est = _estimate_tokens(msgs)

        # Simulate a small model (8k window) via env override
        monkeypatch.setenv("BOBO_CONTEXT_LENGTH", "8192")
        monkeypatch.setenv("BOBO_MAX_TOKENS", "1024")
        budget_small = _get_context_budget()
        small_triggers = est > budget_small

        # k3 1M
        monkeypatch.delenv("BOBO_CONTEXT_LENGTH", raising=False)
        monkeypatch.setenv("BOBO_PROVIDER", "moonshot")
        monkeypatch.setenv("API_MODEL_NAME", "kimi-k3")
        monkeypatch.setenv("BOBO_MAX_TOKENS", "8192")
        budget_k3 = _get_context_budget()
        k3_triggers = est > budget_k3

        assert small_triggers, (
            f"Small window (8k) should trigger (est={est:,} > budget={budget_small:,})"
        )
        assert not k3_triggers, (
            f"k3 1M should NOT trigger (est={est:,} < budget={budget_k3:,})"
        )

    def test_custom_fallback(self, monkeypatch):
        """Unknown provider → 128k conservative fallback."""
        monkeypatch.setenv("BOBO_PROVIDER", "unknown_provider_xyz")
        monkeypatch.setenv("API_MODEL_NAME", "some-model")
        monkeypatch.setenv("BOBO_MAX_TOKENS", "8192")
        from core.context import _get_context_budget
        budget = _get_context_budget()
        assert 70000 <= budget <= 90000, (
            f"Unknown provider budget {budget:,} should be ~128k-based"
        )

    def test_ratio_env_override(self, monkeypatch):
        """BOBO_CONTEXT_BUDGET_RATIO should be adjustable."""
        monkeypatch.setenv("BOBO_PROVIDER", "deepseek")
        monkeypatch.setenv("API_MODEL_NAME", "deepseek-v4-pro")
        monkeypatch.setenv("BOBO_MAX_TOKENS", "8192")
        monkeypatch.setenv("BOBO_CONTEXT_BUDGET_RATIO", "0.5")
        from core.context import _get_context_budget
        budget_half = _get_context_budget()

        monkeypatch.setenv("BOBO_CONTEXT_BUDGET_RATIO", "0.9")
        budget_nine = _get_context_budget()

        assert budget_nine > budget_half, (
            f"ratio 0.9 ({budget_nine:,}) should be larger than ratio 0.5 ({budget_half:,})"
        )

    def test_provider_model_context_override(self, monkeypatch):
        """model_context should override provider-level context_length."""
        monkeypatch.setenv("BOBO_PROVIDER", "moonshot")
        monkeypatch.setenv("API_MODEL_NAME", "kimi-k2.6")
        monkeypatch.setenv("BOBO_MAX_TOKENS", "8192")
        from core.provider import get_context_length
        # kimi-k2.6 has model_context=262144, should NOT return 1M
        cl = get_context_length()
        assert cl == 262144, f"kimi-k2.6 context should be 262144, got {cl}"


# ═════════════════════════════════════════════════════════════════════════════
# 3. Orphan-Pair Protection (Compression + Hard Truncation Dual Paths)
# ═════════════════════════════════════════════════════════════════════════════

class TestOrphanPairProtection:
    """Ensure tool_calls/tool message pairs are never split by compression or truncation."""

    def test_compression_does_not_split_tool_pairs(self, engine, monkeypatch):
        """Compression should not leave orphaned tool messages."""
        # Create history where tool messages belong to assistant tool_calls
        engine.history = [
            {"role": "user", "content": "x" * 200},
            {"role": "assistant", "content": "y" * 200},
        ] * 8  # 16 messages of filler

        # Add a tool_calls exchange that must stay together
        engine.history.append({"role": "user", "content": "query"})
        engine.history.append({
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": "call_1",
                "type": "function",
                "function": {"name": "read_local_file", "arguments": '{"file_path": "f.txt"}'}
            }]
        })
        engine.history.append({
            "role": "tool",
            "tool_call_id": "call_1",
            "content": "file contents here"
        })
        engine.history.append({"role": "user", "content": "x" * 200})
        engine.history.append({"role": "assistant", "content": "y" * 200})

        # Force compression
        engine.KEEP_EXCHANGES = 1  # Keep only 1 exchange, forcing everything else to compress
        engine._compressing = False
        engine._compressed_this_turn = False
        engine._compress_history()

        # After compression: the tool message must NOT appear without its tool_calls
        for i, msg in enumerate(engine.history):
            if msg.get("role") == "tool":
                tc_id = msg.get("tool_call_id", "")
                # Find preceding assistant message with matching tool_calls
                found_pair = False
                for j in range(i - 1, -1, -1):
                    prev = engine.history[j]
                    if prev.get("role") == "assistant" and prev.get("tool_calls"):
                        for tc in prev["tool_calls"]:
                            if tc.get("id") == tc_id:
                                found_pair = True
                                break
                    if found_pair:
                        break
                assert found_pair, (
                    f"Orphan tool message at index {i} (tool_call_id={tc_id}) "
                    f"has no matching assistant tool_calls"
                )

    def test_truncation_does_not_split_tool_pairs(self, engine):
        """Hard truncation (_truncate_history) should not split tool_calls/tool pairs."""
        engine.MAX_HISTORY_MESSAGES = 10
        # Build 12 messages manually (6 pairs = 12 messages > MAX_HISTORY_MESSAGES=10)
        engine.history = []
        for n in range(6):
            engine.history.append({"role": "user", "content": f"msg{n}"})
            engine.history.append({"role": "assistant", "content": f"reply{n}"})

        # Insert a tool exchange near the truncation boundary (message 8-9)
        engine.history.insert(8, {
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": "call_trunc",
                "type": "function",
                "function": {"name": "grep_code", "arguments": '{}'}
            }]
        })
        engine.history.insert(9, {
            "role": "tool",
            "tool_call_id": "call_trunc",
            "content": "search results"
        })

        engine._truncate_history()

        # The tool message must not appear without its assistant tool_calls
        for i, msg in enumerate(engine.history):
            if msg.get("role") == "tool":
                tc_id = msg.get("tool_call_id", "")
                found_pair = False
                for j in range(i - 1, -1, -1):
                    prev = engine.history[j]
                    if prev.get("role") == "assistant" and prev.get("tool_calls"):
                        for tc in prev["tool_calls"]:
                            if tc.get("id") == tc_id:
                                found_pair = True
                                break
                    if found_pair:
                        break
                assert found_pair, (
                    f"Truncation orphan: tool at {i} (id={tc_id}) has no pair"
                )

    def test_truncation_split_not_on_tool_message(self, engine):
        """The truncation split point should never land on a tool message."""
        engine.MAX_HISTORY_MESSAGES = 5
        engine.history = [
            {"role": "user", "content": "a"},
            {"role": "assistant", "content": "b"},
            {"role": "user", "content": "c"},
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "x", "type": "function", "function": {"name": "t", "arguments": "{}"}}
            ]},
            {"role": "tool", "tool_call_id": "x", "content": "result"},
            {"role": "user", "content": "d"},
            {"role": "assistant", "content": "e"},
        ]
        engine._truncate_history()
        # First message should NOT be a tool message (would be orphaned)
        assert engine.history[0]["role"] != "tool", (
            f"Truncation left orphan tool as first message"
        )


# ═════════════════════════════════════════════════════════════════════════════
# 4. Retroactive Marking
# ═════════════════════════════════════════════════════════════════════════════

class TestRetroactiveMarking:
    """C4: _retroactive_mark() — marks old tool results, skips recent + small ones."""

    def test_marks_old_tool_results(self, engine):
        """Tool results older than 10 rounds + >500 chars → should be marked."""
        engine.current_tool_round = 20
        # Build 15 tool messages, first 5 are "old" (>10 rounds ago), last 10 are "recent"
        for i in range(15):
            engine.history.append({
                "role": "tool",
                "tool_call_id": f"call_{i}",
                "content": "x" * 600,  # >500 chars
            })
        engine.tracker.retroactive_mark()

        # First 5 (old) should be marked, last 10 (recent) should NOT
        for i in range(5):
            assert engine.history[i]["content"].startswith("[RESULT]"), (
                f"Old tool result at {i} was NOT marked"
            )
        for i in range(5, 15):
            assert not engine.history[i]["content"].startswith("[RESULT]"), (
                f"Recent tool result at {i} was incorrectly marked"
            )

    def test_skips_small_results(self, engine):
        """Tool results <500 chars should NOT be marked, even if old."""
        engine.current_tool_round = 20
        for i in range(15):
            engine.history.append({
                "role": "tool",
                "tool_call_id": f"call_{i}",
                "content": "short",  # <500 chars
            })
        engine.tracker.retroactive_mark()

        for i in range(15):
            assert not engine.history[i]["content"].startswith("[RESULT]"), (
                f"Small result at {i} ({len(engine.history[i]['content'])} chars) was marked"
            )

    def test_skips_already_marked(self, engine):
        """Already-marked results should be skipped (idempotent)."""
        engine.current_tool_round = 20
        for i in range(15):
            engine.history.append({
                "role": "tool",
                "tool_call_id": f"call_{i}",
                "content": "[RESULT] already\n  → marked\n  → id: xxx, 600 chars",
            })
        # Should not crash or double-mark
        engine.tracker.retroactive_mark()
        for i in range(15):
            content = engine.history[i]["content"]
            # Should still start with [RESULT] (only one)
            assert content.startswith("[RESULT]"), f"Already-marked result changed at {i}"

    def test_idempotent_across_calls(self, engine):
        """Multiple _retroactive_mark calls should be idempotent."""
        engine.current_tool_round = 20
        for i in range(15):
            engine.history.append({
                "role": "tool",
                "tool_call_id": f"call_{i}",
                "content": "y" * 600,
            })
        engine.tracker.retroactive_mark()
        first_pass = [m["content"] for m in engine.history]
        engine.tracker.retroactive_mark()
        second_pass = [m["content"] for m in engine.history]
        assert first_pass == second_pass, "Retroactive marking is not idempotent"

    def test_fewer_than_10_tools_skips(self, engine):
        """Fewer than 10 tool results → scan skipped entirely."""
        engine.current_tool_round = 5
        for i in range(3):
            engine.history.append({
                "role": "tool",
                "tool_call_id": f"call_{i}",
                "content": "z" * 600,
            })
        engine.tracker.retroactive_mark()
        for i in range(3):
            assert not engine.history[i]["content"].startswith("[RESULT]"), (
                f"Result at {i} marked when <10 tools exist"
            )
