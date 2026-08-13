"""TICKET-O8 验收测试：office 模式默认启用收工闸 + 事后补账检测。

覆盖票 O8-1/O8-2/O8-3 全部验收：
  1. office on（无 auto）→ 收工闸激活：缺字段 deny（reason=ledger_field_missing）
     + OFFICE MODE 文案；全合规放行
  2. office on + 补账嫌疑（批量创建即全 done）→ deny（reason=ledger_backfill）
     + history 指令要求列出下一步真实待办
  3. resume 豁免：create 前已有非空台账（有历史轮次）→ 不置补账嫌疑
  4. 普通模式对照组（auto off + office off）→ 整段物理跳过，零 deny 零审计
  5. 判定内核 _detect_ledger_backfill 单测（prev 空 + >=2 项 + done 占比 >=80%）
  6. auto 模式回归：原有字段闸语义不变（AUTO MODE 文案保留）
"""

import pytest

from tests.test_engine_e2e import (
    FakeLLMCaller, FakeToolExecutor, _make_test_engine,
)
from tests.test_ticket_c_ledger_gate import _track_events


def _make_engine(fake_llm, fake_tools, monkeypatch, ledger=None, auto=False, office_on=False):
    """构造 engine：设台账 + auto/office 会话级开关。"""
    engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)
    if ledger is not None:
        engine.task_ledger = ledger
    engine._auto_mode_getter = (lambda: True) if auto else (lambda: False)
    monkeypatch.setattr("bobo_tui_gateway.server.get_office_on", lambda sid: office_on)
    return engine


# ── 判定内核单测（票 O8-2 检测逻辑） ──

class TestDetectLedgerBackfill:
    def _eng(self, monkeypatch, ledger):
        engine = _make_test_engine(FakeLLMCaller([("ok", None)]), FakeToolExecutor(), monkeypatch)
        engine.task_ledger = ledger
        return engine

    def test_batch_create_all_done_detected(self, monkeypatch):
        """prev 空 + task_ledger + 3 项全 done → 补账嫌疑"""
        engine = self._eng(monkeypatch, [
            {"id": "1", "title": "a", "status": "done"},
            {"id": "2", "title": "b", "status": "done"},
            {"id": "3", "title": "c", "status": "done"},
        ])
        assert engine._detect_ledger_backfill([], ["task_ledger"]) is True

    def test_two_items_all_done_detected(self, monkeypatch):
        """>=2 项阈值：2 项全 done → 嫌疑"""
        engine = self._eng(monkeypatch, [
            {"id": "1", "title": "a", "status": "done"},
            {"id": "2", "title": "b", "status": "done"},
        ])
        assert engine._detect_ledger_backfill([], ["task_ledger"]) is True

    def test_eighty_percent_done_detected(self, monkeypatch):
        """大部阈值：5 项 4 done（80%）→ 嫌疑"""
        engine = self._eng(monkeypatch, [
            {"id": str(i), "title": f"t{i}", "status": "done"} for i in range(4)
        ] + [{"id": "5", "title": "t5", "status": "pending"}])
        assert engine._detect_ledger_backfill([], ["task_ledger"]) is True

    def test_sixty_percent_done_not_detected(self, monkeypatch):
        """5 项 3 done（60%）< 80% → 非补账"""
        engine = self._eng(monkeypatch, [
            {"id": str(i), "title": f"t{i}", "status": "done"} for i in range(3)
        ] + [{"id": str(i), "title": f"t{i}", "status": "pending"} for i in range(3, 5)])
        assert engine._detect_ledger_backfill([], ["task_ledger"]) is False

    def test_no_ledger_tool_not_detected(self, monkeypatch):
        """工具轮不含 task_ledger → 非补账"""
        engine = self._eng(monkeypatch, [
            {"id": "1", "title": "a", "status": "done"},
            {"id": "2", "title": "b", "status": "done"},
        ])
        assert engine._detect_ledger_backfill([], ["edit_file"]) is False

    def test_resume_prev_nonempty_exempt(self, monkeypatch):
        """resume 豁免：create 前已有非空台账（有历史轮次）→ 非补账"""
        engine = self._eng(monkeypatch, [
            {"id": "1", "title": "a", "status": "done"},
            {"id": "2", "title": "b", "status": "done"},
        ])
        prev = [{"id": "old", "title": "历史项", "status": "in_progress"}]
        assert engine._detect_ledger_backfill(prev, ["task_ledger"]) is False

    def test_single_item_not_detected(self, monkeypatch):
        """单项台账（<2）不算批量补账"""
        engine = self._eng(monkeypatch, [
            {"id": "1", "title": "a", "status": "done"},
        ])
        assert engine._detect_ledger_backfill([], ["task_ledger"]) is False


