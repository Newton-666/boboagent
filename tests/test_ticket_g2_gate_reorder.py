"""票 G2 收工闸时序重排（先账后复）+ 死锁安全阀验收测试。

语义迁移说明（票 G2-3）：
- 旧时序：LLM 生成最终回复 → 进 RESPONDING → 收工闸查账 → 不平回注（用户看到"回复了还在想"）。
- 新时序：闸在 THINKING 分支执行（进 RESPONDING 之前）——账不平回注（用户只见 Working），
  账平/纯聊天才进 RESPONDING 发回复，回复发出 = 闸过 = 回合结束。
- 现有 test_goal_gate.py / test_ticket_c_ledger_gate.py 断言的是闸的**结果语义**
  （deny 次数、事件落地、最终 DONE），对闸在哪个阶段执行不敏感，天然兼容新时序，无需重写。
  本文件新增覆盖**时序本身**与新安全阀行为的测试。
"""

import pytest

from tests.test_engine_e2e import (
    FakeLLMCaller, FakeToolExecutor, _make_tool_call, _make_test_engine, _collect_states,
)


def _track_notify_complete(engine):
    """包装 _notify，记录 complete 事件。返回事件列表。"""
    completes = []
    original_notify = engine._notify

    def tracking_notify(event_type, data):
        if event_type == "complete":
            completes.append(data)
        original_notify(event_type, data)

    engine._notify = tracking_notify
    return completes


def _make_auto_engine(fake_llm, fake_tools, monkeypatch, ledger, auto=True):
    """构造 engine：设台账 + 开/关 auto_mode_getter（与票 C 测试同款）。"""
    engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)
    engine.task_ledger = ledger
    engine._auto_mode_getter = (lambda: True) if auto else (lambda: False)
    return engine


class TestGateBeforeReply:
    """G2-1：先账后复——账不平无回复发出（闸在进 RESPONDING 前）"""

    def test_pending_ledger_no_reply_until_done(self, monkeypatch):
        """台账有 pending → 收工文本被闸拦：无 complete 通知、状态回 THINKING；
        回注后建账全 done → 才发回复 → DONE。"""
        fake_llm = FakeLLMCaller([
            ("已完成全部工作", None),  # R1: pending 账 → 闸拦回注
            ("已完成全部工作", None),  # R2: 建账后放行
        ])
        fake_tools = FakeToolExecutor()
        engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)
        engine.task_ledger = [{"id": "1", "title": "任务", "status": "pending", "verify": "跑测试"}]

        # 拦截 pending 回注事件，在第一次回注后把台账置全 done（模拟模型建账销账）
        original_emit = engine._emit_state_change
        _injected = [False]

        def tracking_emit(state, reason):
            if state == engine.STATE_THINKING and "ledger re-injection" in str(reason) and not _injected[0]:
                _injected[0] = True
                engine.task_ledger = [{"id": "1", "title": "任务", "status": "done",
                                       "verify": "跑测试", "evidence": "全过"}]
            original_emit(state, reason)

        engine._emit_state_change = tracking_emit

        completes = _track_notify_complete(engine)
        engine.run(user_input="干活")

        assert engine.state == engine.STATE_DONE
        # 回注期间无 complete；建账后闸过只发 1 次回复
        assert len(completes) == 1, f"只有闸过后发 1 次回复，实际 {len(completes)}"
        # 回注消息落地（pending 未完成提示）
        assert any("未完成" in (m.get("content") or "") for m in engine.history
                   if m.get("role") == "user")

    def test_no_reply_emitted_when_gate_blocks(self, monkeypatch):
        """核心断言：闸拦时 complete 通知计数为 0（用户看不到任何回复）。"""
        fake_llm = FakeLLMCaller([
            ("完成了", None),  # R1: 有 pending → 拦
        ])
        fake_tools = FakeToolExecutor()
        engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)
        engine.task_ledger = [{"id": "1", "title": "任务", "status": "pending", "verify": "x"}]

        completes = _track_notify_complete(engine)
        # 只跑一轮 step（会被闸拦回注，不会 DONE）
        engine._step()
        assert len(completes) == 0, "闸拦时不应发出任何 complete 通知"
        assert engine.state == engine.STATE_THINKING, "账不平应回 THINKING（用户只见 Working）"

    def test_clean_ledger_reply_once(self, monkeypatch):
        """台账全 done → 闸过 → 一次回复即结束（回复=结束）。"""
        fake_llm = FakeLLMCaller([
            ("全部完成", None),
        ])
        fake_tools = FakeToolExecutor()
        engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)
        engine.task_ledger = [{"id": "1", "title": "任务", "status": "done",
                               "verify": "跑测试", "evidence": "全过"}]

        completes = _track_notify_complete(engine)
        states = _collect_states(engine)
        engine.run(user_input="干活")

        assert engine.state == engine.STATE_DONE
        assert len(completes) == 1, f"账平应只发 1 次回复，实际 {len(completes)}"
        # 正常序列：THINKING → RESPONDING → DONE（无回注循环）
        seq = [s for s in states if s != engine.STATE_IDLE]
        assert seq[-2:] == [engine.STATE_RESPONDING, engine.STATE_DONE]

    def test_casual_chat_fast_path(self, monkeypatch):
        """纯聊天快速通道：无工具调用且无台账 → 直接回复不经闸。"""
        fake_llm = FakeLLMCaller([
            ("你好！有什么可以帮你？", None),
        ])
        fake_tools = FakeToolExecutor()
        engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)
        engine.task_ledger = []  # 无台账

        completes = _track_notify_complete(engine)
        engine.run(user_input="你好")

        assert engine.state == engine.STATE_DONE
        assert len(completes) == 1, "纯聊天应直接回复 1 次"
        # 无账但 tool_round==0 → 不触发 no-ledger 回注（直放）
        user_msgs = [m for m in engine.history if m.get("role") == "user"]
        assert not any("task_ledger" in m.get("content", "") for m in user_msgs)


