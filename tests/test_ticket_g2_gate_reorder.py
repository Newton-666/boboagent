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
    """G2-2：字段闸死锁安全阀（auto 缺字段 deny 3 次降级 / 5 次强制放行）"""

    def test_deny_3_degrades_to_handoff(self, monkeypatch):
        """连续 deny 第 3 次：回注指令降级（含"转 pending 交接"提示）。"""
        fake_llm = FakeLLMCaller([
            ("已完成全部工作", None),  # deny #1
            ("已完成全部工作", None),  # deny #2
            ("已完成全部工作", None),  # deny #3 → 降级文案
        ])
        fake_tools = FakeToolExecutor()
        engine = _make_auto_engine(fake_llm, fake_tools, monkeypatch,
                                   [{"id": "1", "title": "任务", "status": "done"}], auto=True)
        # 4 步：第 1 步 IDLE→THINKING（不消耗 deny），后 3 步各 deny 1 次
        for _ in range(4):
            engine._step()

        user_msgs = [m for m in engine.history if m.get("role") == "user"]
        deny_msgs = [m for m in user_msgs if "收工拒绝" in m.get("content", "")]
        assert len(deny_msgs) == 3
        # 第 3 次 deny 含降级提示（转交接）
        assert "转 pending 交接" in deny_msgs[-1]["content"], \
            f"第 3 次 deny 应降级为交接提示，实际: {deny_msgs[-1]['content']}"
        assert engine._ledger_field_deny_count == 3

    def test_deny_5_force_release_with_audit(self, monkeypatch):
        """连续 deny 第 5 次：强制放行 + goal_gate.forced_release 审计事件 + ⚠️ 遗言。"""
        from core.event_bus import event_bus
        events = []
        original_write = event_bus.write

        def tracking_write(event_type, data):
            events.append((event_type, data))
            original_write(event_type, data)

        event_bus.write = tracking_write

        fake_llm = FakeLLMCaller([
            ("已完成全部工作", None),  # deny #1
            ("已完成全部工作", None),  # deny #2
            ("已完成全部工作", None),  # deny #3
            ("已完成全部工作", None),  # deny #4
            ("已完成全部工作", None),  # deny #5 → 强制放行
        ])
        fake_tools = FakeToolExecutor()
        engine = _make_auto_engine(fake_llm, fake_tools, monkeypatch,
                                   [{"id": "1", "title": "任务", "status": "done"}], auto=True)

        completes = _track_notify_complete(engine)
        # 7 步：step1 IDLE→THINKING；step2-6 为 deny #1-4 + 第 5 次强制放行
        # （放行后 state=RESPONDING）；step7 执行 RESPONDING 分支落 history + 发回复
        for _ in range(7):
            engine._step()

        # 强制放行审计事件落地
        forced = [e for e in events if e[0] == "goal_gate.forced_release"]
        assert len(forced) == 1, f"应触发 1 次 forced_release，实际 {len(forced)}"
        assert forced[0][1]["deny_count"] == 5
        assert forced[0][1]["field_issues"] == [{"id": "1", "missing": ["verify", "evidence"]}]
        # 终稿含 ⚠️ 审计遗言
        assert any("强制放行" in (m.get("content") or "") for m in engine.history
                   if m.get("role") == "assistant")
        # 放行后发出回复（闸过）
        assert len(completes) == 1, f"第 5 次放行应发出回复，实际 {len(completes)}"

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
