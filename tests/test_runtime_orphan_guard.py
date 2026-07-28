"""票 H：运行时孤儿防线测试 — Layer 1 发送前清洗 / Layer 2 配对 400 重试。

验证四条铁规：
1. 清洗作用在发送副本，engine.history 本体不许动
2. 清洗必留 WARNING（含 orphan 数和 tool_call_id）
3. 非配对类 400 禁止重试
4. engine.history 本体未被篡改（任何时候）
"""

import logging
from unittest.mock import MagicMock

import pytest


# ── 夹具 ──

def _make_engine(llm_caller, history=None):
    """构造最小 Engine 实例用于测试 _call_llm。

    - callback=None 使 _notify 静默（不抛异常）
    - injector.build_messages 直接返回 self.history（不做注入）
    - llm_caller 由测试方提供
    """
    from core.engine import Engine

    engine = Engine(llm_caller=llm_caller, tool_executor=None, callback=None)
    if history is not None:
        engine.history = list(history)  # 拷贝：后续检查本体不变
    # bypass injector —— 测试用 engine.history 作为 messages
    engine.injector.build_messages = lambda **kwargs: engine.history
    return engine


def _orphan_history():
    """构造运行中带孤儿的 history。

    两条 assistant 发了 tool_calls，其中一条的 tool 结果丢失。
    """
    return [
        {"role": "system", "content": "你是助手"},
        {"role": "user", "content": "搜索一下"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": "tc_good", "function": {"name": "web_search", "arguments": '{"q":"x"}'}, "type": "function"},
                {"id": "tc_orphan", "function": {"name": "read_file", "arguments": '{"path":"/x"}'}, "type": "function"},
            ],
        },
        # tool 结果只回了 tc_good，tc_orphan 丢失
        {"role": "tool", "tool_call_id": "tc_good", "content": "搜索结果"},
        # 下一条 assistant 继续对话
        {"role": "assistant", "content": "好的找到了"},
        {"role": "user", "content": "再分析一下"},
    ]


# ── Layer 1：发送前清洗 ──


class TestLayer1SendClean:
    """Layer 1：engine._call_llm() 发送前对 messages 副本做 clean_orphan_tool_calls。"""

    def test_llm_receives_cleaned_messages(self):
        """含孤儿 history → mock caller 断言收到已配对的 messages。"""
        mock_caller = MagicMock(return_value={
            "choices": [{"message": {"content": "分析结果"}}],
            "usage": {},
        })

        engine = _make_engine(mock_caller, _orphan_history())
        engine._call_llm()

        # mock_caller 被调用至少一次
        assert mock_caller.called
        sent_messages = mock_caller.call_args[0][0]

        # 确认清洗效果：孤儿 assistant 的 tc_orphan 后面被补了占位 tool 消息
        tool_call_ids_in_sent = []
        for m in sent_messages:
            if isinstance(m, dict) and m.get("role") == "tool":
                tool_call_ids_in_sent.append(m.get("tool_call_id", ""))

        assert "tc_orphan" in tool_call_ids_in_sent, (
            "孤儿 tool_call_id 应在发送副本中获得占位 tool 消息"
        )

    def test_engine_history_not_mutated_by_layer1(self):
        """engine.history 本体在 Layer 1 清洗后保持不变。"""
        original = _orphan_history()
        engine = _make_engine(
            MagicMock(return_value={"choices": [{"message": {"content": "ok"}}], "usage": {}}),
            original,
        )
        engine._call_llm()

        # history 本体不应有任何变化
        assert engine.history == original, "engine.history 本体被篡改！清洗必须作用在发送副本上"

    def test_layer1_warning_logged(self, caplog):
        """清洗时产生 WARNING 日志，含 orphan 数和 tool_call_id。"""
        mock_caller = MagicMock(return_value={
            "choices": [{"message": {"content": "ok"}}],
            "usage": {},
        })

        engine = _make_engine(mock_caller, _orphan_history())
        with caplog.at_level(logging.WARNING):
            engine._call_llm()

        warnings = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
        assert any("运行时孤儿" in msg for msg in warnings), (
            f"应有一条 WARNING 标记运行时孤儿清洗，实际: {warnings}"
        )
        assert any("tc_orphan" in msg for msg in warnings), (
            f"WARNING 应包含 orphan tool_call_id 'tc_orphan'，实际: {warnings}"
        )


# ── Layer 2：配对 400 重试 ──


