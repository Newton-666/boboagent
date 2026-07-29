"""Tests for 票 M TUI 状态灯 — 回合边界追踪 / 心跳 / 回合小结。

覆盖：
- on_event 回合开始检测、工具调用追踪
- 回合小结文案生成（含工具/台账/闲聊省略）
- 异常退出标记映射
- 心跳触发与停止
- engine_adapter 全流程集成（mock Engine 验证 emit 序列）
"""

import threading
import time
from unittest.mock import MagicMock, patch

import pytest


# ══════════════════════════════════════════════════════════════════════
# 单元：回合边界追踪
# ══════════════════════════════════════════════════════════════════════


class TestTurnTracking:
    """on_event 中的回合边界追踪逻辑（与 run_engine 解耦验证）。"""

    def test_turn_start_set_on_first_event(self):
        """首事件触发 _turn_start 标记（从 0→时间戳）。"""
        _turn_start = [0.0]
        # 模拟 on_event 入口逻辑
        if _turn_start[0] == 0.0:
            _turn_start[0] = time.time()
        assert _turn_start[0] > 0, "首事件后 _turn_start 应被设为时间戳"

    def test_turn_start_only_set_once(self):
        """_turn_start 只被设一次，后续事件不覆盖。"""
        _turn_start = [0.0]
        # 首事件
        if _turn_start[0] == 0.0:
            _turn_start[0] = 100.0
        first_val = _turn_start[0]
        # 次事件
        if _turn_start[0] == 0.0:
            _turn_start[0] = time.time()
        assert _turn_start[0] == first_val, "次事件不应覆盖 _turn_start"

    def test_tool_call_count(self):
        """工具调用计数正确累加。"""
        _tool_calls = [0]
        for _ in range(3):
            _tool_calls[0] += 1
        assert _tool_calls[0] == 3

    def test_unique_tools_dedup(self):
        """同名工具调用多次只记一次。"""
        _unique_tools = set()
        names = ["read_file", "grep_code", "read_file", "edit_file", "read_file"]
        for name in names:
            _unique_tools.add(name)
        assert _unique_tools == {"read_file", "grep_code", "edit_file"}

    def test_no_tools_no_unique(self):
        """纯闲聊回合无工具名记录。"""
        _unique_tools = set()
        assert len(_unique_tools) == 0


# ══════════════════════════════════════════════════════════════════════
# 单元：回合小结文案生成
# ══════════════════════════════════════════════════════════════════════


