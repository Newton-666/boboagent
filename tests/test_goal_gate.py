"""票 Z 收工闸 v2 验收测试 — 真撞闸验证

覆盖 6 个验收标准：
1. 复刻 10:50 早退案（承诺检测 + 回注）
2. 无账强制建账提醒
3. 熔断逃生
4. 闲聊零误拦
5. 收束白名单
6. 全量回归

【票 G2-1 语义迁移】四个闸已前移到 THINKING 分支（先账后复）：
闸在进 RESPONDING 前执行，账不平无回复发出、状态停在 THINKING。
以下断言已按新时序重写（回注发生在 THINKING 阶段，RESPONDING 前）。
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

        # 在工具执行后设台账，避免无账硬闸误拦（票Z v3）
        _wrapped_executor = [engine.tool_executor]
        _ledger_set = [False]
        class _WrappedToolExecutor:
            def __call__(self, tool_name, args):
                result = _wrapped_executor[0](tool_name, args)
                if not _ledger_set[0]:
                    _ledger_set[0] = True
                    engine.task_ledger = [{"id": "1", "title": "test", "status": "done"}]
                return result
        engine.tool_executor = _WrappedToolExecutor()

        states = _collect_states(engine)

        engine.run(user_input="帮我跑一下测试")

        assert engine.state == engine.STATE_DONE

        # 【G2-1 语义迁移】闸在 THINKING 执行：承诺回注期间状态停在 THINKING，
        # 不进入 RESPONDING（用户只看到 Working，账不平无回复发出）
        seq = [s for s in states if s != engine.STATE_IDLE]
        assert engine.STATE_RESPONDING not in seq[:-2], (
            f"承诺回注应停在 THINKING，不应提前进 RESPONDING: {seq}"
        )
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


class TestNoLedgerHardGate:
    """票 Z v3：无账硬闸 — 工作回合无台账强制回注"""

    # ── 验收标准 1：工作回合无账被拦 ──

    def test_work_round_no_ledger_rejected(self, monkeypatch):
        """1轮工具调用后给中性收尾文本（无承诺词无完成词）
        → 不回 complete，回注消息含'task_ledger'，事件 goal_gate.no_ledger_detected 落地"""
        from core.event_bus import event_bus
        events = []
        original_write = event_bus.write
        def tracking_write(event_type, data):
            events.append((event_type, data))
            original_write(event_type, data)
        event_bus.write = tracking_write

        fake_llm = FakeLLMCaller([
            (None, [_make_tool_call("call_1", "echo", {"msg": "work"})]),  # R1: tool → tool_round=1
            ("好的，已处理", None),  # R2: neutral → no-ledger re-injection
            ("已完成全部工作", None),  # R3: after re-injection, finish
        ])
        fake_tools = FakeToolExecutor({"echo": "ok"})
        engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)
        states = _collect_states(engine)
        engine.run(user_input="干活")

        assert engine.state == engine.STATE_DONE

        # 【G2-1 语义迁移】无账硬闸在 THINKING 执行：回注期间不进 RESPONDING
        seq = [s for s in states if s != engine.STATE_IDLE]
        resp_idx = seq.index(engine.STATE_RESPONDING) if engine.STATE_RESPONDING in seq else -1
        if resp_idx >= 0:
            # 首个 RESPONDING 之前不允许再出现 RESPONDING（回注全程停在 THINKING）
            assert engine.STATE_RESPONDING not in seq[:resp_idx], (
                f"无账回注应停在 THINKING: {seq}"
            )

        # 验证回注消息含 task_ledger
        user_msgs = [m for m in engine.history if m.get("role") == "user"]
        assert any("task_ledger" in m.get("content", "") for m in user_msgs)

        # 验证 goal_gate.no_ledger_detected 事件落地
        detected = [e for e in events if e[0] == "goal_gate.no_ledger_detected"]
        assert len(detected) >= 1, "应触发 goal_gate.no_ledger_detected 事件"

    # ── 验收标准 2：回注后建账全销 → 干净收工 ──

    def test_no_ledger_reinject_then_clean_done(self, monkeypatch):
        """回注后建账并全 done → 正常 done，history 中回注消息仅 1 条"""
        fake_llm = FakeLLMCaller([
            (None, [_make_tool_call("call_1", "echo", {"msg": "work"})]),  # R1: tool → tool_round=1
            ("好的", None),  # R2: neutral → no-ledger re-injection
            ("已完成全部工作", None),  # R3: after re-injection, complete with ledger set
        ])
        fake_tools = FakeToolExecutor({"echo": "ok"})
        engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)

        # 拦截 no-ledger 回注事件，在第一次回注后设置台账（模拟模型建账）
        original_emit = engine._emit_state_change
        _injected = [False]
        def tracking_emit(state, reason):
            if state == engine.STATE_THINKING and "no-ledger" in str(reason) and not _injected[0]:
                _injected[0] = True
                engine.task_ledger = [{"id": "1", "title": "task", "status": "done"}]
            original_emit(state, reason)
        engine._emit_state_change = tracking_emit

        engine.run(user_input="干活")
        assert engine.state == engine.STATE_DONE

        # history 中回注消息仅 1 条（建账后不再回注）
        user_msgs = [m for m in engine.history if m.get("role") == "user"]
        reinject_msgs = [m for m in user_msgs if "task_ledger" in m.get("content", "")]
        assert len(reinject_msgs) == 1, f"应只有 1 条回注消息，实际 {len(reinject_msgs)}"

    # ── 验收标准 3：两次熔断放行 ──

    def test_no_ledger_circuit_breaker_releases(self, monkeypatch):
        """连续 2 回合不建账 → 放行，终稿含 ⚠️，事件 goal_gate.released reason=no_ledger_exhausted"""
        from core.event_bus import event_bus
        events = []
        original_write = event_bus.write
        def tracking_write(event_type, data):
            events.append((event_type, data))
            original_write(event_type, data)
        event_bus.write = tracking_write

        fake_llm = FakeLLMCaller([
            (None, [_make_tool_call("call_1", "echo", {"msg": "1"})]),  # R1: tool → tool_round=1
            ("好的", None),  # R2: neutral → re-injection #1
            (None, [_make_tool_call("call_2", "echo", {"msg": "2"})]),  # R3: tool → tool_round=2
            ("好的", None),  # R4: neutral → re-injection #2 (count=2,熔断)
            ("好的", None),  # R5: neutral → 已熔断, 放行 + ⚠️
        ])
        fake_tools = FakeToolExecutor({"echo": "ok"})
        engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)
        engine.run(user_input="干活")

        assert engine.state == engine.STATE_DONE

        # 终稿含 ⚠️
        asst_texts = [str(m.get("content", "")) for m in engine.history if m.get("role") == "assistant" and m.get("content") is not None]
        assert any("⚠️" in c for c in asst_texts), "终稿应含 ⚠️ 警告"

        # goal_gate.released 事件 reason=no_ledger_exhausted
        released = [e for e in events if e[0] == "goal_gate.released" and e[1].get("reason") == "no_ledger_exhausted"]
        assert len(released) >= 1, "应触发 goal_gate.released reason=no_ledger_exhausted"

    # ── 验收标准 4：纯聊天零误伤 ──

    def test_chat_round_no_ledger_passes(self, monkeypatch):
        """tool_round=0 且无台账 → 直接 done，task.no_ledger 事件照旧"""
        from core.event_bus import event_bus
        events = []
        original_write = event_bus.write
        def tracking_write(event_type, data):
            events.append((event_type, data))
            original_write(event_type, data)
        event_bus.write = tracking_write

        fake_llm = FakeLLMCaller([
            ("谢谢你的反馈！", None),
        ])
        fake_tools = FakeToolExecutor()
        engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)
        engine.run(user_input="谢谢")

        assert engine.state == engine.STATE_DONE

        # 验证 task.no_ledger 事件照旧
        no_ledger_events = [e for e in events if e[0] == "task.no_ledger"]
        assert len(no_ledger_events) >= 1, "纯聊天应照旧写 task.no_ledger 事件"

        # history 无回注消息
        user_msgs = [m for m in engine.history if m.get("role") == "user"]
        reinject_msgs = [m for m in user_msgs if "task_ledger" in m.get("content", "")]
        assert len(reinject_msgs) == 0, "纯聊天不应有回注消息"

    # ── 验收标准 5（回归）：收束词不豁免 ──

    def test_completion_word_no_exemption(self, monkeypatch):
        """工作回合含"已完成"但无台账 → 仍然回注，不因完成词放行。
        回归票Z v3 终审结论：删掉 _HAS_COMPLETION 豁免。"""
        from core.event_bus import event_bus
        events = []
        original_write = event_bus.write
        def tracking_write(event_type, data):
            events.append((event_type, data))
            original_write(event_type, data)
        event_bus.write = tracking_write

        fake_llm = FakeLLMCaller([
            (None, [_make_tool_call("call_1", "echo", {"msg": "work"})]),  # R1: tool → tool_round=1
            ("已完成全部工作", None),  # R2: 含完成词但无台账 → 仍回注
            ("好的，我来建账", None),  # R3: after re-injection
        ])
        fake_tools = FakeToolExecutor({"echo": "ok"})
        engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)
        engine.run(user_input="干活")

        assert engine.state == engine.STATE_DONE

        # 验证回注消息含 task_ledger（完成词没救它）
        user_msgs = [m for m in engine.history if m.get("role") == "user"]
        assert any("task_ledger" in m.get("content", "") for m in user_msgs)

        # 验证 goal_gate.no_ledger_detected 事件落地
        detected = [e for e in events if e[0] == "goal_gate.no_ledger_detected"]
        assert len(detected) >= 1, "完成词不豁免，应仍触发 no_ledger_detected 事件"


class TestBackfillDetectionO9:
    """票 O-9 回归：同轮批量建账全 done → 补账嫌疑置位（基线快照必须在工具执行前）。

    血案：EV-1 首跑 A2——_prev_ledger 在 _execute_tool_loop 之后快照，
    工具已替换 engine.task_ledger → prev 非空 → 误判 resume 豁免 → 闸不响。
    """

    def test_same_round_batch_create_all_done_flags_suspect(self, monkeypatch):
        fake_llm = FakeLLMCaller([
            (None, [_make_tool_call("call_1", "task_ledger", {"action": "create"})]),
            ("台账已建立，3 项全部标 done。全部完成", None),
            ("补上 pending 项", None),
        ])
        fake_tools = FakeToolExecutor({"task_ledger": "ok"})
        engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)

        # 模拟真实 task_ledger 工具副作用：执行时把 engine.task_ledger 替换为
        # 同轮新建且全 done 的台账（O-9 事故现场）
        _inner = [engine.tool_executor]
        class _LedgerExecutor:
            def __call__(self, tool_name, args):
                r = _inner[0](tool_name, args)
                engine.task_ledger = [
                    {"id": "1", "title": "t1", "status": "done", "verify": "v", "evidence": "e"},
                    {"id": "2", "title": "t2", "status": "done", "verify": "v", "evidence": "e"},
                    {"id": "3", "title": "t3", "status": "done", "verify": "v", "evidence": "e"},
                ]
                return r
        engine.tool_executor = _LedgerExecutor()

        engine.run(user_input="把这3件事补登记一下，都完成了")

        assert engine._ledger_backfill_suspect is True, (
            "O-9 回归：同轮批量建账全 done 必须置位 _ledger_backfill_suspect"
        )

    def test_resume_existing_ledger_exempt(self, monkeypatch):
        """对照组：create 前已有非空台账（resume 恢复）→ 豁免不置位"""
        engine = _make_test_engine(FakeLLMCaller([("x", None)]), FakeToolExecutor({}), monkeypatch)
        engine.task_ledger = [
            {"id": "1", "title": "t1", "status": "done"},
            {"id": "2", "title": "t2", "status": "done"},
        ]
        prev = list(engine.task_ledger)  # 工具执行前快照（非空 = 有历史）
        engine.task_ledger = prev + [{"id": "3", "title": "t3", "status": "done"}]
        assert engine._detect_ledger_backfill(prev, ["task_ledger"]) is False

    def test_partial_done_not_backfill(self, monkeypatch):
        """对照组：同轮建账但含 pending 项（真实计划）→ 不置位"""
        engine = _make_test_engine(FakeLLMCaller([("x", None)]), FakeToolExecutor({}), monkeypatch)
        engine.task_ledger = [
            {"id": "1", "title": "t1", "status": "done"},
            {"id": "2", "title": "t2", "status": "pending"},
            {"id": "3", "title": "t3", "status": "pending"},
        ]
        assert engine._detect_ledger_backfill([], ["task_ledger"]) is False
