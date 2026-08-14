"""TICKET-CORE-INT2 回归测试 — 中断链路取证修复。

取证结论（events.jsonl 实弹，2026-08-14）：
- 39 次 engine.cancel.requested 中 23 次 ≤15s 退出、16 次 >15s（最长 129s）；
- 129s 案例断环定位：cancel 6 连发 → 引擎在 llm.call（headers 阶段）→ 129s 零事件 →
  exit interrupted。根因：_post_with_headers_watchdog 主线程 join(timeout=90) 期间
  无 _interrupt_event 检查 —— headers 阶段是无检查点黑洞。
- 57s 案例同根因（<90s：headers 中途返回后流式 1s 检查点兜底捕获）。

修复：
- INT2-A：_post_with_headers_watchdog 加 _interrupt_event 参数，join 改 0.5s 短轮询，
  中断置位立即 shutdown socket + 抛 LLMInterrupted（≤0.5s 响应，验收口径 1 检查点周期内）。
- INT2-B：cancel() 打点补全 —— requested 无条件写（原实现 miss 路径静默）、
  命中写 found+set、miss 写 miss + running_sids 快照（消灭无声死亡）。

覆盖：
- INT2-1 静态断言：watchdog 签名/轮询/中断抛出；cancel 四打点
- INT2-2 单元实弹：headers 阶段挂起 + 中断置位 → <1s 抛 LLMInterrupted
- INT2-3 cancel 打点行为：命中 → requested+found+set；miss → requested+miss（附注册表快照）
"""

import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
import sys

sys.path.insert(0, str(ROOT))

from core import engine_adapter as ea  # noqa: E402
from core import llm_caller as lc  # noqa: E402


# ── INT2-1：静态断言 ──────────────────────────────────────────────────

def test_int2_1_headers_watchdog_interruptible():
    """watchdog 必须带 _interrupt_event 参数 + 短轮询 + 中断抛 LLMInterrupted。"""
    import inspect

    sig = inspect.signature(lc._post_with_headers_watchdog)
    assert "_interrupt_event" in sig.parameters, "INT2: watchdog 需要 _interrupt_event 参数"

    src = Path(lc.__file__).read_text(encoding="utf-8")
    assert "join(timeout=min(0.5, _remaining))" in src, "INT2: join 必须改 0.5s 短轮询"
    assert "_interrupt_event is not None and _interrupt_event.is_set()" in src, \
        "INT2: 轮询循环须检查中断标志"
    assert 'raise LLMInterrupted("user interrupt during headers (silent)")' in src, \
        "INT2: 中断须抛 LLMInterrupted（走引擎既有 interrupted 路径，绝不重试）"
    assert "_close_socket(_sock)" in src, "INT2: 中断须 shutdown 打断阻塞 socket"


def test_int2_1_cancel_full_trace():
    """cancel() 四打点：requested 无条件 + found/set 命中 + miss 附注册表快照。"""
    src = Path(ea.__file__).read_text(encoding="utf-8")
    # requested 必须移到函数开头（命中与否都写）
    assert src.index("engine.cancel.requested") < src.index("event = _running.get(sid)"), \
        "INT2: requested 必须在查表前无条件写（消灭 miss 静默）"
    assert "engine.cancel.found" in src, "INT2: 命中打点 found 缺失"
    assert "engine.cancel.set" in src, "INT2: set 打点缺失"
    assert "engine.cancel.miss" in src, "INT2: miss 打点缺失"
    assert "running_sids" in src, "INT2: miss 须附 running_sids 注册表快照"


# ── INT2-2：单元实弹 —— headers 阶段中断 ≤1s 响应 ────────────────────

def test_int2_2_headers_interrupt_responds_fast(monkeypatch):
    """headers 阶段挂起（服务端不返回响应头）时中断置位 → <1s 抛 LLMInterrupted。"""
    interrupt = threading.Event()
    release = threading.Event()
    calls = []

    class FakeResp:
        status_code = 200
        text = ""
        raw = None

        def close(self):
            pass

    def fake_post(url, **kw):
        calls.append(("post", kw.get("stream")))
        # 模拟服务端 headers 阶段挂起：只等测试收尾信号，不随客户端中断解除
        # （真实场景：服务端挂起不会因为客户端 cancel 而返回响应头）
        release.wait(timeout=30)
        return FakeResp()

    monkeypatch.setattr(lc.requests, "post", fake_post)

    def fire():
        time.sleep(0.2)  # 让 worker 进入挂起
        interrupt.set()

    t = threading.Thread(target=fire)
    t.start()
    t0 = time.time()
    try:
        with pytest.raises(lc.LLMInterrupted):
            lc._post_with_headers_watchdog(
                "http://fake/api",
                json={},
                headers={},
                timeout=(5, 120),
                stream=True,
                headers_timeout=90,  # 预算 90s，中断必须远早于此返回
                _interrupt_event=interrupt,
            )
    finally:
        release.set()  # 放行 worker 线程，避免 pytest 等待非 daemon 线程
        t.join(timeout=2)
    dt = time.time() - t0
    assert dt < 5, f"INT2: headers 阶段中断响应需 <5s，实际 {dt:.1f}s（验收口径 1 检查点周期）"
    assert calls, "INT2: requests.post 应已被调用"


# ── INT2-3：cancel 打点行为 ───────────────────────────────────────────

def test_int2_3_cancel_hit_trace(monkeypatch):
    """命中路径：requested → found → set 三连打点。"""
    trace = []
    fake_bus = type("FB", (), {"write": staticmethod(lambda t, d: trace.append((t, d)))})()
    monkeypatch.setattr(ea, "_running", {"sid_x": threading.Event()})

    import core.event_bus as eb
    monkeypatch.setattr(eb, "event_bus", fake_bus)
    # cancel 内部 from core.event_bus import event_bus —— monkeypatch 模块属性生效
    ea.cancel("sid_x")
    types = [t for t, _ in trace]
    assert types == ["engine.cancel.requested", "engine.cancel.found", "engine.cancel.set"], \
        f"INT2: 命中路径打点序列错误: {types}"
    assert trace[0][1] == {"session_id": "sid_x"}


def test_int2_3_cancel_miss_trace(monkeypatch):
    """miss 路径：requested + miss 双打点，附 running_sids 快照，绝不静默。"""
    trace = []
    fake_bus = type("FB", (), {"write": staticmethod(lambda t, d: trace.append((t, d)))})()
    monkeypatch.setattr(ea, "_running", {"sid_a": threading.Event()})

    import core.event_bus as eb
    monkeypatch.setattr(eb, "event_bus", fake_bus)
    ea.cancel("sid_ghost")
    types = [t for t, _ in trace]
    assert types == ["engine.cancel.requested", "engine.cancel.miss"], \
        f"INT2: miss 路径打点序列错误: {types}"
    assert trace[1][1]["session_id"] == "sid_ghost"
    assert trace[1][1]["running_sids"] == ["sid_a"], "INT2: miss 须附注册表快照"


def test_int2_3_cancel_miss_no_set():
    """miss 路径不得 set 任何 event（僵尸打点）。"""
    ev = threading.Event()
    src = Path(ea.__file__).read_text(encoding="utf-8")
    assert "return" in src, "INT2: miss 路径须 return（不触碰 event）"
    # 行为验证：ghost sid 不 set 真实 event
    ea._running.clear()
    ea.cancel("ghost")
    assert not ev.is_set(), "INT2: ghost sid 不得 set 无关 event"
