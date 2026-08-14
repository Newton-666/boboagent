"""票 CORE-R3：答复压制源拆除——四刀专项测试

验收（票附录施工方案）：
1. 复现解剖场景：施工收尾一次性登记台账全 done（create 前有真实施工轮）→
   零 deny、零打回、一次成稿（刀 a：_detect_ledger_backfill 施工证据豁免）
2. 收尾 ct=0 回归断言：不再出现"deny → 空回复 ct=0 → 再 deny"死循环（刀 c/d）
3. R2b 豁免面扩大：读/查类施工（非写类工具）收尾不被打回（刀 b）
4. verifier 完成词收紧：无工具轮但含"完成"/"阶段"字样不误触发（刀 c）

覆写 _make_test_engine 的 verifier 禁用（本票要测 verifier 真实行为）。
"""

import pytest

from tests.test_engine_e2e import (
    FakeLLMCaller, FakeToolExecutor, _make_tool_call, _make_test_engine,
)
from tests.test_ticket_c_ledger_gate import _track_events
from core.verifier import Verifier


def _make_engine(fake_llm, fake_tools, monkeypatch, ledger=None, auto=False,
                 office_on=False, keep_verifier=False):
    """构造 engine：设台账 + auto/office 会话级开关。

    keep_verifier=True 时恢复真实 verifier.check_and_inject（测刀 c）。
    """
    engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)
    if ledger is not None:
        engine.task_ledger = ledger
    # 让假执行器里的 task_ledger 走真实 execute（写 engine.task_ledger）
    fake_tools.ledger_engine = engine
    engine._auto_mode_getter = (lambda: True) if auto else (lambda: False)
    monkeypatch.setattr("bobo_tui_gateway.server.get_office_on", lambda sid: office_on)
    if keep_verifier:
        engine.verifier = Verifier()
    return engine


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


# ── 场景 1：收尾一次性登记台账全 done → 零 deny 零打回一次成稿（刀 a） ──

class TestAnatomyOneShotLedgerCloseout:
    """复现解剖场景：干完活（有施工轮）→ 收尾一次性 task_ledger create 全 done。

    修复前：create 前台账空 + 新账全 done → 判"事后补账"→ deny（799 次/库）。
    修复后：create 前存在非 ledger 工具轮（真实施工痕迹）→ 豁免，零 deny。
    """

    def test_construction_then_one_shot_ledger_zero_deny(self, monkeypatch):
        """施工轮（echo 工具）→ 收尾 create 台账全 done → 零 deny、一次成稿"""
        events = _track_events()
        # 施工轮：非 ledger 工具（echo）；收尾轮：task_ledger create 全 done
        fake_llm = FakeLLMCaller([
            (None, [_make_tool_call("c1", "echo", {"msg": "施工痕迹"})]),     # R1: 施工
            (None, [_make_tool_call("c2", "task_ledger", {
                "action": "create",
                "items": [
                    {"id": "a", "title": "任务A", "status": "done",
                     "verify": "测试通过", "evidence": "pytest 全绿"},
                    {"id": "b", "title": "任务B", "status": "done",
                     "verify": "文件存在", "evidence": "core/engine.py 改动"},
                ],
            })]),                                                             # R2: 收尾登记全 done
            ("全部完成。改了 engine.py，测试全绿。", None),                    # R3: 成稿
        ])
        fake_tools = FakeToolExecutor({
            "echo": "ok",
            "task_ledger": "[ledger updated]",
        })
        engine = _make_engine(fake_llm, fake_tools, monkeypatch, auto=True)
        engine.run(user_input="施工任务A和B")

        assert engine.state == engine.STATE_DONE
        # 零 deny：无 ledger_backfill deny、无任何 goal_gate.deny
        denies = [e for e in events if e[0] == "goal_gate.deny"]
        assert denies == [], f"应零 deny，实际 {denies}"
        # 零打回：无收工拒绝回注
        user_msgs = _user_msgs(engine)
        reject_msgs = [m for m in user_msgs if "收工拒绝" in m.get("content", "")]
        assert reject_msgs == [], f"应零打回，实际 {reject_msgs}"
        # 一次成稿：LLM 调用 3 次（施工、登记、成稿），无额外重试
        assert fake_llm.call_count == 3, f"应 3 次调用一次成稿，实际 {fake_llm.call_count}"
        # 台账已登记
        assert len(engine.task_ledger) == 2
        assert all(e.get("status") == "done" for e in engine.task_ledger)

    def test_backfill_still_denied_without_construction(self, monkeypatch):
        """无施工痕迹 + 批量 create 全 done → 仍 deny（闸能力保留，只收窄不拆除）

        deny 无熔断：R2 触发补账 deny 后，模型须按指令用 update 修正（改 pending →
        补证据销账）才能闭合；序列模拟真实响应链。
        """
        events = _track_events()
        fake_llm = FakeLLMCaller([
            (None, [_make_tool_call("c1", "task_ledger", {
                "action": "create",
                "items": [
                    {"id": "a", "title": "任务A", "status": "done",
                     "verify": "x", "evidence": "y"},
                    {"id": "b", "title": "任务B", "status": "done",
                     "verify": "x", "evidence": "y"},
                ],
            })]),                                                        # R1: 批量全 done → 嫌疑置位
            ("全部完成", None),                                           # R2: 文本 → 补账 deny #1
            (None, [_make_tool_call("c2", "task_ledger", {
                "action": "update",
                "items": [
                    {"id": "a", "status": "pending"},
                    {"id": "b", "status": "pending"},
                ],
            })]),                                                        # R3: 按指令改 pending → 清嫌疑
            (None, [_make_tool_call("c3", "task_ledger", {
                "action": "update",
                "items": [
                    {"id": "a", "status": "done", "verify": "测试通过", "evidence": "pytest 全绿"},
                    {"id": "b", "status": "done", "verify": "文件存在", "evidence": "core/engine.py"},
                ],
            })]),                                                        # R4: 真实销账（带 verify/evidence）
            ("全部完成。任务A测试全绿，任务B文件改动已落地，证据已补齐。", None),  # R5: 收尾成稿
        ])
        fake_tools = FakeToolExecutor({})
        engine = _make_engine(fake_llm, fake_tools, monkeypatch, auto=True)
        engine.run(user_input="干活")

        # 无施工轮 → 补账嫌疑 → deny 审计照留
        denies = [e for e in events if e[0] == "goal_gate.deny"
                  and e[1].get("reason") == "ledger_backfill"]
        assert len(denies) >= 1, f"无施工痕迹的批量全 done 应仍 deny，实际 {denies}"
        assert engine.state == engine.STATE_DONE, "修正链路应闭合到 DONE"