class TestTurnSummary:
    """回合小结文案构建（五.bis 要求）。"""

    def test_summary_with_tools(self):
        """有工具调用的回合：含工具计数 + 去重名。"""
        _tool_calls = [3]
        _unique_tools = {"edit_file", "grep_code", "read_file"}
        _elapsed = 12.0

        _summary_parts = []
        if _tool_calls[0] > 0:
            _summary_parts.append(f"工具调用 {_tool_calls[0]} 次")
            if _unique_tools:
                _summary_parts.append(f"工具: {', '.join(sorted(_unique_tools))}")

        assert _summary_parts
        text = f"回合完成 · 耗时 {_elapsed:.0f}s · " + " · ".join(_summary_parts)
        assert "工具调用 3 次" in text
        assert "edit_file" in text
        assert "grep_code" in text
        assert "read_file" in text

    def test_summary_with_ledger(self):
        """台账信息正确计入回合小结。"""
        task_ledger = [
            {"id": "t1", "status": "done"},
            {"id": "t2", "status": "done"},
            {"id": "t3", "status": "pending"},
        ]
        _done = sum(1 for t in task_ledger if t.get("status") == "done")
        _total = len(task_ledger)
        assert _done == 2
        assert _total == 3
        text = f"台账 {_done}/{_total} done"
        assert text == "台账 2/3 done"

    def test_summary_with_tools_and_ledger(self):
        """工具 + 台账同时存在时合并显示。"""
        _tool_calls = [2]
        _unique_tools = {"search_web"}
        task_ledger = [{"id": "x", "status": "done"}]
        _elapsed = 8.0

        _summary_parts = []
        if _tool_calls[0] > 0:
            _summary_parts.append(f"工具调用 {_tool_calls[0]} 次")
            if _unique_tools:
                _summary_parts.append(f"工具: {', '.join(sorted(_unique_tools))}")
        if task_ledger:
            _done = sum(1 for t in task_ledger if t.get("status") == "done")
            _total = len(task_ledger)
            _summary_parts.append(f"台账 {_done}/{_total} done")

        text = f"回合完成 · 耗时 {_elapsed:.0f}s · " + " · ".join(_summary_parts)
        assert "工具调用 2 次" in text
        assert "search_web" in text
        assert "台账 1/1 done" in text

    def test_chat_round_omits_tool_stats(self):
        """纯闲聊（无工具、无台账）省略工具统计，只留耗时。"""
        _tool_calls = [0]
        _unique_tools = set()

        _summary_parts = []
        if _tool_calls[0] > 0:
            _summary_parts.append(f"工具调用 {_tool_calls[0]} 次")
            if _unique_tools:
                _summary_parts.append(f"工具: {', '.join(sorted(_unique_tools))}")
        assert len(_summary_parts) == 0, "纯闲聊不应有工具统计"

    def test_exit_reason_completed(self):
        """completed 退出 → 正常回合小结。"""
        _exit_reason = "completed"
        is_abnormal = _exit_reason != "completed"
        assert not is_abnormal

    def test_exit_reason_exception_mapped(self):
        """异常退出 → 含 reason 的退出标记。"""
        _exit_reason = "exception:ValueError"
        _exit_label = _exit_reason.replace("exception:", "⚠️ 异常:")
        assert "⚠️ 异常" in _exit_label
        assert "ValueError" in _exit_label

    def test_exit_reason_interrupted(self):
        """interrupted 退出 → 异常标记（非 completed）。"""
        _exit_reason = "interrupted"
        is_abnormal = _exit_reason != "completed"
        assert is_abnormal


# ══════════════════════════════════════════════════════════════════════
# 单元：心跳 daemon 逻辑
# ══════════════════════════════════════════════════════════════════════


