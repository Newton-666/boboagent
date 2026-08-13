"""TICKET-LEDGER-1 台账机制重构 — 验收测试

验收金标准：
1. 收工自动对账：收工闸触发时注入只读 git status/diff --stat（工作区实况），
   模拟"干了活没记账" → 收工时对账说明必须出现
2. deny 降本：缺字段 → 精简补正指令本轮放行 + 执法记录照留（不再全上下文重跑）
3. 提醒降噪：强制建账提醒每回合至多一次
4. 自动销账辅助：run_tests 全绿 → 建议性标 done（模型可推翻）
5. ledger.persist 独立事件（md5 复核可区分）
"""

import pytest

from tests.test_engine_e2e import FakeLLMCaller, _make_tool_call, FakeToolExecutor


def _make_engine(llm_caller, monkeypatch, auto_mode=False):
    """零外部依赖的 Engine（同 test_task_ledger 模式，支持 auto_mode）。"""
    import core.engine as engine_mod

    monkeypatch.setattr(engine_mod.Engine, "_build_system_prompt",
                        lambda self: "You are a helpful assistant.")

    engine = engine_mod.Engine(
        llm_caller=llm_caller,
        tool_executor=None,
        test_mode=True,
        auto_mode_getter=(lambda: True) if auto_mode else None,
    )

    class FakeExecutor(FakeToolExecutor):
        def __call__(self, name, args):
            if name == "task_ledger":
                from tools.task_ledger import execute
                return execute(**args)
            if name == "run_tests":
                return "2302 passed, 0 failed, 2 skipped, 1 xpassed"
            return super().__call__(name, args)

    engine.tool_executor = FakeExecutor()

    def _fake_build_messages(system_prompt, user_input, tools_schema, extra_categories, session_id=""):
        msgs = [{"role": "system", "content": system_prompt}]
        if engine.history:
            msgs.extend(engine.history)
        return msgs

    monkeypatch.setattr(engine.injector, "build_messages", _fake_build_messages)
    monkeypatch.setattr(engine.proactive, "inject_context", lambda msgs: msgs)
    monkeypatch.setattr(engine.proactive, "mode", "off")
    monkeypatch.setattr(engine.skill_loader, "load_standards", lambda: [])
    engine.verifier.check_and_inject = lambda *a, **kw: False
    engine._worker_reminded = True
    monkeypatch.setattr(engine, "_check_guards", lambda: False)

    return engine


def _run_with_capture(engine, user_input):
    """运行并捕获 complete 事件终稿。"""
    final_output = [""]
    engine.callback = (lambda et, d: final_output.__setitem__(0, d.get("content", ""))
                       if et == "complete" else None)
    engine.run(user_input=user_input)
    return final_output[0]


# ── 验收 1：收工自动对账 ────────────────────────────────────────────


class TestLedger1WorkspaceRecon:
    """收工闸触发时注入工作区实况，堵汇报失实。"""

    @pytest.fixture(autouse=True)
    def _reset_ledger(self):
        from tools.task_ledger import _set_ledger
        _set_ledger([])
        yield
        _set_ledger([])

    def test_recon_live_returns_real_git(self, monkeypatch):
        """_workspace_recon 真实执行只读 git（当前 repo 有改动 → 返回实况）。"""
        import core.engine as engine_mod
        monkeypatch.setattr(engine_mod.Engine, "_build_system_prompt",
                            lambda self: "sys")
        engine = engine_mod.Engine(llm_caller=None, test_mode=True)
        recon = engine._workspace_recon()
        assert isinstance(recon, str)
        if recon:
            assert "工作区实况" in recon
            assert "git status" in recon or "git diff" in recon

    def test_recon_injected_on_finish_after_tool_rounds(self, monkeypatch):
        """实弹：干了活（工具轮）→ 工作区实况并入 history 内部上下文（LEDGER-1B：
        不再拼进可见终稿，git 原文不上屏；对账机制仍触发）。"""
        fake_llm = FakeLLMCaller([
            (None, [_make_tool_call("t1", "edit_file",
                                    {"file_path": "x.txt", "old_string": "a", "new_string": "b"})]),
            ("改好了", None),
        ])
        engine = _make_engine(fake_llm, monkeypatch)
        monkeypatch.setattr(
            engine, "_workspace_recon",
            lambda: "\n\n── 工作区实况（收工对账，只读）──\n"
                    "git status --short: 1 项变更\n"
                    "台账与汇报必须与以上工作区实况一致",
        )
        final = _run_with_capture(engine, "改个文件")
        # LEDGER-1B：git 原文不上屏（可见回复零原文墙）
        assert "工作区实况" not in final, f"对账段不得进可见终稿: {final}"
        assert "git status" not in final, f"git 原文不得上屏: {final}"
        # 对账机制不破：history 里并入工作区实况（内部上下文，供模型写汇报时对账）
        hist_txt = "\n".join(m.get("content") or "" for m in engine.history)
        assert "工作区实况" in hist_txt, "对账段应并入 history（内部上下文）"
        assert "台账与汇报必须" in hist_txt

    def test_recon_injected_on_clean_done(self, monkeypatch):
        """台账全 done 干净收工，有工具轮 → 对账仍并入 history（LEDGER-1B：不进可见终稿）。"""
        fake_llm = FakeLLMCaller([
            (None, [_make_tool_call("t1", "task_ledger", {
                "action": "create",
                "items": [{"id": "1", "title": "A", "status": "done",
                           "verify": "测试全绿", "evidence": "2302 passed"}],
            })]),
            ("任务完成", None),
        ])
        engine = _make_engine(fake_llm, monkeypatch)
        monkeypatch.setattr(engine, "_workspace_recon",
                            lambda: "\n\n── 工作区实况（收工对账，只读）──\nM core/engine.py")
        final = _run_with_capture(engine, "做 A")
        assert "工作区实况" not in final, f"对账段不得进可见终稿: {final}"
        hist_txt = "\n".join(m.get("content") or "" for m in engine.history)
        assert "工作区实况" in hist_txt, "对账段应并入 history（内部上下文）"
        assert engine.state == engine.STATE_DONE

    def test_recon_not_injected_chat_round(self, monkeypatch):
        """纯聊天回合（tool_round=0）→ 不注入，行为不变。"""
        fake_llm = FakeLLMCaller([("你好", None)])
        engine = _make_engine(fake_llm, monkeypatch)
        monkeypatch.setattr(engine, "_workspace_recon",
                            lambda: "SHOULD NOT APPEAR")
        final = _run_with_capture(engine, "你好")
        assert "SHOULD NOT APPEAR" not in final
        assert engine.state == engine.STATE_DONE