# ── 场景 2：收尾 ct=0 回归断言（刀 c/d） ──

class TestCloseoutNoEmptyReplyLoop:
    """收尾回合不再出现 completion_tokens=0 死循环。

    修复前典型死循环：R2b 打回 → 收工闸 deny → 空回复 ct=0 → 再打回 → 熔断。
    修复后：有施工证据 → 各闸直接放行，无回注 → 无空回复轮。
    """

    def test_no_empty_reply_after_construction(self, monkeypatch):
        """有施工证据的收尾 → 无"空回复"轮（每轮都有实质 content 或工具轮）"""
        events = _track_events()
        fake_llm = FakeLLMCaller([
            (None, [_make_tool_call("c1", "echo", {"msg": "a"})]),
            (None, [_make_tool_call("c2", "echo", {"msg": "b"})]),
            (None, [_make_tool_call("c3", "echo", {"msg": "c"})]),
            (None, [_make_tool_call("c4", "task_ledger", {
                "action": "create",
                "items": [{"id": "a", "title": "任务A", "status": "done",
                           "verify": "v", "evidence": "e"}],
            })]),
            ("全部完成，三次施工都做了。", None),
        ])
        fake_tools = FakeToolExecutor({"echo": "ok", "task_ledger": "[ok]"})
        engine = _make_engine(fake_llm, fake_tools, monkeypatch, auto=True)
        engine.run(user_input="连续施工三次并收尾")

        assert engine.state == engine.STATE_DONE
        # 零 deny（施工证据豁免 → 不逼"继续" → 无空回复触发源）
        denies = [e for e in events if e[0] == "goal_gate.deny"]
        assert denies == [], f"施工收尾应零 deny，实际 {denies}"
        # 无"请继续执行"类回注（无强制继续 → 无空回复轮）
        user_msgs = _user_msgs(engine)
        continue_msgs = [m for m in user_msgs if "请继续执行" in m.get("content", "")]
        assert continue_msgs == [], f"应无强制继续回注，实际 {continue_msgs}"
        # 终稿含实质内容（非空回复残骸）
        completes = _capture_complete(engine)
        engine._notify("complete", {"content": "全部完成，三次施工都做了。"})
        assert any("三次施工都做了" in c for c in completes), f"终稿应含实质内容，实际 {completes}"


# ── 刀 b：R2b 豁免面扩大（读/查施工不被打回） ──

