"""票 TICKET-INT-1：LLM 流式调用可中断（Interrupt 一刀切）。

实证：推理模型单次思考最长 86s（2026-08-13 13:46），期间 stop 置位无人可见，
引擎要等 LLM 调用整体返回才在回合检查点（engine.py:1422/1955）发现。

修复：
  1. llm_caller 流式读循环每 chunk 查 _interrupt_event（仿 execute_terminal 注入），
     置位即 _force_close 断流 + 抛 LLMInterrupted（绝不重试）
  2. 引擎捕获 LLMInterrupted 走既有 interrupted 路径（STATE interrupted、正常退场）
  3. 收尾沉淀（takeaway 提取 + living_notes）同样接受中断
  4. 非流式调用入口前检查一次

本文件专项覆盖：
  - 流式中断 → LLMInterrupted（断流 + 抛异常，线程 join 超时 <5s 收紧）
  - 无中断流式正常路径回归（检查点不破坏正常流）
  - 非流式入口前检查（中断已置位 → 不发请求直接抛）
  - engine 集成：思考中中断 → run 正常返回、STATE interrupted、无状态残留
  - takeaway 提取中断 → 静默返回 []（不留 notes.error）
"""

import threading
import time

import pytest

from core import llm_caller as lc
from core.llm_caller import LLMInterrupted
from core.engine import Engine
from core.tool_executor import execute_tool


# ── 1. 流式中断 → LLMInterrupted ────────────────────────────────

def _make_fake_response():
    class FakeResponse:
        status_code = 200
        text = ""

        def close(self):
            pass

    return FakeResponse()


def test_streaming_interrupt_raises_llm_interrupted(monkeypatch):
    """流式读循环中中断置位 → 断流 + 抛 LLMInterrupted（<1s 验收口径）。"""
    interrupt = threading.Event()

    def fake_post(api_url, **kw):
        assert kw.get("stream") is True  # 流式模式
        return _make_fake_response()

    monkeypatch.setattr(lc, "_post_with_headers_watchdog", fake_post)

    def fake_read(response, read_timeout, vitals, _interrupt_event=None):
        # 先吐一个内容块（进入循环体），然后挂起模拟思考中
        yield b'data: {"choices":[{"delta":{"content":"hi"}}]}\n\n'
        while not _interrupt_event.is_set():
            time.sleep(0.01)
        # 中断已置位：空行触发循环体 → 每 chunk 检查点命中
        yield b""

    monkeypatch.setattr(lc, "_read_stream_lines", fake_read)

    caller = lc.create_llm_caller("k", "http://x", "m")
    outcome = {}

    def _run():
        try:
            caller([{"role": "user", "content": "hi"}],
                   stream_callback=lambda t: None,
                   _interrupt_event=interrupt)
            outcome["ok"] = True
        except LLMInterrupted as e:
            outcome["interrupted"] = str(e)

    t = threading.Thread(target=_run)
    t.start()
    time.sleep(0.05)  # 让流进入挂起
    _t0 = time.time()
    interrupt.set()
    t.join(timeout=5)
    _elapsed = time.time() - _t0

    assert not t.is_alive(), "中断后流式调用必须在限定时间内退出"
    assert outcome.get("interrupted"), f"期望 LLMInterrupted，实际 {outcome}"
    assert _elapsed < 1.0, f"断流退场应 <1s，实际 {_elapsed:.2f}s"


def test_streaming_no_interrupt_normal_path(monkeypatch):
    """无中断时流式正常路径回归——检查点不破坏正常流（零回归基线）。"""
    interrupt = threading.Event()

    def fake_post(api_url, **kw):
        return _make_fake_response()

    monkeypatch.setattr(lc, "_post_with_headers_watchdog", fake_post)

    def fake_read(response, read_timeout, vitals, _interrupt_event=None):
        yield b'data: {"choices":[{"delta":{"content":"Hello"}}]}\n\n'
        yield b'data: {"choices":[{"delta":{"content":" world"}}]}\n\n'
        yield b'data: {"choices":[{"delta":{"finish_reason":"stop"}}]}\n\n'
        yield b"data: [DONE]\n\n"

    monkeypatch.setattr(lc, "_read_stream_lines", fake_read)

    caller = lc.create_llm_caller("k", "http://x", "m")
    chunks = []

    result = caller([{"role": "user", "content": "hi"}],
                    stream_callback=chunks.append,
                    _interrupt_event=interrupt)

    assert "".join(chunks) == "Hello world"
    assert result["choices"][0]["message"]["content"] == "Hello world"
    assert result["finish_reason"] == "stop"


