"""TICKET-C 验收测试：台账字段化 + 收工闸 auto 硬拦。

覆盖票 C-1a/C-1b/C-1c 全部验收（含两项 owner 裁决）：
  1. auto on + 全字段合规 → 收工放行，行为与原链路一致
  2. auto on + 缺 verify → deny 收工 + 审计明细 + 连续 deny 无熔断（裁决 2）
  3. auto on + done 缺 evidence → deny；补齐 evidence 后放行
  4. auto off（普通模式）+ 缺字段 → 收工行为与施工前一致（零影响铁律对照组）
  5. 老格式台账（无新字段）在 auto 下 → 按缺字段硬拦（裁决 1，无迁移豁免）
  6. 审计事件字段齐全（type/sid/field_issues 明细）
  7. 判定内核 _ledger_field_issues 单测（单元级，不依赖端到端）
  8. 工具 schema 载体：verify/evidence 为可选字段，execute 语义零变化
"""

import json

import pytest

from tests.test_engine_e2e import (
    FakeLLMCaller, FakeToolExecutor, _make_tool_call, _make_test_engine,
)


def _track_events():
    """包装 event_bus.write 收集事件，返回 (engine, events) 前先挂好。"""
    from core.event_bus import event_bus
    events = []
    original_write = event_bus.write

    def tracking_write(event_type, data):
        events.append((event_type, data))
        original_write(event_type, data)

    event_bus.write = tracking_write
    return events


def _make_auto_engine(fake_llm, fake_tools, monkeypatch, ledger, auto=True):
    """构造 engine：设台账 + 开/关 auto_mode_getter。"""
    engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)
    engine.task_ledger = ledger
    engine._auto_mode_getter = (lambda: True) if auto else (lambda: False)
    return engine


# ── 判定内核单测（单元级） ──

class TestLedgerFieldIssues:
    def test_all_compliant_empty_issues(self, monkeypatch):
        engine = _make_test_engine(FakeLLMCaller([("ok", None)]), FakeToolExecutor(), monkeypatch)
        engine.task_ledger = [
            {"id": "1", "title": "a", "status": "done", "verify": "跑测试", "evidence": "1815 passed"},
            {"id": "2", "title": "b", "status": "pending", "verify": "写代码"},
        ]
        assert engine._ledger_field_issues() == []

    def test_missing_verify_reported(self, monkeypatch):
        engine = _make_test_engine(FakeLLMCaller([("ok", None)]), FakeToolExecutor(), monkeypatch)
        engine.task_ledger = [{"id": "1", "title": "a", "status": "pending"}]
        issues = engine._ledger_field_issues()
        assert len(issues) == 1
        assert issues[0]["id"] == "1"
        assert issues[0]["missing"] == ["verify"]

    def test_done_missing_evidence_reported(self, monkeypatch):
        engine = _make_test_engine(FakeLLMCaller([("ok", None)]), FakeToolExecutor(), monkeypatch)
        engine.task_ledger = [{"id": "1", "title": "a", "status": "done", "verify": "v"}]
        issues = engine._ledger_field_issues()
        assert issues[0]["missing"] == ["evidence"]

    def test_legacy_format_all_missing(self, monkeypatch):
        """老格式 {id,title,status}：done 项缺 verify+evidence，pending 项缺 verify"""
        engine = _make_test_engine(FakeLLMCaller([("ok", None)]), FakeToolExecutor(), monkeypatch)
        engine.task_ledger = [
            {"id": "1", "title": "a", "status": "done"},
            {"id": "2", "title": "b", "status": "pending"},
        ]
        issues = engine._ledger_field_issues()
        by_id = {i["id"]: i["missing"] for i in issues}
        assert by_id["1"] == ["verify", "evidence"]
        assert by_id["2"] == ["verify"]

    def test_empty_ledger_no_issues(self, monkeypatch):
        """台账为空 → 无缺字段问题（无账回合策略本票不管）"""
        engine = _make_test_engine(FakeLLMCaller([("ok", None)]), FakeToolExecutor(), monkeypatch)
        engine.task_ledger = []
        assert engine._ledger_field_issues() == []


# ── 端到端：收工闸 auto 硬拦 ──

