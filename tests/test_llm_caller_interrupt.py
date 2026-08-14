"""票 INT-1：流式可中断专项测试。

覆盖两个核心场景（对应票 INT-1 验收口径）：
  1. 流式中置位中断 → 断流退场：
     a. call_llm 入口前检查——中断已置位直接抛 LLMInterrupted，不发请求；
     b. 流式每 chunk 检查——收到首个内容块后置位，下一 chunk 断流抛 LLMInterrupted，
        绝不重试（retry_callback 不被调用）、response 被 close；
     c. 完全静默期（模型思考中零 chunk）——_read_stream_lines 的 q.get 空转
        检查中断标志，≤1s 断流抛 LLMInterrupted。
  2. 中断后会话可继续——中断事件清除后，同一 caller 再次调用正常出结果
     （中断状态不残留）。
"""

import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from core.llm_caller import (
    LLMInterrupted,
    _read_stream_lines,
    create_llm_caller,
)


class _BlockingRaw:
    """流式 mock 响应体：前 n 次 read1 返回给定字节，之后阻塞直到 release。

    模拟真实 socket 阻塞读——_read_stream_lines 的读者线程会卡在 read1 上，
    主循环 q.get(timeout=1.0) 空转，从而可测静默期/置位中断路径。
    """

    decode_content = True

    def __init__(self, chunks, release):
        self._chunks = list(chunks)
        self._release = release

    def read1(self, n):
        if self._chunks:
            return self._chunks.pop(0)
        self._release.wait()
        return b""


def _make_stream_response(first_chunk: bytes, release: threading.Event):
    """构造 status_code=200 的流式 mock response（raw 走 _BlockingRaw）。"""
    resp = MagicMock()
    resp.status_code = 200
    resp.raw = _BlockingRaw([first_chunk], release)
    return resp


# ── 场景 1a：入口前检查（中断已置位 → 直接抛，不发请求）──────────


class TestEntryCheckBeforeNetwork:
    """票 INT-1：call_llm 入口前检查中断标志。"""

    def test_interrupt_set_raises_before_request(self):
        interrupt = threading.Event()
        interrupt.set()
        caller = create_llm_caller("k", "http://api.test", "m", tools_schema=[])

        with patch("core.llm_caller._post_with_headers_watchdog") as mock_post:
            with pytest.raises(LLMInterrupted):
                caller([{"role": "user", "content": "hi"}],
                       _interrupt_event=interrupt)
            # 中断已置位 → 不发起任何网络请求
            mock_post.assert_not_called()

    def test_none_event_no_interrupt(self):
        """对照组：_interrupt_event=None（正常模式）不抛中断。"""
        caller = create_llm_caller("k", "http://api.test", "m", tools_schema=[])
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "choices": [{"message": {"role": "assistant", "content": "ok"}}]
        }
        with patch("core.llm_caller._post_with_headers_watchdog",
                   return_value=resp) as mock_post:
            result = caller([{"role": "user", "content": "hi"}])
            assert result["choices"][0]["message"]["content"] == "ok"
            mock_post.assert_called_once()


# ── 场景 1b：流式中置位中断 → 断流退场，绝不重试 ────────────────


class TestStreamInterruptMidstream:
    """票 INT-1：流式读取中置位中断 → 断流抛 LLMInterrupted。"""

    def test_interrupt_after_first_chunk_raises_no_retry(self):
        interrupt = threading.Event()
        release = threading.Event()
        first = b'data: {"choices":[{"delta":{"content":"hi"}}]}\n\n'
        resp = _make_stream_response(first, release)

        received = []
        retried = []

        def on_chunk(text):
            received.append(text)
            # 收到首个内容块后置位中断 → 下一 chunk 检查即断流
            interrupt.set()

        caller = create_llm_caller("k", "http://api.test", "m", tools_schema=[])
        with patch("core.llm_caller._post_with_headers_watchdog",
                   return_value=resp):
            with pytest.raises(LLMInterrupted):
                caller([{"role": "user", "content": "hi"}],
                       stream_callback=on_chunk,
                       retry_callback=lambda *a: retried.append(a),
                       _interrupt_event=interrupt)

        release.set()  # 释放读者线程，测试干净退出

        # 流式确实在走（收到过内容块）
        assert received == ["hi"]
        # 用户中断绝不重试（与网络断流本质不同）
        assert retried == []
        # 断流退场：response 被强制关闭
        resp.close.assert_called()


# ── 场景 1c：完全静默期中断（模型思考中零 chunk）────────────────


class TestReadStreamLinesSilentInterrupt:
    """票 INT-1：_read_stream_lines 静默期 q.get 空转检查中断标志。"""

    def test_silent_period_interrupt_raises_and_closes(self):
        interrupt = threading.Event()
        release = threading.Event()
        resp = MagicMock()
        resp.raw = _BlockingRaw([], release)  # 读者线程立即阻塞 → 全程无数据

        vitals = {"last_chunk": time.time()}
        interrupt.set()

        with pytest.raises(LLMInterrupted):
            list(_read_stream_lines(resp, 120, vitals,
                                    _interrupt_event=interrupt))

        release.set()  # 释放读者线程
        # 断流退场：强制关闭连接
        resp.close.assert_called()

    def test_silent_period_without_interrupt_yields_normally(self):
        """对照组：中断未置位 → 数据行正常产出（静默期检查不误伤）。"""
        interrupt = threading.Event()
        release = threading.Event()
        resp = MagicMock()
        resp.raw = _BlockingRaw([b"data: hello\n\n", b"data: world\n\n"],
                                release)

        vitals = {"last_chunk": time.time()}
        lines = []
        for line in _read_stream_lines(resp, 120, vitals,
                                       _interrupt_event=interrupt):
            lines.append(line)
            # 两行数据 + 各自空行分隔 = 4 个 yield，收集满即退出
            if len(lines) >= 4:
                break
        release.set()
        assert b"data: hello" in lines and b"data: world" in lines


# ── 场景 2：中断后会话可继续（状态不残留）───────────────────────


class TestSessionContinuesAfterInterrupt:
    """票 INT-1：中断清除后，同一 caller 可继续正常出结果。"""

    def test_call_after_interrupt_cleared(self):
        interrupt = threading.Event()
        caller = create_llm_caller("k", "http://api.test", "m", tools_schema=[])

        # 第一次调用：中断已置位 → 抛 LLMInterrupted
        interrupt.set()
        with pytest.raises(LLMInterrupted):
            caller([{"role": "user", "content": "hi"}],
                   _interrupt_event=interrupt)

        # 中断清除 → 同一 caller 再次调用正常返回
        interrupt.clear()
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "choices": [{"message": {"role": "assistant", "content": "ok"}}]
        }
        with patch("core.llm_caller._post_with_headers_watchdog",
                   return_value=resp) as mock_post:
            result = caller([{"role": "user", "content": "hi"}],
                            _interrupt_event=interrupt)
            assert result["choices"][0]["message"]["content"] == "ok"
            mock_post.assert_called_once()

    def test_interrupt_event_does_not_persist_in_caller(self):
        """对照组：caller 本身不持有中断状态——中断是注入的事件，非调用级残留。"""
        caller = create_llm_caller("k", "http://api.test", "m", tools_schema=[])
        # 不带 _interrupt_event 的普通调用，即使之前发生过中断也正常
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "choices": [{"message": {"role": "assistant", "content": "ok"}}]
        }
        with patch("core.llm_caller._post_with_headers_watchdog",
                   return_value=resp):
            result = caller([{"role": "user", "content": "hi"}])
            assert result["choices"][0]["message"]["content"] == "ok"