# ── 验收 2：deny 降本（缺字段 → 本轮放行 + 执法记录） ─────────────────


class TestLedger1FieldGatePassWithNote:
    """缺字段不再强制全上下文重跑；执法记录照留。"""

    @pytest.fixture(autouse=True)
    def _reset_ledger(self):
        from tools.task_ledger import _set_ledger
        _set_ledger([])
        yield
        _set_ledger([])

    def test_field_missing_pass_with_note_no_reinject(self, monkeypatch):
        """AUTO MODE：done 项缺 evidence → 本轮放行 + 补正指令，不重跑。"""
        fake_llm = FakeLLMCaller([
            (None, [_make_tool_call("t1", "task_ledger", {
                "action": "create",
                "items": [{"id": "1", "title": "A", "status": "done"}],  # 缺 evidence
            })]),
            ("做完了", None),
        ])
        events = []
        import core.event_bus as eb_mod
        monkeypatch.setattr(eb_mod.event_bus, "write",
                            lambda etype, data: events.append((etype, data)) or None)

        engine = _make_engine(fake_llm, monkeypatch, auto_mode=True)
        monkeypatch.setattr(engine, "_workspace_recon", lambda: "")
        final = _run_with_capture(engine, "做 A")

        assert engine.state == engine.STATE_DONE
        # 不重跑：除初始 user_input 外无额外 user 回注
        user_msgs = [m for m in engine.history if m.get("role") == "user"]
        assert len(user_msgs) == 1, f"缺字段仍触发重跑: {len(user_msgs)} 条 user"
        # 终稿带精简补正指令（本轮放行语义）
        assert "字段闸记录" in final and "本轮放行" in final
        # 执法记录照留（goal_gate.deny + pass_with_note 标记）
        denies = [d for t, d in events if t == "goal_gate.deny"]
        assert denies and denies[0].get("mode") == "pass_with_note"
        assert denies[0].get("reason") == "ledger_field_missing"
        # LLM 调用次数 = 2（无额外重跑轮）
        assert fake_llm.call_count == 2

    def test_field_missing_no_auto_mode_untouched(self, monkeypatch):
        """普通模式（非 auto/office）→ 字段闸整段跳过，零行为变化。"""
        fake_llm = FakeLLMCaller([
            (None, [_make_tool_call("t1", "task_ledger", {
                "action": "create",
                "items": [{"id": "1", "title": "A", "status": "done"}],  # 缺 evidence
            })]),
            ("做完了", None),
        ])
        engine = _make_engine(fake_llm, monkeypatch)  # auto_mode=False
        monkeypatch.setattr(engine, "_workspace_recon", lambda: "")
        final = _run_with_capture(engine, "做 A")
        assert engine.state == engine.STATE_DONE
        assert "字段闸记录" not in final  # 普通模式不执法