class TestAutoFieldGate:
    def test_auto_compliant_passes(self, monkeypatch):
        """验收 1：auto on + 全字段合规 → 直接收工，无 deny"""
        events = _track_events()
        fake_llm = FakeLLMCaller([("已完成全部工作", None)])
        fake_tools = FakeToolExecutor()
        engine = _make_auto_engine(fake_llm, fake_tools, monkeypatch, [
            {"id": "1", "title": "a", "status": "done", "verify": "跑测试", "evidence": "全过"},
        ], auto=True)

        engine.run(user_input="干活")

        assert engine.state == engine.STATE_DONE
        denies = [e for e in events if e[0] == "goal_gate.deny"]
        assert denies == [], "合规台账不应 deny"
        assert engine._ledger_field_deny_count == 0

    def test_auto_missing_verify_denied_and_audited(self, monkeypatch):
        """验收 2：auto + 缺 verify → deny + 审计明细；补齐后放行"""
        events = _track_events()
        fake_llm = FakeLLMCaller([
            ("已完成全部工作", None),  # R1 → deny #1
            ("已完成全部工作", None),  # R2 → deny #2
            ("已完成全部工作", None),  # R3 → deny #3（无熔断，仍不放行）
            ("已完成全部工作", None),  # R4 → 钩子已补字段 → 放行
        ])
        fake_tools = FakeToolExecutor()
        engine = _make_auto_engine(fake_llm, fake_tools, monkeypatch, [
            {"id": "1", "title": "a", "status": "pending"},  # 缺 verify
        ], auto=True)

        # 钩子：第 3 次 deny 后模拟 agent 补字段（否则 deny 循环到 depth 熔断）
        original_emit = engine._emit_state_change
        _denies = [0]

        def tracking_emit(state, reason):
            if state == engine.STATE_THINKING and "ledger field deny" in str(reason):
                _denies[0] += 1
                if _denies[0] == 3:
                    engine.task_ledger = [
                        {"id": "1", "title": "a", "status": "done",
                         "verify": "跑测试", "evidence": "全过"},
                    ]
            original_emit(state, reason)

        engine._emit_state_change = tracking_emit
        engine.run(user_input="干活")

        assert engine.state == engine.STATE_DONE
        # 连续 3 次 deny 仍不放行（裁决 2：无熔断）
        denies = [e for e in events if e[0] == "goal_gate.deny"]
        assert len(denies) == 3, f"应 deny 3 次，实际 {len(denies)}"
        assert engine._ledger_field_deny_count == 3
        # 独立计数：不消耗回注熔断计数
        assert engine._ledger_reinject_count == 0, "缺字段 deny 不应消耗回注计数"
        # 审计事件字段齐全（验收 6）
        last_deny = denies[-1][1]
        assert last_deny["reason"] == "ledger_field_missing"
        assert last_deny["session_id"] == getattr(engine, "sid", "")
        assert last_deny["field_issues"] == [{"id": "1", "missing": ["verify"]}]
        assert last_deny["deny_count"] == 3
        # deny 指令含明确指引
        user_msgs = [m for m in engine.history if m.get("role") == "user"]
        deny_msgs = [m for m in user_msgs if "收工拒绝" in m.get("content", "")]
        assert len(deny_msgs) == 3, "每次 deny 都应向 history 追加指令"
        assert "verify" in deny_msgs[0]["content"] and "1" in deny_msgs[0]["content"]

    def test_auto_done_missing_evidence_then_fixed(self, monkeypatch):
        """验收 3：auto + done 缺 evidence → deny；补齐 evidence 后放行"""
        events = _track_events()
        fake_llm = FakeLLMCaller([
            ("已完成全部工作", None),  # R1 → deny（done 缺 evidence）
            ("已完成全部工作", None),  # R2 → 钩子已补 evidence → 放行
        ])
        fake_tools = FakeToolExecutor()
        engine = _make_auto_engine(fake_llm, fake_tools, monkeypatch, [
            {"id": "1", "title": "a", "status": "done", "verify": "跑测试"},  # 缺 evidence
        ], auto=True)

        original_emit = engine._emit_state_change

        def tracking_emit(state, reason):
            if state == engine.STATE_THINKING and "ledger field deny" in str(reason):
                engine.task_ledger = [
                    {"id": "1", "title": "a", "status": "done",
                     "verify": "跑测试", "evidence": "全过"},
                ]
            original_emit(state, reason)

        engine._emit_state_change = tracking_emit
        engine.run(user_input="干活")

        assert engine.state == engine.STATE_DONE
        denies = [e for e in events if e[0] == "goal_gate.deny"]
        assert len(denies) == 1
        assert denies[0][1]["field_issues"] == [{"id": "1", "missing": ["evidence"]}]

    def test_auto_off_legacy_ledger_passes_unaffected(self, monkeypatch):
        """验收 4（对照组）：auto off + 老格式缺字段台账 → 与施工前一致直接收工"""
        events = _track_events()
        fake_llm = FakeLLMCaller([("已完成全部工作", None)])
        fake_tools = FakeToolExecutor()
        engine = _make_auto_engine(fake_llm, fake_tools, monkeypatch, [
            {"id": "1", "title": "a", "status": "done"},  # 老格式，缺 verify+evidence
        ], auto=False)

        engine.run(user_input="干活")

        assert engine.state == engine.STATE_DONE
        denies = [e for e in events if e[0] == "goal_gate.deny"]
        assert denies == [], "普通模式零影响：不得触发 deny"
        assert engine._ledger_field_deny_count == 0

    def test_auto_off_no_getter_passes_unaffected(self, monkeypatch):
        """对照组 2：_auto_mode_getter 为 None（未注入）→ 物理跳过，零影响"""
        events = _track_events()
        fake_llm = FakeLLMCaller([("已完成全部工作", None)])
        fake_tools = FakeToolExecutor()
        engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)
        engine.task_ledger = [{"id": "1", "title": "a", "status": "done"}]
        engine._auto_mode_getter = None  # 普通模式未注入

        engine.run(user_input="干活")

        assert engine.state == engine.STATE_DONE
        denies = [e for e in events if e[0] == "goal_gate.deny"]
        assert denies == []

    def test_auto_legacy_format_denied(self, monkeypatch):
        """验收 5（裁决 1）：老格式台账在 auto 下 → 缺字段硬拦，无迁移豁免"""
        events = _track_events()
        fake_llm = FakeLLMCaller([
            ("已完成全部工作", None),
            ("已完成全部工作", None),
        ])
        fake_tools = FakeToolExecutor()
        engine = _make_auto_engine(fake_llm, fake_tools, monkeypatch, [
            {"id": "1", "title": "a", "status": "done"},  # 老格式
        ], auto=True)

        original_emit = engine._emit_state_change

        def tracking_emit(state, reason):
            if state == engine.STATE_THINKING and "ledger field deny" in str(reason):
                engine.task_ledger = [
                    {"id": "1", "title": "a", "status": "done",
                     "verify": "v", "evidence": "e"},
                ]
            original_emit(state, reason)

        engine._emit_state_change = tracking_emit
        engine.run(user_input="干活")

        assert engine.state == engine.STATE_DONE
        denies = [e for e in events if e[0] == "goal_gate.deny"]
        assert len(denies) == 1, "老格式在 auto 下应硬拦一次"
        assert denies[0][1]["field_issues"] == [{"id": "1", "missing": ["verify", "evidence"]}]