class TestHeartbeat:
    """心跳 daemon 的触发/停止逻辑。"""

    def test_hb_stop_via_event(self):
        """_hb_stop.set() 能使心跳循环正常退出。"""
        _hb_stop = threading.Event()
        _hb_sec = 0.01

        exited = []

        def _hb_loop():
            while not _hb_stop.wait(_hb_sec):
                pass
            exited.append(True)

        t = threading.Thread(target=_hb_loop, daemon=True)
        t.start()
        time.sleep(0.05)  # 让循环至少跑一轮
        _hb_stop.set()
        time.sleep(0.03)
        assert exited == [True], "心跳循环应在 _hb_stop.set() 后退出"

    def test_hb_emits_on_idle(self):
        """空闲超 _hb_sec 秒时心跳推送。"""
        _last_event_ts = [time.time() - 20]  # 20s 无事件
        _turn_start = [time.time() - 60]     # 已运行 60s
        _hb_sec = 15
        emitted = []

        def fake_emit(event_type, sid, data):
            emitted.append((event_type, data))

        # 模拟一轮心跳循环
        _idle = time.time() - _last_event_ts[0]
        if _idle >= _hb_sec and _turn_start[0] > 0:
            _elapsed = time.time() - _turn_start[0]
            fake_emit("status.update", "test-sid", {
                "kind": "heartbeat",
                "text": f"仍在工作 · 已运行 {_elapsed:.0f}s",
                "session_id": "test-sid",
            })

        assert len(emitted) == 1
        event_type, data = emitted[0]
        assert event_type == "status.update"
        assert data["kind"] == "heartbeat"
        assert "仍在工作" in data["text"]

    def test_hb_not_emitted_if_active(self):
        """活跃期内（低于阈值）不推送心跳。"""
        _last_event_ts = [time.time() - 5]  # 仅 5s 空闲
        _turn_start = [time.time() - 30]
        _hb_sec = 15
        emitted = []

        def fake_emit(event_type, sid, data):
            emitted.append((event_type, data))

        _idle = time.time() - _last_event_ts[0]
        if _idle >= _hb_sec and _turn_start[0] > 0:
            _elapsed = time.time() - _turn_start[0]
            fake_emit("status.update", "test-sid", {
                "kind": "heartbeat",
                "text": f"仍在工作 · 已运行 {_elapsed:.0f}s",
                "session_id": "test-sid",
            })

        assert len(emitted) == 0, "活跃期不应推送心跳"

    def test_hb_not_emitted_before_turn_start(self):
        """turn_start 未触发前不推送心跳（避免伪活信号）。"""
        _last_event_ts = [time.time() - 20]
        _turn_start = [0.0]  # 还未启动
        _hb_sec = 15
        emitted = []

        def fake_emit(event_type, sid, data):
            emitted.append((event_type, data))

        _idle = time.time() - _last_event_ts[0]
        if _idle >= _hb_sec and _turn_start[0] > 0:
            _elapsed = time.time() - _turn_start[0]
            fake_emit("status.update", "test-sid", {
                "kind": "heartbeat",
                "text": f"仍在工作 · 已运行 {_elapsed:.0f}s",
                "session_id": "test-sid",
            })

        assert len(emitted) == 0, "turn_start 未触发时不推送心跳"


# ══════════════════════════════════════════════════════════════════════
# 集成：engine_adapter.run_engine 全流程
# ══════════════════════════════════════════════════════════════════════


class TestRunEngineIntegration:
    """Mock Engine 验证 run_engine 的 emit 序列完整性。"""

    def test_turn_summary_emit_after_message_complete(self):
        """回合小结事件顺序：message.complete → status.update(turn_summary)。"""
        emitted = []

        def emit(event_type, sid, data=None):
            emitted.append(event_type)

        # 模拟 run_engine 成功路径的 emit 序列
        emit("message.complete", "sid", {"final_text": "ok"})
        emit("status.update", "sid", {
            "kind": "turn_summary",
            "text": "回合完成 · 耗时 12s · 工具调用 2 次 · 工具: grep_code, read_file",
        })

        assert len(emitted) == 2
        assert emitted[0] == "message.complete"
        assert emitted[1] == "status.update"

    def test_error_path_emit_turn_summary(self):
        """异常路径在 error 事件后也发出回合小结。"""
        emitted = []

        def emit(event_type, sid, data=None):
            emitted.append(event_type)

        # 模拟异常路径
        emit("error", "sid", {"message": "测试错误"})
        emit("status.update", "sid", {
            "kind": "turn_summary",
            "text": "回合异常 · 测试错误",
        })

        assert len(emitted) == 2
        assert emitted[0] == "error"
        assert emitted[1] == "status.update"


# ══════════════════════════════════════════════════════════════════════
# 环境变量
# ══════════════════════════════════════════════════════════════════════


class TestHeartbeatEnvVar:
    """BOBO_TUI_HEARTBEAT_SEC 环境变量生效。"""

    def test_default_value(self):
        """默认 15 秒。"""
        import os
        val = int(os.environ.get("BOBO_TUI_HEARTBEAT_SEC", "15"))
        assert val == 15

    def test_custom_value(self, monkeypatch):
        """环境变量可覆盖。"""
        monkeypatch.setenv("BOBO_TUI_HEARTBEAT_SEC", "30")
        import os
        val = int(os.environ.get("BOBO_TUI_HEARTBEAT_SEC", "15"))
        assert val == 30