def test_streaming_silent_interrupt_raises(monkeypatch):
    """完全静默（模型思考中零 chunk）→ _read_stream_lines 轮询 1s 内响应中断。

    走真实 _read_stream_lines（不 mock）：reader 线程永久挂起模拟零字节流，
    主循环 q.get(timeout=1.0) 每秒空转一次，在超时路径检查中断标志断流。
    """
    interrupt = threading.Event()

    class FakeRaw:
        decode_content = False

        def read1(self, n):
            # 完全静默：永久挂起（不返回 EOF，逼主循环走 q.get 超时检查路径）
            while True:
                time.sleep(0.01)

        read = read1

    class FakeResponse:
        status_code = 200
        text = ""

        def __init__(self):
            self.raw = FakeRaw()

        def close(self):
            pass

    def fake_post(api_url, **kw):
        return FakeResponse()

    monkeypatch.setattr(lc, "_post_with_headers_watchdog", fake_post)
    # 不 mock _read_stream_lines——验证真实轮询路径的中断响应

    caller = lc.create_llm_caller("k", "http://x", "m")
    outcome = {}

    def _run():
        try:
            caller([{"role": "user", "content": "hi"}],
                   stream_callback=lambda t: None,
                   _interrupt_event=interrupt)
            outcome["ok"] = True
        except LLMInterrupted as e:
            outcome["interrupted"] = str(e)

    t = threading.Thread(target=_run)
    t.start()
    time.sleep(0.1)  # 让流进入完全静默
    _t0 = time.time()
    interrupt.set()
    t.join(timeout=5)
    _elapsed = time.time() - _t0

    assert not t.is_alive(), "静默中断后流式调用必须在限定时间内退出"
    assert outcome.get("interrupted"), f"期望 LLMInterrupted，实际 {outcome}"
    # q.get 周期 1s：中断置位后最坏 ~1s 发现 + 立即断流（理论口径 <1s，实测浮动给裕量）
    assert _elapsed < 2.0, f"静默中断断流应 ≤1s 周期，实际 {_elapsed:.2f}s"


# ── 2. 非流式入口前检查 ─────────────────────────────────────────

def test_non_stream_interrupt_before_call(monkeypatch):
    """中断已置位 → 非流式调用入口直接抛，不发请求。"""
    def fake_post(**kw):
        raise AssertionError("中断已置位，不应发出任何请求")

    monkeypatch.setattr(lc, "_post_with_headers_watchdog", fake_post)

    caller = lc.create_llm_caller("k", "http://x", "m")
    interrupt = threading.Event()
    interrupt.set()

    with pytest.raises(LLMInterrupted):
        caller([{"role": "user", "content": "hi"}],
               use_tools=False, max_tokens=512,
               _interrupt_event=interrupt)


# ── 3. engine 集成：思考中中断 → 走既有 interrupted 路径 ─────────

class _HangThenInterruptLLM:
    """模拟推理模型思考中：收到流式回调 → 挂起，中断置位后抛 LLMInterrupted。"""

    def __init__(self, interrupt):
        self._interrupt = interrupt

    def __call__(self, messages, use_tools=True, stream_callback=None,
                 retry_callback=None, tools_override=None, session_id=None,
                 reasoning_callback=None, max_tokens=None, _interrupt_event=None):
        assert _interrupt_event is self._interrupt, "引擎必须注入 _interrupt_event"
        if stream_callback:
            while not self._interrupt.is_set():
                time.sleep(0.01)
            raise LLMInterrupted("user interrupt during stream")
        return {"choices": [{"message": {"content": ""}}]}


def test_engine_thinking_interrupt_exits_cleanly():
    """思考中 stop → engine 捕获 LLMInterrupted → STATE interrupted、正常退场、无残留。"""
    interrupt = threading.Event()

    engine = Engine(_HangThenInterruptLLM(interrupt), execute_tool,
                    test_mode=True)
    engine._interrupt_event = interrupt

    def _run():
        engine.run("hi")

    t = threading.Thread(target=_run)
    t.start()
    time.sleep(0.05)  # 让引擎进入 THINKING 挂起
    interrupt.set()
    t.join(timeout=5)

    assert not t.is_alive(), "中断后引擎线程必须正常退场（不抛异常到 adapter）"
    # 走既有 interrupted 路径：_emit_state_change(STATE_ERROR, "interrupted")
    # （事件走 event_bus 非 callback，此处断言引擎状态）
    assert engine.state == engine.STATE_ERROR, \
        f"期望 STATE_ERROR（interrupted 路径），实际 {engine.state}"
    # 无状态残留：引擎已退场，state 不应停留在 thinking/executing
    assert engine.state not in (engine.STATE_THINKING, engine.STATE_EXECUTING), \
        f"状态残留: {engine.state}"


# ── 4. 收尾沉淀：takeaway 提取中断 → 静默返回 [] ─────────────────

class _InterruptImmediatelyLLM:
    def __call__(self, messages, use_tools=True, stream_callback=None,
                 retry_callback=None, tools_override=None, session_id=None,
                 reasoning_callback=None, max_tokens=None, _interrupt_event=None):
        assert _interrupt_event is not None, "沉淀调用必须注入 _interrupt_event"
        raise LLMInterrupted("user interrupt")


def test_extract_takeaways_interrupt_returns_empty():
    """沉淀提取期间中断 → 静默返回 []（不留 notes.error、不阻塞）。"""
    interrupt = threading.Event()
    interrupt.set()  # 提取前已中断

    engine = Engine(_InterruptImmediatelyLLM(), execute_tool, test_mode=True)
    engine._interrupt_event = interrupt

    result = engine._extract_takeaways(
        fallback_content="用户消息",
        history=[{"role": "user", "content": "hi"}],
        tool_round=0,
    )
    assert result == []
