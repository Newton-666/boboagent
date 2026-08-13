"""票 ENG-1c：回复终局性回归测试。

owner 裁决语义：收尾（台账/笔记/提取/回合小结）全部在回复发出之前完成；
message.complete 发出后，本回合零 LLM 调用、零工具调用、零用户可见事件，
状态立即 ready。

本测试聚焦 run_engine 层 emit 序列：
  1. message.complete 必须是本回合最后一个 emit（其后零事件）
  2. turn_exit（中断路径）在 complete 之前
  3. turn_summary（空回复兜底路径）在 complete 之前
  4. heartbeat（若触发）在 complete 之前，complete 后心跳不再发声

用假 Engine 模拟三种收尾形态（正常/中断/空回复），
复用 test_engine_adapter_interrupt.py 的 monkeypatch 模式。
"""

import threading
import time as _time

from core import engine_adapter
from core import engine as engine_mod


class FakeEngine:
    """run_engine 内部 Engine 的最小替身：run() 模拟产出 + 可选中断/空回复。"""

    def __init__(self, *args, **kwargs):
        self.callback = kwargs.get("callback")  # run_engine 传入的 on_event
        self.sid = None
        self.history = []
        self.checkpoint_mgr = __import__("types").SimpleNamespace(checkpoints=[])
        self.task_ledger = []
        self.proactive = __import__("types").SimpleNamespace(load_config=lambda: None)
        self._interrupt_event = None
        self._exit_reason = "completed"
        self._interrupt = False
        self._empty = False

    def run(self, text):
        if self._interrupt:
            self.history.append({"role": "assistant", "content": "已完成文件写入"})
            self.checkpoint_mgr.checkpoints.append({"ts": "20260810", "note": "written"})
            self.task_ledger.append({"id": "t1", "title": "写文档", "status": "done"})
            assert self._interrupt_event is not None
            self._interrupt_event.set()
        elif self._empty:
            self.history.append({"role": "assistant", "content": ""})
        else:
            self.history.append({"role": "assistant", "content": "正常完成，收工汇报。"})


def _call_run_engine(monkeypatch, emit, engine_cls=None, hb_sec=None):
    """按 run_engine 全参数签名调用，返回 (session, emitted)。"""
    sid = "test-sid"
    monkeypatch.setattr(engine_mod, "Engine", engine_cls or FakeEngine)

    if hb_sec is not None:
        monkeypatch.setenv("BOBO_TUI_HEARTBEAT_SEC", str(hb_sec))

    session = {
        "messages": [{"role": "user", "content": "继续"}],
        "checkpoints": [],
        "task_ledger": [],
    }
    emitted = []
    saved_sids = []

    def _save(sid_):
        saved_sids.append(sid_)

    engine_adapter.run_engine(
        sid=sid,
        session=session,
        text="继续",
        emit=emit,
        get_llm_caller=lambda: object(),
        get_context_length=lambda: 100_000,
        register_engine_thread=lambda *a, **kw: None,
        pending_confirm={},
        pending_confirm_result={},
        confirm_lock=threading.Lock(),
        auto_mode={},
        current_engines={},
        current_engines_lock=threading.Lock(),
        session_usage={},
        session_usage_lock=threading.Lock(),
        save_session_to_disk=_save,
    )
    return session, emitted


# message.complete 之后绝不允许出现的事件类型（用户可见，非纯日志）
_FORBIDDEN_AFTER_COMPLETE = {
    "message.start", "message.delta", "status.update", "tool.start",
    "tool.complete", "notes.changed", "terminal.output", "approval.request",
    "gateway.error", "error", "reasoning.delta", "message.complete",
}


def _assert_complete_is_final(emitted):
    """message.complete 必须是最后一个事件（其后零事件）。"""
    completes = [i for i, (t, _) in enumerate(emitted) if t == "message.complete"]
    assert len(completes) == 1, f"必须恰好一个 message.complete，实际 {len(completes)}"
    idx = completes[0]
    tail = emitted[idx + 1:]
    assert tail == [], f"message.complete 之后仍有关键事件: {tail}"
    return idx


