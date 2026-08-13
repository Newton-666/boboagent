"""票 CORE-R2a（v2 软限制版）：台账改软引导，拆无账硬闸 专项测试

验收（票原文，v2 owner 终裁）：
1. 拆除无账硬闸：任何回合不再因为"没建账"被回注（含票Z v3 回注、票 L1 提醒、票Z 缝1 提醒）
2. 改软引导：系统提示词建账纪律改写（多步主动建账，简单问答直接回答）
3. 保留有账后的全部闸门：字段闸（verify/evidence）、补账检测、批量销账检测
4. 台账显示（📋 台账 段）只在真的有账时出现；无账回合收工回复禁止出现台账段

配套回归（tests/test_goal_gate.py）：
- TestNoLedgerSoftGate 类整体改写：工作回合/多轮/完成词无账 → 全部软放行零回注
- test_no_ledger_reminder_after_two_tool_rounds 改为断言零提醒
- tests/test_ticket_ledger_1.py test_no_ledger_reminder_injected_once 改为断言零回注
"""

from tests.test_engine_e2e import (
    FakeLLMCaller, FakeToolExecutor, _make_tool_call, _make_test_engine, _collect_states,
)


def _user_msgs(engine):
    return [m for m in engine.history if m.get("role") == "user"]


def _sys_msgs(engine):
    return [m for m in engine.history if m.get("role") == "system"]


def _asst_texts(engine):
    return [str(m.get("content", "")) for m in engine.history
            if m.get("role") == "assistant" and m.get("content") is not None]


def _capture_complete(engine):
    """包装 _notify 捕获 complete 事件 content（台账段/字段闸记录只进 complete 不进 history）"""
    original_notify = engine._notify
    captured = []

    def tracking_notify(event, data=None):
        if event == "complete" and data and data.get("content"):
            captured.append(data["content"])
        original_notify(event, data)

    engine._notify = tracking_notify
    return captured


class TestNoLedgerAnyRound:
    """任何回合（纯读/写类/多轮）无账 → 零回注零提醒直接收工"""

    def test_read_only_3_rounds_no_ledger_passes(self, monkeypatch):
        """纯读 3 轮无账 → 正常 DONE，无硬闸回注、无轻提醒"""
        fake_llm = FakeLLMCaller([
            (None, [_make_tool_call("c1", "echo", {"msg": "s1"})]),
            (None, [_make_tool_call("c2", "echo", {"msg": "s2"})]),
            (None, [_make_tool_call("c3", "echo", {"msg": "s3"})]),
            ("已查完，回答完毕", None),
        ])
        fake_tools = FakeToolExecutor({"echo": "ok"})
        engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)
        engine.task_ledger = []  # 明确无台账

        engine.run(user_input="帮我查点资料")

        assert engine.state == engine.STATE_DONE
        # 零硬闸回注：user 消息不含 task_ledger
        assert not any("task_ledger" in m.get("content", "") for m in _user_msgs(engine))
        # 零提醒：system 消息既无"未建台账"也无"建议建账"
        sys_joined = " ".join(m.get("content", "") for m in _sys_msgs(engine))
        assert "未建台账" not in sys_joined
        assert "建议建账" not in sys_joined
        # 无账回合回复禁止出现台账段
        assert not any("📋 台账" in c for c in _asst_texts(engine)), "无账回合不应出现台账段"

    def test_write_round_no_ledger_passes(self, monkeypatch):
        """写类工具（edit_file）1 轮无账 → R2a v2 也直接放行（原硬闸语义已拆）"""
        from core.event_bus import event_bus
        events = []
        original_write = event_bus.write

        def tracking_write(event_type, data):
            events.append((event_type, data))
            original_write(event_type, data)

        event_bus.write = tracking_write

        fake_llm = FakeLLMCaller([
            (None, [_make_tool_call("c1", "edit_file",
                                    {"file_path": "a.py", "old_string": "x", "new_string": "y"})]),
            ("好的", None),            # 中性收尾 → R2a v2 直接放行
        ])
        fake_tools = FakeToolExecutor({"edit_file": "ok"})
        engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)
        engine.task_ledger = []

        engine.run(user_input="改个文件")

        assert engine.state == engine.STATE_DONE
        # 零回注：user 消息不含 task_ledger
        assert not any("task_ledger" in m.get("content", "") for m in _user_msgs(engine))
        # 事件：task.no_ledger 落地，goal_gate.no_ledger_detected 不再触发
        no_ledger = [e for e in events if e[0] == "task.no_ledger"]
        assert len(no_ledger) >= 1, "应写 task.no_ledger 事件"
        detected = [e for e in events if e[0] == "goal_gate.no_ledger_detected"]
        assert len(detected) == 0, "R2a v2 不应再触发 goal_gate.no_ledger_detected"

    def test_multi_round_8_no_ledger_passes(self, monkeypatch):
        """8 轮无账 → 直接 DONE，无任何提醒（原票Z 缝1 轻提醒已拆）"""
        calls = [(None, [_make_tool_call(f"c{i}", "echo", {"msg": f"s{i}"})])
                 for i in range(1, 9)]
        fake_llm = FakeLLMCaller(calls + [("查完收工", None)])
        fake_tools = FakeToolExecutor({"echo": "ok"})
        engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)
        engine.task_ledger = []

        engine.run(user_input="翻很多资料")

        assert engine.state == engine.STATE_DONE, "多轮无账应直接收工"
        sys_joined = " ".join(m.get("content", "") for m in _sys_msgs(engine))
        assert "未建台账" not in sys_joined, "R2a v2 不应有建账提醒"
        assert "建议建账" not in sys_joined
        assert not any("task_ledger" in m.get("content", "") for m in _user_msgs(engine))