class TestLayer2400Retry:
    """Layer 2：捕获配对类 HTTP 400，清洗后重试一次。"""

    def test_pairing_400_retry_succeeds(self, caplog):
        """第一次返回配对 400 → 清洗重试 → 第二次成功 → 返回内容。"""
        call_count = [0]

        def caller(messages, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # 配对 400（DeepSeek 实际错误文本）
                return {
                    "error": "messages with role 'tool' must be a response to a preceding message",
                    "error_type": "bad_request",
                    "retryable": False,
                    "detail": '{"error":{"message":"tool message must be preceded by a user or assistant message"}}',
                }
            else:
                return {
                    "choices": [{"message": {"content": "重试后正常回复"}}],
                    "usage": {},
                }

        engine = _make_engine(caller, _orphan_history())
        with caplog.at_level(logging.WARNING):
            content, tool_calls = engine._call_llm()

        assert call_count[0] == 2, f"预期调用 2 次（400 + 清洗重试），实际 {call_count[0]}"
        assert content == "重试后正常回复"
        assert tool_calls == []

        # WARNING 日志验证
        warnings = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
        assert any("清洗后重试成功" in msg for msg in warnings), f"应有重试成功 WARNING，实际: {warnings}"

    def test_pairing_400_retry_fails(self):
        """两次都返回配对 400 → 最终返回错误信息。"""
        def caller(messages, **kwargs):
            return {
                "error": "tool_call_id mismatch",
                "error_type": "bad_request",
                "retryable": False,
                "detail": "messages with role 'tool' must be a response...",
            }

        engine = _make_engine(caller, _orphan_history())
        content, tool_calls = engine._call_llm()

        assert "错误:" in content
        assert tool_calls == []

    def test_non_pairing_400_not_retried(self):
        """非配对类 400（如参数错误）不触发清洗重试。"""
        call_count = [0]

        def caller(messages, **kwargs):
            call_count[0] += 1
            return {
                "error": "Invalid request: model does not support parameter 'temperature'",
                "error_type": "bad_request",
                "retryable": False,
                "detail": "Invalid parameter",
            }

        engine = _make_engine(caller, _orphan_history())
        content, tool_calls = engine._call_llm()

        assert call_count[0] == 1, f"非配对 400 不应重试，实际调用 {call_count[0]} 次"
        assert "错误:" in content

    def test_non_400_error_not_retried(self):
        """非 400 错误（如 500）不触发清洗重试。"""
        call_count = [0]

        def caller(messages, **kwargs):
            call_count[0] += 1
            return {
                "error": "Internal Server Error",
                "error_type": "server_error",
                "retryable": True,  # llm_caller 层已重试过
                "detail": "",
            }

        engine = _make_engine(caller, _orphan_history())
        content, _ = engine._call_llm()

        assert call_count[0] == 1, f"非 400 错误不应触发清洗重试"


# ── _is_tool_pairing_400 单元测试 ──


class TestIsToolPairing400:
    """_is_tool_pairing_400 纯函数——配对关键词判定。"""

    def test_deepseek_pairing_error(self):
        from core.engine import _is_tool_pairing_400
        resp = {
            "error": "messages with role 'tool' must be a response to a preceding message",
            "error_type": "bad_request",
            "detail": "",
        }
        assert _is_tool_pairing_400(resp) is True

    def test_openai_pairing_error(self):
        from core.engine import _is_tool_pairing_400
        resp = {
            "error": "requires a corresponding tool call",
            "error_type": "bad_request",
            "detail": "",
        }
        assert _is_tool_pairing_400(resp) is True

    def test_tool_call_id_in_detail(self):
        from core.engine import _is_tool_pairing_400
        resp = {
            "error": "Bad Request",
            "error_type": "bad_request",
            "detail": "validation failed: tool_call_id mismatch",
        }
        assert _is_tool_pairing_400(resp) is True

    def test_non_bad_request_not_match(self):
        from core.engine import _is_tool_pairing_400
        resp = {
            "error": "tool_call_id something",
            "error_type": "server_error",
            "detail": "",
        }
        assert _is_tool_pairing_400(resp) is False

    def test_bad_request_not_pairing(self):
        from core.engine import _is_tool_pairing_400
        resp = {
            "error": "Invalid model parameter",
            "error_type": "bad_request",
            "detail": "parameter 'top_p' not supported",
        }
        assert _is_tool_pairing_400(resp) is False

    def test_unknown_error_type(self):
        from core.engine import _is_tool_pairing_400
        resp = {
            "error": "some tool_call_id error",
            "error_type": "unknown",
            "detail": "",
        }
        assert _is_tool_pairing_400(resp) is False


# ── history 完整性跨所有场景 ──


class TestHistoryIntegrity:
    """engine.history 本体无论 Layer 1/2 都不被篡改。"""

    def test_history_untouched_after_layer2_retry(self):
        """Layer 2 清洗重试后，history 本体仍不变。"""
        call_count = [0]
        original = _orphan_history()

        def caller(messages, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return {
                    "error": "messages with role 'tool' must be a response",
                    "error_type": "bad_request",
                    "retryable": False,
                    "detail": "tool message must be preceded by",
                }
            return {"choices": [{"message": {"content": "ok"}}], "usage": {}}

        engine = _make_engine(caller, original)
        engine._call_llm()

        assert engine.history == original, "Layer 2 清洗后 history 本体不应被篡改"