# ── 端到端：office on（无 auto）闸生效（票 O8-1） ──

class TestOfficeFieldGate:
    def test_office_on_missing_field_pass_with_note(self, monkeypatch):
        """票 L1（deny 降本）：office on + 缺字段 → 本轮放行 + 执法记录照留。

        原票 O8-1 语义：缺字段 deny 强制全上下文重跑一轮；
        票 L1 裁决：精简补正指令本轮放行 + goal_gate.deny 执法记录，不再重跑。
        """
        events = _track_events()
        fake_llm = FakeLLMCaller([("已完成全部工作", None)])
        fake_tools = FakeToolExecutor()
        engine = _make_engine(fake_llm, fake_tools, monkeypatch, [
            {"id": "1", "title": "a", "status": "done"},  # done 缺 evidence
        ], auto=False, office_on=True)
        final_output = [""]
        engine.callback = (lambda et, d: final_output.__setitem__(0, d.get("content", ""))
                           if et == "complete" else None)

        engine.run(user_input="干活")

        assert engine.state == engine.STATE_DONE
        # 执法记录照留：goal_gate.deny（reason=ledger_field_missing, mode=pass_with_note）
        denies = [e for e in events if e[0] == "goal_gate.deny"]
        assert len(denies) == 1
        assert denies[0][1]["reason"] == "ledger_field_missing"
        assert denies[0][1]["mode"] == "pass_with_note"
        # 不再强制全上下文重跑：无"收工拒绝"user 回注，LLM 只调 1 次
        assert fake_llm.call_count == 1
        user_msgs = [m for m in engine.history if m.get("role") == "user"]
        deny_msgs = [m for m in user_msgs if "收工拒绝" in m.get("content", "")]
        assert deny_msgs == []
        # 终稿带 OFFICE MODE 补正指令（本轮放行语义）
        assert "OFFICE MODE 字段闸记录" in final_output[0]
        assert "本轮放行" in final_output[0]

    def test_office_on_compliant_passes(self, monkeypatch):
        """验收 2：office on + 全字段合规 → 直接放行，无 deny"""
        events = _track_events()
        fake_llm = FakeLLMCaller([("已完成全部工作", None)])
        fake_tools = FakeToolExecutor()
        engine = _make_engine(fake_llm, fake_tools, monkeypatch, [
            {"id": "1", "title": "a", "status": "done", "verify": "跑测试", "evidence": "全过"},
        ], auto=False, office_on=True)

        engine.run(user_input="干活")

        assert engine.state == engine.STATE_DONE
        denies = [e for e in events if e[0] == "goal_gate.deny"]
        assert denies == []


# ── 端到端：office on 补账 deny（票 O8-2） ──