class TestSafetyValve:
    """G2-2/L1：字段闸 deny 降本——缺字段单次记录即放行，死锁循环已退役

    票 L1 裁决：缺字段不再强制全上下文重跑（旧语义 deny 3 次降级 / 5 次强制放行），
    改为本轮放行 + 执法记录照留（goal_gate.deny mode=pass_with_note）。
    旧安全阀（3 次降级 / 5 次 forced_release）随循环语义一并退役。
    """

    def test_deny_stops_at_first_pass_with_note(self, monkeypatch):
        """L1：缺字段第 1 次即 pass_with_note 放行，无 deny 循环、无重跑。"""
        fake_llm = FakeLLMCaller([("已完成全部工作", None)])  # 只调 1 次 = 无重跑
        fake_tools = FakeToolExecutor()
        engine = _make_auto_engine(fake_llm, fake_tools, monkeypatch,
                                   [{"id": "1", "title": "任务", "status": "done"}], auto=True)
        for _ in range(4):
            engine._step()

        user_msgs = [m for m in engine.history if m.get("role") == "user"]
        deny_msgs = [m for m in user_msgs if "收工拒绝" in m.get("content", "")]
        assert deny_msgs == [], "L1：缺字段不再回注'收工拒绝'重跑指令"
        assert engine._ledger_field_deny_count == 1, "单次记录即止"
        assert fake_llm.call_count == 1, "不应重跑"

    def test_no_forced_release_loop_under_l1(self, monkeypatch):
        """L1：字段闸不再有 5 次 forced_release 循环——单次记录后终稿带补正指令放行。"""
        from core.event_bus import event_bus
        events = []
        original_write = event_bus.write

        def tracking_write(event_type, data):
            events.append((event_type, data))
            original_write(event_type, data)

        event_bus.write = tracking_write

        fake_llm = FakeLLMCaller([("已完成全部工作", None)])
        fake_tools = FakeToolExecutor()
        engine = _make_auto_engine(fake_llm, fake_tools, monkeypatch,
                                   [{"id": "1", "title": "任务", "status": "done"}], auto=True)

        completes = _track_notify_complete(engine)
        for _ in range(4):
            engine._step()

        # 不再有 forced_release 循环事件；只有 1 次 pass_with_note 记录
        forced = [e for e in events if e[0] == "goal_gate.forced_release"]
        assert forced == [], "L1：forced_release 循环已退役"
        notes = [e for e in events if e[0] == "goal_gate.deny"]
        assert len(notes) == 1
        assert notes[0][1]["mode"] == "pass_with_note"
        assert notes[0][1]["field_issues"] == [{"id": "1", "missing": ["verify", "evidence"]}]
        # 终稿带补正指令（本轮放行语义），且回复正常发出
        assert any("字段闸记录" in (m.get("content") or "") for m in engine.history
                   if m.get("role") == "assistant")
        assert any("本轮放行" in (m.get("content") or "") for m in engine.history
                   if m.get("role") == "assistant")
        assert len(completes) == 1, "记录后应直接放行发出回复"

    def test_auto_off_control_group(self, monkeypatch):
        """对照组：auto off（_auto_mode_getter 为 False）→ 字段闸整段跳过，不 deny。"""
        fake_llm = FakeLLMCaller([
            ("已完成全部工作", None),
        ])
        fake_tools = FakeToolExecutor()
        engine = _make_auto_engine(fake_llm, fake_tools, monkeypatch,
                                   [{"id": "1", "title": "任务", "status": "done"}], auto=False)

        completes = _track_notify_complete(engine)
        engine.run(user_input="干活")

        assert engine.state == engine.STATE_DONE
        assert engine._ledger_field_deny_count == 0, "auto off 不应 deny"
        assert len(completes) == 1

    def test_interrupt_unaffected(self, monkeypatch):
        """中断语义不受影响：_interrupt_event 置位 → 直接 ERROR（闸无关）。"""
        import threading
        fake_llm = FakeLLMCaller([("ok", None)])
        fake_tools = FakeToolExecutor()
        engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)

        ev = threading.Event()
        ev.set()  # 预先置位 → 主循环第一步即中断
        engine._interrupt_event = ev
        engine.run(user_input="干活")

        assert engine.state == engine.STATE_ERROR, "中断应走 ERROR 分支"
