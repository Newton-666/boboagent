"""票 AUTO-E E-1：run_engine 中断保进度测试。

验证旧行为修复——中断（Ctrl+C / Esc 硬终止）时：
  1. checkpoints / messages / task_ledger 照常回写 session
  2. save_session_to_disk 照常被调用（进度必落盘）
  3. message.complete 照常发射（TUI 回合生命周期靠它解除 busy），
     final_text 带 [已中断] 标注
  4. status.update(turn_exit) 报告 "引擎退出: interrupted"

用假 Engine 模拟"引擎执行期间被中断"（interrupt_event 已 set），
聚焦 run_engine 层的中断回写行为；engine 内部中断路径由
test_engine_e2e.py 的 test_real_interrupt_in_executing_phase 覆盖。
"""

import threading

from core import engine_adapter
from core import engine as engine_mod


class FakeEngine:
    """run_engine 内部 Engine 的最小替身：run() 模拟产出 + 中断。"""

    def __init__(self, *args, **kwargs):
        self.sid = None
        self.history = []
        self.checkpoint_mgr = __import__("types").SimpleNamespace(checkpoints=[])
        self.task_ledger = []
        self.proactive = __import__("types").SimpleNamespace(load_config=lambda: None)
        self._interrupt_event = None
        self._exit_reason = "completed"

    def run(self, text):
        # 模拟本次回合已产生的进度：写文件记录 / 台账 done / 对话消息
        self.history.append({"role": "assistant", "content": "已完成文件写入"})
        self.checkpoint_mgr.checkpoints.append({"ts": "20260810", "note": "written"})
        self.task_ledger.append({"id": "t1", "title": "写文档", "status": "done"})
        # 运行中被用户中断（Ctrl+C / Esc 硬终止通道）
        assert self._interrupt_event is not None
        self._interrupt_event.set()


def _call_run_engine(monkeypatch, emit, save_fn, engine_cls=None):
    """按 run_engine 全参数签名调用，返回 (session, emitted, saved_sids)。"""
    sid = "test-sid"

    # run_engine 内部是 `from core.engine import Engine`（函数内 import），
    # 必须替换 core.engine 模块上的 Engine 属性才生效。
    monkeypatch.setattr(engine_mod, "Engine", engine_cls or FakeEngine)

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
        get_llm_caller=lambda: object(),  # FakeEngine 不使用
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
    return session, emitted, saved_sids


class TestRunEngineInterruptPreservesProgress:
    """E-1：中断保进度——旧行为直接 return 丢进度，新行为照常回写。"""

    def test_interrupt_writes_checkpoints_messages_ledger(self, monkeypatch):
        """中断后 checkpoints / messages / 台账照常回写 session。"""
        session, _, _ = _call_run_engine(
            monkeypatch,
            emit=lambda *a, **kw: None,
            save_fn=None,
        )

        # 1. checkpoints 回写
        assert session["checkpoints"] == [{"ts": "20260810", "note": "written"}]
        # 2. messages 回写（engine.history → session["messages"]）
        assert session["messages"][-1] == {"role": "assistant", "content": "已完成文件写入"}
        # 3. 台账回写
        assert session["task_ledger"][0]["status"] == "done"

    def test_interrupt_still_saves_session_to_disk(self, monkeypatch):
        """中断后 save_session_to_disk 照常被调用（进度必落盘）。"""
        session, _, saved_sids = _call_run_engine(
            monkeypatch,
            emit=lambda *a, **kw: None,
            save_fn=None,
        )

        assert saved_sids == ["test-sid"]
        # 落盘内容 = 已回写的 session（run_engine 原地修改传入的 session dict）
        assert session["messages"][-1]["role"] == "assistant"
        assert session["task_ledger"][0]["status"] == "done"

    def test_interrupt_emits_message_complete_with_marker(self, monkeypatch):
        """中断后 message.complete 照常发射，final_text 带 [已中断] 标注。"""
        emitted = []

        def emit(event_type, sid, data=None):
            emitted.append((event_type, data))

        _call_run_engine(monkeypatch, emit=emit, save_fn=None)

        completes = [d for t, d in emitted if t == "message.complete"]
        assert len(completes) == 1, "中断也必须有一个结束事件解除 TUI busy"
        assert "[已中断]" in completes[0]["final_text"]
        assert completes[0]["session_id"] == "test-sid"

    def test_interrupt_emits_turn_exit_interrupted(self, monkeypatch):
        """中断后 status.update(turn_exit) 报告 interrupted（回合小结兜底）。"""
        emitted = []

        def emit(event_type, sid, data=None):
            emitted.append((event_type, data))

        _call_run_engine(monkeypatch, emit=emit, save_fn=None)

        exits = [d for t, d in emitted if t == "status.update" and d.get("kind") == "turn_exit"]
        assert len(exits) == 1
        assert "interrupted" in exits[0]["text"]

    def test_interrupt_not_swallowed_by_exception_path(self, monkeypatch):
        """中断不是异常：不进 exception 分支，回写与 complete 照常。"""
        emitted = []

        def emit(event_type, sid, data=None):
            emitted.append((event_type, data))

        _call_run_engine(monkeypatch, emit=emit, save_fn=None)

        # 无 error 事件（中断 ≠ 异常）
        assert not [t for t, _ in emitted if t == "error"]

    def test_completed_turn_has_no_interrupt_marker(self, monkeypatch):
        """对照组：正常完成（interrupt 未 set）final_text 不带 [已中断]。"""
        class NormalEngine(FakeEngine):
            def run(self, text):
                self.history.append({"role": "assistant", "content": "正常完成"})

        emitted = []

        def emit(event_type, sid, data=None):
            emitted.append((event_type, data))

        _call_run_engine(monkeypatch, emit=emit, save_fn=None, engine_cls=NormalEngine)

        completes = [d for t, d in emitted if t == "message.complete"]
        assert len(completes) == 1
        assert "[已中断]" not in completes[0]["final_text"]