class TestOfficeBackfillGate:
    def test_backfill_denied_with_instruction(self, monkeypatch):
        """验收 3：office on + 补账嫌疑 → deny（reason=ledger_backfill）+ 指令要求列出真实待办"""
        events = _track_events()
        fake_llm = FakeLLMCaller([
            ("已完成全部工作", None),  # R1 → deny（补账）
            ("已完成全部工作", None),  # R2 → 钩子已修正 → 放行
        ])
        fake_tools = FakeToolExecutor()
        engine = _make_engine(fake_llm, fake_tools, monkeypatch, [
            {"id": "1", "title": "a", "status": "done", "verify": "v1", "evidence": "e1"},
            {"id": "2", "title": "b", "status": "done", "verify": "v2", "evidence": "e2"},
        ], auto=False, office_on=True)
        engine._ledger_backfill_suspect = True  # 模拟检测已置位（工具轮批量创建即全 done）

        original_emit = engine._emit_state_change
        _denies = [0]

        def tracking_emit(state, reason):
            if state == engine.STATE_THINKING and "ledger backfill deny" in str(reason):
                _denies[0] += 1
                if _denies[0] == 1:
                    # agent 修正：列出真实待办（suspect 清除）
                    engine._ledger_backfill_suspect = False
            original_emit(state, reason)

        engine._emit_state_change = tracking_emit
        engine.run(user_input="干活")

        assert engine.state == engine.STATE_DONE
        denies = [e for e in events if e[0] == "goal_gate.deny"]
        assert len(denies) == 1
        assert denies[0][1]["reason"] == "ledger_backfill"
        user_msgs = [m for m in engine.history if m.get("role") == "user"]
        deny_msgs = [m for m in user_msgs if "补账检测" in m.get("content", "")]
        assert len(deny_msgs) == 1
        assert "下一步真实待办" in deny_msgs[0]["content"]


# ── 普通模式对照组 ──

class TestNormalModeControl:
    def test_normal_mode_skipped_zero_impact(self, monkeypatch):
        """验收 4：auto off + office off（普通模式）→ 整段物理跳过，零 deny 零审计"""
        events = _track_events()
        fake_llm = FakeLLMCaller([("已完成全部工作", None)])
        fake_tools = FakeToolExecutor()
        engine = _make_engine(fake_llm, fake_tools, monkeypatch, [
            {"id": "1", "title": "a", "status": "done"},  # 老格式：缺 verify/evidence
        ], auto=False, office_on=False)

        engine.run(user_input="干活")

        assert engine.state == engine.STATE_DONE
        denies = [e for e in events if e[0] == "goal_gate.deny"]
        assert denies == [], "普通模式不应触发任何 deny"
        backfills = [e for e in events if e[0] == "ledger.backfill_detected"]
        assert backfills == []
        assert engine._ledger_field_deny_count == 0


# ── auto 模式回归 ──

class TestAutoModeRegression:
    def test_auto_mode_label_kept_in_note(self, monkeypatch):
        """票 L1：auto on 缺字段 → AUTO MODE 文案保留（本轮放行补正指令）。"""
        events = _track_events()
        fake_llm = FakeLLMCaller([("已完成全部工作", None)])
        fake_tools = FakeToolExecutor()
        engine = _make_engine(fake_llm, fake_tools, monkeypatch, [
            {"id": "1", "title": "a", "status": "done"},  # done 缺 evidence
        ], auto=True, office_on=False)
        final_output = [""]
        engine.callback = (lambda et, d: final_output.__setitem__(0, d.get("content", ""))
                           if et == "complete" else None)

        engine.run(user_input="干活")

        assert engine.state == engine.STATE_DONE
        # 执法记录照留 + AUTO MODE 文案（票 C 标签语义保留）
        denies = [e for e in events if e[0] == "goal_gate.deny"]
        assert len(denies) == 1
        assert denies[0][1]["reason"] == "ledger_field_missing"
        assert denies[0][1]["mode"] == "pass_with_note"
        assert "AUTO MODE 字段闸记录" in final_output[0]
        assert "本轮放行" in final_output[0]
        # 不再强制重跑：LLM 只调 1 次
        assert fake_llm.call_count == 1