# ── 工具载体：schema 可选字段 + execute 语义零变化 ──

class TestToolSchemaCarrier:
    def test_schema_has_optional_fields(self):
        """C-1a：schema items 含 verify/evidence 可选字段（不进 required）"""
        from tools.task_ledger import TOOL_SCHEMA
        items = TOOL_SCHEMA["function"]["parameters"]["properties"]["items"]["items"]
        props = items["properties"]
        assert "verify" in props and "evidence" in props
        assert "verify" not in items["required"]
        assert "evidence" not in items["required"]
        assert items["required"] == ["id", "title"]  # 原有 required 不变

    def test_execute_semantics_unchanged(self, monkeypatch):
        """execute 语义零变化：create 老格式照常；新字段只是透传载体"""
        from tools.task_ledger import execute
        from core.event_bus import event_bus
        events = []
        original_write = event_bus.write
        event_bus.write = lambda t, d: (events.append((t, d)), original_write(t, d))

        # 老格式 create（无新字段）必须照常成功
        r = execute(action="create", items=[{"id": "1", "title": "a", "status": "pending"}])
        assert "已创建" in r, f"老格式 create 应成功: {r}"

        # 新字段透传：create 带 verify/evidence
        r2 = execute(action="create", items=[
            {"id": "2", "title": "b", "status": "done", "verify": "v", "evidence": "e"},
        ])
        assert "已创建" in r2

        # 清空全局台账避免污染
        from tools.task_ledger import _set_ledger
        _set_ledger([])

    def test_update_semantics_unchanged(self, monkeypatch):
        """update 语义零变化：老字段照常更新"""
        from tools.task_ledger import execute, _set_ledger
        _set_ledger([{"id": "1", "title": "a", "status": "pending"}])
        r = execute(action="update", items=[{"id": "1", "status": "done"}])
        assert "已更新" in r
        _set_ledger([])
