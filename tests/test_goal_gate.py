"""票 Z 收工闸 v2 验收测试 — 真撞闸验证

覆盖 6 个验收标准：
1. 复刻 10:50 早退案（承诺检测 + 回注）
2. 无账强制建账提醒
3. 熔断逃生
4. 闲聊零误拦
5. 收束白名单
6. 全量回归
"""

import pytest

from tests.test_engine_e2e import (
    FakeLLMCaller, FakeToolExecutor, _make_tool_call, _make_test_engine, _collect_states,
)


class TestGoalGate:
    """收工闸 v2 验收 — 缝2 承诺检测闸 + 缝1 无账提醒"""

    # ── 验收标准 1：复刻 10:50 早退案 ──

    def test_promise_detection_early_exit(self, monkeypatch):
        """10:50 案：FakeLLM 第一轮说"现在跑测试"（无工具调用，无台账）
        → 承诺检测闸命中 → 回注 → 第二轮真跑 → 才 DONE"""
        fake_llm = FakeLLMCaller([
            # 第 1 轮：说"现在跑测试"但不调工具（10:50 早退模式）
            ("现在跑测试", None),
            # 第 2 轮：回注后真跑
            (None, [_make_tool_call("call_1", "echo", {"msg": "tests passed"})]),
            # 第 3 轮：结果回来，报告完成
            ("测试通过，全部完成", None),
        ])
        fake_tools = FakeToolExecutor({
            "echo": "all tests passed",
        })
        engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)
        states = _collect_states(engine)

        engine.run(user_input="帮我跑一下测试")

        assert engine.state == engine.STATE_DONE

        # 验证承诺检测触发 → 回注（第 1 轮被拦截，所以 LLM 被多调用一次）
        # 正常流程 2 轮，回注后变 3 轮
        assert fake_llm.call_count == 3

        # 验证回注消息在 history 中
        user_msgs = [m for m in engine.history if m.get("role") == "user"]
        assert any("未完成的承诺" in m.get("content", "") for m in user_msgs)

        # 验证最终 history 包含工具执行结果
        tool_msgs = [m for m in engine.history if m.get("role") == "tool"]
        assert len(tool_msgs) >= 1

    def test_promise_detection_then_second_finishes(self, monkeypatch):
        """承诺被拦后，第二轮正常完成"""
        fake_llm = FakeLLMCaller([
            ("接下来我会继续处理", None),
            ("已完成所有修改", None),
        ])
        fake_tools = FakeToolExecutor()
        engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)
        engine.run(user_input="改一下配置")

        assert engine.state == engine.STATE_DONE
        # 第 1 轮被承诺检测拦 → 回注 → 第 2 轮"已完成"不被拦 → DONE
        assert fake_llm.call_count == 2

    # ── 验收标准 2：无账强制建账 ──

    def test_no_ledger_reminder_after_two_tool_rounds(self, monkeypatch):
        """3 个工具轮无台账 → history 中出现建账提醒"""
        fake_llm = FakeLLMCaller([
            (None, [_make_tool_call("call_1", "echo", {"msg": "step1"})]),
            (None, [_make_tool_call("call_2", "echo", {"msg": "step2"})]),
            (None, [_make_tool_call("call_3", "echo", {"msg": "step3"})]),
            ("done", None),
        ])
        fake_tools = FakeToolExecutor({
            "echo": "ok",
        })
        engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)
        engine.task_ledger = []  # 明确无台账

        engine.run(user_input="做一系列操作")

        assert engine.state == engine.STATE_DONE

        # 验证历史中有系统建账提醒
        sys_msgs = [m for m in engine.history if m.get("role") == "system"]
        reminder_found = any("未建台账" in m.get("content", "") for m in sys_msgs)
        assert reminder_found, "应出现建账提醒但未找到"

    # ── 验收标准 3：熔断逃生 ──

    def test_promise_circuit_breaker_releases(self, monkeypatch):
        """连续承诺不兑现 → 第 2 次回注后放行 + ⚠️ + goal_gate.released 事件"""
        from core.event_bus import event_bus
        events = []
        original_write = event_bus.write
        def tracking_write(event_type, data):
            events.append((event_type, data))
            original_write(event_type, data)
        event_bus.write = tracking_write

        fake_llm = FakeLLMCaller([
            ("接下来我会继续处理", None),  # 第 1 轮 → 承诺检测命中 → 回注 #1
            ("稍后我将执行测试", None),    # 第 2 轮 → 承诺检测命中 → 回注 #2（熔断临界）
            ("一会我会跑一下", None),      # 第 3 轮 → 承诺检测命中但已熔断 → 放行 + ⚠️
        ])
        fake_tools = FakeToolExecutor()
        engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)

        engine.run(user_input="执行这个任务")

        assert engine.state == engine.STATE_DONE

        # 验证 ⚠️ 警告出现在终稿
        asst_msgs = [m for m in engine.history if m.get("role") == "assistant"]
        assert any("⚠️" in m.get("content", "") for m in asst_msgs)

        # 验证 goal_gate.released 事件被写入
        released = [e for e in events if e[0] == "goal_gate.released"]
        assert len(released) >= 1, "应触发 goal_gate.released 事件"

        # 验证 goal_gate.promise_detected 事件被写入
        detected = [e for e in events if e[0] == "goal_gate.promise_detected"]
        assert len(detected) >= 1, "应触发 goal_gate.promise_detected 事件"

    # ── 验收标准 4：闲聊零误拦 ──

    def test_casual_chat_passes_through(self, monkeypatch):
        """"谢谢"回合直接 DONE，无闸触发"""
        fake_llm = FakeLLMCaller([
            ("谢谢你的反馈！", None),
        ])
        fake_tools = FakeToolExecutor()
        engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)

        states = _collect_states(engine)
        engine.run(user_input="谢谢")

        assert engine.state == engine.STATE_DONE

        # 正常单轮：IDLE → THINKING → RESPONDING → DONE
        seq = [s for s in states if s != engine.STATE_IDLE]
        assert seq == [
            engine.STATE_THINKING,
            engine.STATE_RESPONDING,
            engine.STATE_DONE,
        ], f"闲聊被误拦: {seq}"

    # ── 验收标准 5：收束白名单 ──

    def test_completion_whitelist_bypasses_promise_gate(self, monkeypatch):
        """"测试已全部完成，明天可以继续优化"（承诺词+收束词并存）→ 放行"""
        fake_llm = FakeLLMCaller([
            ("测试已全部完成，明天可以继续优化", None),
        ])
        fake_tools = FakeToolExecutor()
        engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)

        engine.run(user_input="跑测试")

        assert engine.state == engine.STATE_DONE
        assert fake_llm.call_count == 1  # 未回注

    def test_completion_whitelist_variants(self, monkeypatch):
        """各种收束词均通过"""
        for suffix in ["", "，明天继续"]:
            for word in ["已完成", "全部完成", "测试通过", "已交付"]:
                fake_llm = FakeLLMCaller([
                    (f"{word}{suffix}", None),
                ])
                fake_tools = FakeToolExecutor()
                engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)
                engine.run(user_input="干活")
                assert engine.state == engine.STATE_DONE
                assert fake_llm.call_count == 1, f"收束词 '{word}' 被误拦"

    # ── 验收标准 R1：融断器不动 ──

    def test_circuit_breaker_hard_limit(self, monkeypatch):
        """即使回注路径连续 3 次，计数不超过 2（硬编码熔断）"""
        from core.event_bus import event_bus
        events = []
        original_write = event_bus.write
        def tracking_write(event_type, data):
            events.append((event_type, data))
            original_write(event_type, data)
        event_bus.write = tracking_write

        # 建台账让 ledger gate 也触发
        fake_llm = FakeLLMCaller([
            ("稍后我会执行", None),         # 承诺检测回注 #1
            ("接下来我将继续", None),       # 承诺检测回注 #2
            ("一会我会处理", None),         # 熔断放行
            ("done", None),
        ])
        fake_tools = FakeToolExecutor()
        engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)
        engine.task_ledger = [{"id": "1", "title": "task", "status": "pending"}]

        engine.run(user_input="干活")

        assert engine.state == engine.STATE_DONE
        # 熔断事件必须有
        released = [e for e in events if e[0] == "goal_gate.released"]
        assert len(released) >= 1

        # 验证 engine 内部的 _ledger_reinject_count 在熔断后保持 ≤2
        #（测试结束后 engine 还存在，我们可以检查）
        assert engine._ledger_reinject_count <= 2