class TestEng1ReplyFinality:
    """ENG-1c：message.complete 后零事件（引擎层终局性）。"""

    def test_normal_turn_complete_is_final_event(self, monkeypatch):
        """正常完成：message.complete 是最后一个 emit，其后零事件。"""
        emitted = []
        _call_run_engine(monkeypatch, emit=lambda t, s, d=None: emitted.append((t, d)))
        _assert_complete_is_final(emitted)

    def test_interrupt_turn_exit_before_complete(self, monkeypatch):
        """中断路径：turn_exit 在 message.complete 之前（complete 最后）。"""
        class InterruptEngine(FakeEngine):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self._interrupt = True

        emitted = []
        _call_run_engine(monkeypatch, emit=lambda t, s, d=None: emitted.append((t, d)),
                         engine_cls=InterruptEngine)

        types = [t for t, _ in emitted]
        # 中断必须有 turn_exit 与 complete
        assert "status.update" in types
        assert types.count("message.complete") == 1
        # 顺序：turn_exit 在 complete 之前
        exit_idx = next(i for i, (t, d) in enumerate(emitted)
                        if t == "status.update" and d.get("kind") == "turn_exit")
        complete_idx = types.index("message.complete")
        assert exit_idx < complete_idx, "turn_exit 必须在 message.complete 之前"
        _assert_complete_is_final(emitted)

    def test_empty_reply_turn_summary_before_complete(self, monkeypatch):
        """空回复兜底：turn_summary 在 message.complete 之前（complete 最后）。"""
        class EmptyEngine(FakeEngine):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self._empty = True

        emitted = []
        _call_run_engine(monkeypatch, emit=lambda t, s, d=None: emitted.append((t, d)),
                         engine_cls=EmptyEngine)

        summaries = [i for i, (t, d) in enumerate(emitted)
                     if t == "status.update" and d.get("kind") == "turn_summary"]
        assert len(summaries) == 1, "空回复必须走 turn_summary 兜底"
        complete_idx = [i for i, (t, _) in enumerate(emitted) if t == "message.complete"][0]
        assert summaries[0] < complete_idx, "turn_summary 必须在 message.complete 之前"
        _assert_complete_is_final(emitted)

    def test_heartbeat_never_after_complete(self, monkeypatch):
        """心跳：即使回合尾部长空闲，heartbeat 也绝不在 complete 之后出现。"""
        class SlowEngine(FakeEngine):
            def run(self, text):
                if self.callback:
                    # 启动回合时钟（真实引擎 run() 会发 thinking 等回调）
                    self.callback("thinking", {"phase": "working", "message": "工作中"})
                _time.sleep(1.2)  # 长于心跳间隔（1s），保证至少触发一次心跳
                self.history.append({"role": "assistant", "content": "慢回合完成"})

        emitted = []
        _call_run_engine(monkeypatch, emit=lambda t, s, d=None: emitted.append((t, d)),
                         engine_cls=SlowEngine, hb_sec=1)

        heartbeats = [i for i, (t, d) in enumerate(emitted)
                      if t == "status.update" and d.get("kind") == "heartbeat"]
        assert len(heartbeats) >= 1, "慢回合应至少触发一次心跳（测试前提自检）"
        complete_idx = [i for i, (t, _) in enumerate(emitted) if t == "message.complete"][0]
        for hb in heartbeats:
            assert hb < complete_idx, f"heartbeat({hb}) 出现在 complete({complete_idx}) 之后"
        _assert_complete_is_final(emitted)

    def test_no_duplicate_complete_on_interrupt(self, monkeypatch):
        """中断路径不产生重复 complete（AUTO-E 语义保持）。"""
        class InterruptEngine(FakeEngine):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self._interrupt = True

        emitted = []
        _call_run_engine(monkeypatch, emit=lambda t, s, d=None: emitted.append((t, d)),
                         engine_cls=InterruptEngine)
        completes = [d for t, d in emitted if t == "message.complete"]
        assert len(completes) == 1
        assert "[已中断]" in completes[0]["final_text"]