class TestR2bExemptExpanded:
    """读/查类施工（非写类工具）≥3 次工具执行 → 答复质量闸豁免"""

    def test_read_round_three_tools_exempt(self, monkeypatch):
        """3 次读/查工具（echo）→ 台账腔回复豁免，不被打回"""
        fake_llm = FakeLLMCaller([
            (None, [_make_tool_call("c1", "echo", {"msg": "a"})]),
            (None, [_make_tool_call("c2", "echo", {"msg": "b"})]),
            (None, [_make_tool_call("c3", "echo", {"msg": "c"})]),
            ("📋 台账: 1/1 done\n- 完成项：查了三处资料", None),  # 台账腔但 ≥3 次工具 → 豁免
        ])
        fake_tools = FakeToolExecutor({"echo": "ok"})
        engine = _make_engine(fake_llm, fake_tools, monkeypatch)
        engine.run(user_input="查三处资料并汇报")

        assert engine.state == engine.STATE_DONE
        quality_reinjects = [m for m in _user_msgs(engine) if "没有直接回答" in m.get("content", "")]
        assert quality_reinjects == [], f"≥3 次工具执行应豁免 R2b，实际 {len(quality_reinjects)} 次打回"

    def test_two_tools_still_checked(self, monkeypatch):
        """<3 次工具执行（2 次）→ 台账腔仍打回（豁免面只扩大，不拆闸）"""
        fake_llm = FakeLLMCaller([
            (None, [_make_tool_call("c1", "echo", {"msg": "a"})]),
            (None, [_make_tool_call("c2", "echo", {"msg": "b"})]),
            ("📋 台账: 1/1 done\n- 完成项：查了两处", None),  # 台账腔且 <3 次 → 打回
            ("查完了。结论是 X。", None),
        ])
        fake_tools = FakeToolExecutor({"echo": "ok"})
        engine = _make_engine(fake_llm, fake_tools, monkeypatch)
        engine.run(user_input="查两处资料并汇报")

        assert engine.state == engine.STATE_DONE
        quality_reinjects = [m for m in _user_msgs(engine) if "没有直接回答" in m.get("content", "")]
        assert len(quality_reinjects) == 1, f"2 次工具执行应仍打回 1 次，实际 {len(quality_reinjects)}"


# ── 刀 c：verifier 完成词收紧 ──

class TestVerifierTightened:
    """"完成"/"阶段"两字词不再误触发；仅零 tool.exec 才触发"""

    def test_word_completion_not_triggered(self):
        """含"完成"/"阶段"字样但非完成声称 → 不触发（旧版必误触发）"""
        v = Verifier()
        # 旧版：completion_markers 含"完成"/"阶段" → 必 True；新版应 False
        assert v.needs_verification("任务完成项共 3 条，阶段二已就绪") is False

    def test_phrase_completion_still_triggered(self):
        """明确完成短语 + 零 tool.exec → 仍触发（能力保留）"""
        v = Verifier()
        assert v.needs_verification("我已全部完成") is True

    def test_check_and_inject_skips_when_tools_executed(self):
        """声称完成但本回合有 tool.exec（>0）→ 不注入验证提示（干完活正常收尾）"""
        v = Verifier()
        history = []
        assert v.check_and_inject(history, "全部完成，改了 engine.py", tool_exec_count=5) is False
        assert history == [], "有工具执行不应注入验证提示"

    def test_check_and_inject_fires_when_zero_tools(self):
        """声称完成且零 tool.exec → 注入验证提示（空口声称仍被检测）"""
        v = Verifier()
        history = []
        assert v.check_and_inject(history, "全部完成", tool_exec_count=0) is True
        assert any("[验证]" in m.get("content", "") for m in history)

    def test_engine_pass_round_tool_exec_count(self, monkeypatch):
        """engine 调用 check_and_inject 时传本回合 tool_exec_count（零工具轮问答不误伤）"""
        from core.verifier import Verifier as V2
        fake_llm = FakeLLMCaller([
            ("直接回答：关于X，结论是A。", None),  # 零工具轮问答
        ])
        fake_tools = FakeToolExecutor()
        engine = _make_engine(fake_llm, fake_tools, monkeypatch, keep_verifier=True)
        # 替换为真实 Verifier 实例
        engine.verifier = V2()
        injected = []
        original = engine.verifier.check_and_inject

        def spy_check(history, content, tool_exec_count=0):
            injected.append(tool_exec_count)
            return original(history, content, tool_exec_count=tool_exec_count)

        engine.verifier.check_and_inject = spy_check
        engine.run(user_input="X 是什么")

        assert engine.state == engine.STATE_DONE
        # 零工具轮：tool_exec_count 应为 0（回合初始值），问答不误伤
        assert injected, "check_and_inject 应被调用"
        assert injected[0] == 0, f"零工具轮问答 tool_exec_count 应为 0，实际 {injected[0]}"
        # 问答回复未被验证注入污染
        assert "[验证]" not in str(engine.history)