# ── 验收 3：提醒降噪（建账提醒每回合至多一次） ──────────────────────


class TestLedger1NoLedgerReminderOnce:
    """强制建账提醒每回合至多一次（原上限 2）。"""

    @pytest.fixture(autouse=True)
    def _reset_ledger(self):
        from tools.task_ledger import _set_ledger
        _set_ledger([])
        yield
        _set_ledger([])

    def test_no_ledger_reminder_injected_once(self, monkeypatch):
        """工作回合无账 → R2a v2 零回注零提醒直接收工（原硬闸回注已拆）。"""
        fake_llm = FakeLLMCaller([
            (None, [_make_tool_call("t1", "edit_file",
                                    {"file_path": "y.txt", "old_string": "a", "new_string": "b"})]),
            ("干完了", None),     # 收工 → R2a v2 直接放行
        ])
        engine = _make_engine(fake_llm, monkeypatch)
        monkeypatch.setattr(engine, "_workspace_recon", lambda: "")
        final = _run_with_capture(engine, "改文件")

        assert engine.state == engine.STATE_DONE
        user_msgs = [m for m in engine.history if m.get("role") == "user"]
        reminders = [m for m in user_msgs if "没有建立任务台账" in (m.get("content", "") or "")]
        assert len(reminders) == 0, f"R2a v2 建账提醒应零次，实际 {len(reminders)}"
        assert "引擎放行" not in final, "R2a v2 无账不应有 ⚠️ 放行遗言"


# ── 验收 4：自动销账辅助（run_tests 全绿 → 建议标 done） ─────────────


class TestLedger1AutoSuggest:
    """引擎检测强完成信号 → 建议性标 done（模型可推翻，引擎不改账）。"""

    @pytest.fixture(autouse=True)
    def _reset_ledger(self):
        from tools.task_ledger import _set_ledger
        _set_ledger([])
        yield
        _set_ledger([])

    def test_green_tests_suggest_done(self, monkeypatch):
        """run_tests 全绿 → history 注入建议消息。"""
        fake_llm = FakeLLMCaller([
            (None, [_make_tool_call("t1", "run_tests", {"path": "."})]),
            (None, [_make_tool_call("t2", "task_ledger", {
                "action": "update",
                "items": [{"id": "1", "status": "done", "evidence": "2302 passed"}],
            })]),
            ("完成", None),
        ])
        engine = _make_engine(fake_llm, monkeypatch)
        engine.task_ledger = [
            {"id": "1", "title": "A", "status": "pending", "verify": "测试全绿"},
        ]
        monkeypatch.setattr(engine, "_workspace_recon", lambda: "")
        final = _run_with_capture(engine, "修 A 并跑测试")

        assert engine.state == engine.STATE_DONE
        sys_msgs = [m.get("content", "") for m in engine.history if m.get("role") == "system"]
        assert any("测试全绿强完成信号" in c for c in sys_msgs), "全绿后未注入建议"
        # 台账最终全 done（模型采纳建议）
        assert engine.task_ledger[0]["status"] == "done"
        assert engine.task_ledger[0].get("evidence") == "2302 passed"

    def test_suggest_not_injected_when_no_pending(self, monkeypatch):
        """台账全 done → 无建议注入。"""
        fake_llm = FakeLLMCaller([
            (None, [_make_tool_call("t1", "run_tests", {"path": "."})]),
            ("跑完了", None),
        ])
        engine = _make_engine(fake_llm, monkeypatch)
        engine.task_ledger = [
            {"id": "1", "title": "A", "status": "done", "verify": "v", "evidence": "e"},
        ]
        monkeypatch.setattr(engine, "_workspace_recon", lambda: "")
        final = _run_with_capture(engine, "跑测试")
        sys_msgs = [m.get("content", "") for m in engine.history if m.get("role") == "system"]
        assert not any("测试全绿强完成信号" in c for c in sys_msgs)


# ── 验收 5：ledger.persist 独立事件 ─────────────────────────────────


class TestLedger1PersistEvent:
    """台账持久化记独立事件，md5 复核可区分。"""

    def test_persist_event_write_no_crash(self):
        """ledger.persist 事件写入不抛异常（事件总线铁律）。"""
        from core.event_bus import event_bus
        event_bus.write("ledger.persist", {
            "session_id": "test", "items": 1, "done": 1,
            "with_verify": 1, "with_evidence": 1, "fingerprint": "abc123",
        })

    def test_persist_event_wired_in_adapter(self):
        """engine_adapter 台账回写处已接 ledger.persist 事件。"""
        import pathlib
        repo_root = pathlib.Path(__file__).resolve().parent.parent
        src = (repo_root / "core" / "engine_adapter.py").read_text(encoding="utf-8")
        assert "ledger.persist" in src
        assert "fingerprint" in src
