"""票 CORE-R2b：答复质量闸（先答问题再交账）专项测试

验收（票原文）：
1. 台账腔回复（只有清单无实质答复）被打回一次后给出实质答复
2. 问答回合（无写类工具）回复禁止出现"台账: x/x done"段——没账可交时不交账
3. 思考落纸：thinking 有分析结论但回复过短 → 打回一次要求充实答复
4. 打回每回合至多一次防死循环；写类施工回合豁免（只加闸不松闸）
"""

from tests.test_engine_e2e import (
    FakeLLMCaller, FakeToolExecutor, _make_tool_call, _make_test_engine,
)


def _user_msgs(engine):
    return [m for m in engine.history if m.get("role") == "user"]


def _capture_complete(engine):
    """包装 _notify 捕获 complete 事件 content"""
    original_notify = engine._notify
    captured = []

    def tracking_notify(event, data=None):
        if event == "complete" and data and data.get("content"):
            captured.append(data["content"])
        original_notify(event, data)

    engine._notify = tracking_notify
    return captured


class TestReplyQualityGate:
    """台账腔回复 → 打回一次 → 实质答复"""

    def test_ledgerish_reply_rejected_once_then_substantive(self, monkeypatch):
        """第一轮台账腔回复 → 打回；第二轮实质答复 → DONE"""
        fake_llm = FakeLLMCaller([
            (None, [_make_tool_call("c1", "echo", {"msg": "资料"})]),      # R1: tool
            ("📋 台账: 1/1 done\n- 完成项：查了资料\n- 待人工执行清单：无", None),  # R2: 台账腔 → 打回
            ("查完了。关于你的问题：核心结论是 X，依据是 Y，建议 Z。", None),      # R3: 实质答复
        ])
        fake_tools = FakeToolExecutor({"echo": "ok"})
        engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)
        engine.run(user_input="帮我查资料并回答 X 的问题")

        assert engine.state == engine.STATE_DONE
        # 打回一次：user 消息含答复质量回注
        user_msgs = _user_msgs(engine)
        quality_reinjects = [m for m in user_msgs if "没有直接回答" in m.get("content", "")]
        assert len(quality_reinjects) == 1, f"应恰好打回 1 次，实际 {len(quality_reinjects)}"
        # 终稿是实质答复（非台账腔）
        asst_texts = [str(m.get("content", "")) for m in engine.history
                      if m.get("role") == "assistant" and m.get("content") is not None]
        assert any("核心结论" in c for c in asst_texts), "终稿应为实质答复"

    def test_reinject_at_most_once(self, monkeypatch):
        """连续两次台账腔回复 → 只打回一次，第二次放行（防死循环）"""
        fake_llm = FakeLLMCaller([
            (None, [_make_tool_call("c1", "echo", {"msg": "资料"})]),
            ("📋 台账: 0/1 done\n- 完成项：无", None),   # 台账腔 #1 → 打回
            ("📋 台账: 1/1 done\n- 完成项：还是无", None),  # 台账腔 #2 → 已打回过，放行
        ])
        fake_tools = FakeToolExecutor({"echo": "ok"})
        engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)
        engine.run(user_input="查资料")

        assert engine.state == engine.STATE_DONE
        quality_reinjects = [m for m in _user_msgs(engine) if "没有直接回答" in m.get("content", "")]
        assert len(quality_reinjects) == 1, f"至多打回 1 次，实际 {len(quality_reinjects)}"

    def test_thinking_not_landed_rejected(self, monkeypatch):
        """thinking 有实质分析（≥60 字）但回复过短（<80 字）→ 打回一次"""
        _long_thinking = ("分析：用户问的是 X 问题。核心分三点：第一 Y，第二 Z，第三 W。"
                          "结论应落在 A 上并给出依据，同时提示下一步。"
                          "补充：需要先校验数据源，再交叉验证 B 与 C 的依赖关系，避免遗漏关键前提。")  # >60 字
        fake_llm = FakeLLMCaller([
            (None, [_make_tool_call("c1", "echo", {"msg": "资料"})]),
            # reasoning 在响应顶层（engine 读 response["reasoning"]）
            {"choices": [{"message": {"content": "好的"}}],
             "reasoning": _long_thinking, "usage": {}},  # 思考长回复短 → 打回
            ("查完了。核心结论是 A，依据是 Y/Z/W，建议按第一步执行。", None),  # 实质答复
        ])
        fake_tools = FakeToolExecutor({"echo": "ok"})
        engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)
        engine.run(user_input="查资料回答 X")

        assert engine.state == engine.STATE_DONE
        quality_reinjects = [m for m in _user_msgs(engine) if "没有直接回答" in m.get("content", "")]
        assert len(quality_reinjects) == 1, f"思考未落纸应打回 1 次，实际 {len(quality_reinjects)}"

    def test_write_round_exempt(self, monkeypatch):
        """写类施工回合台账腔回复 → 豁免不被打回（施工收尾以交账为主）"""
        fake_llm = FakeLLMCaller([
            (None, [_make_tool_call("c1", "edit_file",
                                    {"file_path": "a.py", "old_string": "x", "new_string": "y"})]),
            ("📋 台账: 1/1 done\n- 完成项：改了 a.py", None),  # 台账腔但写类回合 → 豁免
        ])
        fake_tools = FakeToolExecutor({"edit_file": "ok"})
        engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)
        engine.run(user_input="改文件")

        assert engine.state == engine.STATE_DONE
        quality_reinjects = [m for m in _user_msgs(engine) if "没有直接回答" in m.get("content", "")]
        assert len(quality_reinjects) == 0, "写类施工回合应豁免答复质量闸"


class TestQaRoundNoLedgerSummary:
    """问答回合（无写类工具）回复禁止出现台账段"""

    def test_qa_round_with_ledger_no_summary(self, monkeypatch):
        """问答回合有账 → complete 不含'📋 台账'段（没账可交时不交账）"""
        fake_llm = FakeLLMCaller([
            (None, [_make_tool_call("c1", "echo", {"msg": "资料"})]),
            ("查完了，直接回答你的问题：结论是 X。", None),
        ])
        fake_tools = FakeToolExecutor({"echo": "ok"})
        engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)
        engine.task_ledger = [{"id": "1", "title": "t", "status": "done",
                               "verify": "v", "evidence": "e"}]
        captured = _capture_complete(engine)
        engine.run(user_input="查资料回答 X")

        assert engine.state == engine.STATE_DONE
        assert not any("📋 台账" in c for c in captured), "问答回合 complete 不应含台账段"