class TestVoluntaryLedgerGatesKept:
    """自愿建账后的闸门全部保留：字段闸照常工作"""

    def test_ledger_field_gate_still_active(self, monkeypatch):
        """AUTO 模式 + 有账但缺字段（老格式无 verify/evidence）→ 字段闸记录照常注入"""
        fake_llm = FakeLLMCaller([
            (None, [_make_tool_call("c1", "echo", {"msg": "s1"})]),
            ("弄完了", None),
        ])
        fake_tools = FakeToolExecutor({"echo": "ok"})
        engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)
        # 激活 AUTO MODE（票 O8-1：字段闸仅在 auto/office 激活，普通模式零影响）
        engine._auto_mode_getter = lambda: True
        # 自愿建账但老格式缺字段（verify/evidence）
        engine.task_ledger = [{"id": "1", "title": "t", "status": "done"}]
        captured = _capture_complete(engine)

        engine.run(user_input="干活")

        assert engine.state == engine.STATE_DONE
        joined = " ".join(captured)
        assert "字段闸记录" in joined, "AUTO 模式字段闸应照常记录（pass-with-note）"

    def test_ledger_summary_only_when_ledger_exists(self, monkeypatch):
        """写类施工回合有账 → 📋 台账 段出现；问答回合/无账 → 不出现（对照，票 R2b 语义）"""
        # 写类施工回合有账场景 → 显示台账段
        fake_llm = FakeLLMCaller([
            (None, [_make_tool_call("c1", "edit_file",
                                    {"file_path": "a.py", "old_string": "x", "new_string": "y"})]),
            ("弄完了", None),
        ])
        fake_tools = FakeToolExecutor({"edit_file": "ok"})
        engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)
        engine.task_ledger = [{"id": "1", "title": "t", "status": "done",
                               "verify": "v", "evidence": "e"}]
        captured = _capture_complete(engine)
        engine.run(user_input="改文件")
        assert engine.state == engine.STATE_DONE
        assert any("📋 台账" in c for c in captured), "写类施工回合有账 complete 应含台账段"

        # 问答回合（无写类工具）有账 → 不显示台账段（票 R2b：没账可交时不交账）
        fake_llm2 = FakeLLMCaller([
            (None, [_make_tool_call("c1", "echo", {"msg": "s1"})]),
            ("查完了", None),
        ])
        engine2 = _make_test_engine(fake_llm2, fake_tools, monkeypatch)
        engine2.task_ledger = [{"id": "1", "title": "t", "status": "done",
                                "verify": "v", "evidence": "e"}]
        captured2 = _capture_complete(engine2)
        engine2.run(user_input="查资料")
        assert engine2.state == engine2.STATE_DONE
        assert not any("📋 台账" in c for c in captured2), "问答回合 complete 不应含台账段"

        # 无账场景
        fake_llm3 = FakeLLMCaller([
            (None, [_make_tool_call("c1", "echo", {"msg": "s1"})]),
            ("弄完了", None),
        ])
        engine3 = _make_test_engine(fake_llm3, fake_tools, monkeypatch)
        engine3.task_ledger = []
        captured3 = _capture_complete(engine3)
        engine3.run(user_input="干活")
        assert engine3.state == engine3.STATE_DONE
        assert not any("📋 台账" in c for c in captured3), "无账 complete 不应含台账段"
