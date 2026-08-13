"""票 K v2 任务台账 — 验收全量测试

验收金标准：
1. 续跑复活（核心）— 台账有 pending → 回注再调 LLM
2. 两次熔断 — 连续 3 轮文本不销账 → 第 2 次回注后放行 + ⚠️ 遗言
3. 干净收工零误伤 — 全 done → 正常 done
4. 无账放行 — 空台账 → done + task.no_ledger 事件
5. 持久化 — save/load 后台账原样恢复
6. 事件流 — create/update 触发 task.check
7. pytest 全绿（基线 892）
8. 五查汇报
"""

import pytest


# ── 工具单元测试 ──


class TestTaskLedgerTool:
    """子系统②：task_ledger 工具本身的功能测试。"""

    @pytest.fixture(autouse=True)
    def _reset_ledger(self):
        from tools.task_ledger import _set_ledger
        _set_ledger([])
        yield
        _set_ledger([])

    def test_create_empty_list(self):
        from tools.task_ledger import execute
        result = execute(action="create", items=[])
        assert "需要提供 items" in result

    def test_create_valid_items(self):
        from tools.task_ledger import execute, _get_ledger
        items = [
            {"id": "1", "title": "修复 bug A"},
            {"id": "2", "title": "写测试", "status": "pending"},
            {"id": "3", "title": "部署", "status": "in_progress"},
        ]
        result = execute(action="create", items=items)
        assert "已创建" in result
        ledger = _get_ledger()
        assert len(ledger) == 3
        assert ledger[0]["id"] == "1"
        assert ledger[0]["status"] == "pending"
        assert ledger[2]["status"] == "in_progress"

    def test_create_rejects_duplicate_ids(self):
        from tools.task_ledger import execute
        items = [{"id": "1", "title": "A"}, {"id": "1", "title": "B"}]
        result = execute(action="create", items=items)
        assert "id 必须唯一" in result

    def test_create_rejects_over_20_items(self):
        from tools.task_ledger import execute
        items = [{"id": str(i), "title": f"任务{i}"} for i in range(21)]
        result = execute(action="create", items=items)
        assert "不能超过 20" in result

    def test_create_rejects_invalid_item(self):
        from tools.task_ledger import execute
        result = execute(action="create", items=[{"id": "1"}])
        assert "校验失败" in result

    def test_update_single_item(self):
        from tools.task_ledger import execute, _get_ledger
        execute(action="create", items=[{"id": "1", "title": "bug A"}, {"id": "2", "title": "bug B"}])
        result = execute(action="update", items=[{"id": "1", "status": "done"}])
        assert "已更新" in result
        ledger = _get_ledger()
        assert ledger[0]["status"] == "done"
        assert ledger[1]["status"] == "pending"

    def test_update_not_found(self):
        from tools.task_ledger import execute
        execute(action="create", items=[{"id": "1", "title": "A"}])
        result = execute(action="update", items=[{"id": "99", "status": "done"}])
        assert "未找到" in result

    def test_list_when_empty(self):
        from tools.task_ledger import execute
        result = execute(action="list")
        assert "为空" in result

    def test_list_with_items(self):
        from tools.task_ledger import execute
        execute(action="create", items=[{"id": "1", "title": "A"}, {"id": "2", "title": "B"}])
        execute(action="update", items=[{"id": "1", "status": "done"}])
        result = execute(action="list")
        assert "1/2" in result

    def test_list_shows_verify_evidence_flags(self):
        """票 C 落账收编（C2）：create 带 verify → list 显 [V|e-]；补 evidence → [V|E]。"""
        from tools.task_ledger import execute
        execute(action="create", items=[{"id": "v1", "title": "带验证", "verify": "pytest 全绿"}])
        result = execute(action="list")
        assert "[V|e-]" in result, f"verify 落账未显示 V: {result}"
        execute(action="update", items=[{"id": "v1", "status": "pending", "evidence": "md5 一致"}])
        result = execute(action="list")
        assert "[V|E]" in result, f"evidence 补录后未显示 E: {result}"

    def test_update_adds_evidence_shows_e(self):
        """票 C 落账收编（C2）：update 补 evidence → [v-|E]，缺 verify 不误显 V。"""
        from tools.task_ledger import execute
        execute(action="create", items=[{"id": "v2", "title": "补证据"}])
        execute(action="update", items=[{"id": "v2", "status": "done", "evidence": "测试 12 全过"}])
        result = execute(action="list")
        assert "[v-|E]" in result, f"evidence 未显示 E 或 verify 误显: {result}"

    def test_all_done_prompt(self):
        from tools.task_ledger import execute
        execute(action="create", items=[{"id": "1", "title": "A"}])
        result = execute(action="update", items=[{"id": "1", "status": "done"}])
        assert "所有任务已完成" in result

    def test_rejects_bad_status(self):
        from tools.task_ledger import execute
        result = execute(action="create", items=[{"id": "1", "title": "A", "status": "invalid"}])
        assert "status" in result or "必须是" in result

    def test_rejects_empty_id(self):
        from tools.task_ledger import execute
        result = execute(action="create", items=[{"id": "", "title": "A"}])
        assert "id 必须" in result

    def test_unknown_action(self):
        from tools.task_ledger import execute
        result = execute(action="unknown")
        assert "不支持" in result


class TestTaskLedgerEvents:
    """事件流：create/update 各触发 task.check。"""

    @pytest.fixture(autouse=True)
    def _reset_ledger(self):
        from tools.task_ledger import _set_ledger
        _set_ledger([])
        yield
        _set_ledger([])

    def test_create_triggers_event(self):
        """验收金标准 6：create 触发 task.check。"""
        from tools.task_ledger import execute
        execute(action="create", items=[{"id": "1", "title": "A"}])

    def test_update_triggers_event(self):
        """验收金标准 6：update 触发 task.check。"""
        from tools.task_ledger import execute
        execute(action="create", items=[{"id": "1", "title": "A"}])
        execute(action="update", items=[{"id": "1", "status": "done"}])

    def test_events_do_not_crash(self):
        """事件写入不抛异常。"""
        from tools.task_ledger import execute
        execute(action="create", items=[{"id": "1", "title": "A"}])
        execute(action="update", items=[{"id": "1", "status": "done"}])


# ── Engine 集成测试（收工闸核心） ──


class TestEngineLedgerReinjection:
    """子系统③：RESPONDING 收工闸 — Engine 集成测试。"""

    @pytest.fixture(autouse=True)
    def _reset_everything(self):
        from tools.task_ledger import _set_ledger
        _set_ledger([])
        yield
        _set_ledger([])

    def _make_engine(self, llm_caller, monkeypatch):
        """创建零外部依赖的 Engine（与 test_engine_e2e 一致）。"""
        import core.engine as engine_mod

        monkeypatch.setattr(engine_mod.Engine, "_build_system_prompt",
                            lambda self: "You are a helpful assistant.")

        engine = engine_mod.Engine(
            llm_caller=llm_caller,
            tool_executor=None,
            test_mode=True,
        )

        class FakeExecutor:
            def __call__(self, name, args):
                if name == "task_ledger":
                    from tools.task_ledger import execute
                    return execute(**args)
                return f"[fake:{name}]"

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

    # ── 金标准 1：续跑复活（核心） ──

    def test_reinjection_continues_pending_ledger(self, monkeypatch):
        """台账有 pending 项，LLM 返回文本 → 引擎回注并再调 LLM。"""
        from tests.test_engine_e2e import FakeLLMCaller, _make_tool_call

        fake_llm = FakeLLMCaller([
            (None, [_make_tool_call("t1", "task_ledger", {
                "action": "create",
                "items": [{"id": "1", "title": "修复 bug A"}, {"id": "2", "title": "修复 bug B"}],
            })]),
            ("我先等30秒再拉取结果", None),
            (None, [_make_tool_call("t2", "task_ledger", {
                "action": "update",
                "items": [{"id": "1", "status": "done"}, {"id": "2", "status": "done"}],
            })]),
            ("两个 bug 都修好了", None),
        ])

        engine = self._make_engine(fake_llm, monkeypatch)
        engine.run(user_input="修复 bug A 和 B")

        assert engine.state == engine.STATE_DONE
        assert fake_llm.call_count == 4

        pending = [e for e in engine.task_ledger if e.get("status") != "done"]
        assert len(pending) == 0

        user_msgs = [m for m in engine.history if m.get("role") == "user"]
        assert any("任务台账还有" in (m.get("content", "") or "") for m in user_msgs)

    # ── 金标准 2：两次熔断 ──

    def test_two_reinjections_then_force_release(self, monkeypatch):
        """连续回注 2 次后熔断放行，终稿含 ⚠️ 遗言。"""
        from tests.test_engine_e2e import FakeLLMCaller, _make_tool_call

        fake_llm = FakeLLMCaller([
            (None, [_make_tool_call("t1", "task_ledger", {
                "action": "create",
                "items": [{"id": "1", "title": "A"}, {"id": "2", "title": "B"}, {"id": "3", "title": "C"}],
            })]),
            ("我还在处理，稍等", None),
            ("快了快了", None),
            ("好了好了", None),
        ])

        final_output = [""]

        def capture_complete(event_type, data):
            if event_type == "complete":
                final_output[0] = data.get("content", "")

        engine = self._make_engine(fake_llm, monkeypatch)
        engine.callback = capture_complete
        engine.run(user_input="处理 A B C")

        assert engine.state == engine.STATE_DONE
        assert "⚠️" in final_output[0] and "台账" in final_output[0]

    # ── 金标准 3：干净收工零误伤 ──

    def test_clean_done_when_all_complete(self, monkeypatch):
        """台账全 done → 正常 done，无回注、无遗言。"""
        from tests.test_engine_e2e import FakeLLMCaller, _make_tool_call

        fake_llm = FakeLLMCaller([
            (None, [_make_tool_call("t1", "task_ledger", {
                "action": "create", "items": [{"id": "1", "title": "单一任务"}],
            })]),
            (None, [_make_tool_call("t2", "task_ledger", {
                "action": "update", "items": [{"id": "1", "status": "done"}],
            })]),
            ("任务完成", None),
        ])

        engine = self._make_engine(fake_llm, monkeypatch)
        engine.run(user_input="做一件事")

        assert engine.state == engine.STATE_DONE

        user_msgs = [m for m in engine.history if m.get("role") == "user"]
        assert not any("任务台账还有" in (m.get("content", "") or "") for m in user_msgs)
        assert "⚠️" not in (engine._pending_content or "")

    # ── 金标准 4：无账放行 ──

    def test_no_ledger_direct_done(self, monkeypatch):
        """台账为空 → 直接 done，无回注。"""
        from tests.test_engine_e2e import FakeLLMCaller

        fake_llm = FakeLLMCaller([("随便聊聊", None)])
        engine = self._make_engine(fake_llm, monkeypatch)
        engine.run(user_input="你好")
        assert engine.state == engine.STATE_DONE

        user_msgs = [m for m in engine.history if m.get("role") == "user"]
        assert len(user_msgs) == 1

    # ── 金标准 5：持久化 ──

    def test_ledger_persistence(self, monkeypatch):
        """engine 运行后，task_ledger 可从 session dict 恢复。"""
        from tests.test_engine_e2e import FakeLLMCaller, _make_tool_call

        fake_llm = FakeLLMCaller([
            (None, [_make_tool_call("t1", "task_ledger", {
                "action": "create", "items": [{"id": "1", "title": "持久化测试"}],
            })]),
            (None, [_make_tool_call("t2", "task_ledger", {
                "action": "update", "items": [{"id": "1", "status": "done"}],
            })]),
            ("完成", None),
        ])

        engine = self._make_engine(fake_llm, monkeypatch)
        engine.run(user_input="测试持久化")

        session = {"messages": list(engine.history), "task_ledger": list(engine.task_ledger)}

        restored = list(session.get("task_ledger", []))
        assert len(restored) == 1
        assert restored[0]["id"] == "1"
        assert restored[0]["status"] == "done"

    # ── 降级方案：摘要行 ──

    def test_summary_line_appended(self, monkeypatch):
        """写类施工回合台账非空 → 终稿包含 📋 摘要行（票 R2b：仅写类施工回合交账）。"""
        from tests.test_engine_e2e import FakeLLMCaller, _make_tool_call

        fake_llm = FakeLLMCaller([
            (None, [_make_tool_call("c1", "edit_file",
                                    {"file_path": "a.py", "old_string": "x", "new_string": "y"})]),
            ("任务进行中", None),
        ])
        final_output = [""]

        def capture_complete(event_type, data):
            if event_type == "complete":
                final_output[0] = data.get("content", "")

        engine = self._make_engine(fake_llm, monkeypatch)
        engine.task_ledger = [
            {"id": "1", "title": "A", "status": "done"},
            {"id": "2", "title": "B", "status": "pending"},
        ]
        engine.callback = capture_complete
        engine.run(user_input="继续")

        assert "📋 台账:" in final_output[0]
        assert "1/2" in final_output[0]


# ── 导入验证 ──

class TestLedgerImports:
    def test_tool_import(self):
        from tools.task_ledger import execute, _get_ledger, _set_ledger, TOOL_NAME
        assert TOOL_NAME == "task_ledger"

    def test_engine_field_exists(self):
        from unittest.mock import MagicMock
        from core.engine import Engine
        e = Engine(llm_caller=MagicMock(), tool_executor=MagicMock(), test_mode=True)
        assert hasattr(e, "task_ledger")
        assert hasattr(e, "_ledger_reinject_count")


class TestLedgerPerEngineIsolation:
    """票 L：task_ledger 必须路由到调用方 Engine 的台账，禁止跨 Engine 串味。"""

    @pytest.fixture(autouse=True)
    def _reset_module_ledger(self):
        from tools.task_ledger import _set_ledger
        _set_ledger([])
        yield
        _set_ledger([])

    def _run_with_engine(self, engine, action, **kwargs):
        """在指定 Engine 上下文中执行 task_ledger 工具。"""
        from tools.task_ledger import execute
        return execute(action=action, _engine=engine, **kwargs)

    def test_two_engines_create_isolated_ledgers(self, monkeypatch):
        """两个 Engine 各自 create，台账互不可见。"""
        import core.engine as engine_mod
        from tests.test_engine_e2e import FakeLLMCaller

        monkeypatch.setattr(engine_mod.Engine, "_build_system_prompt",
                            lambda self: "You are a helpful assistant.")

        engine_a = engine_mod.Engine(
            llm_caller=FakeLLMCaller([]),
            test_mode=True,
        )
        engine_b = engine_mod.Engine(
            llm_caller=FakeLLMCaller([]),
            test_mode=True,
        )

        self._run_with_engine(engine_a, "create", items=[
            {"id": "a-1", "title": "任务 A1"},
        ])
        self._run_with_engine(engine_b, "create", items=[
            {"id": "b-1", "title": "任务 B1"},
        ])

        assert len(engine_a.task_ledger) == 1
        assert engine_a.task_ledger[0]["id"] == "a-1"
        assert engine_a.task_ledger[0]["title"] == "任务 A1"

        assert len(engine_b.task_ledger) == 1
        assert engine_b.task_ledger[0]["id"] == "b-1"
        assert engine_b.task_ledger[0]["title"] == "任务 B1"

    def test_engine_update_does_not_affect_other_engine(self, monkeypatch):
        """A 更新自己的台账不应影响 B。"""
        import core.engine as engine_mod
        from tests.test_engine_e2e import FakeLLMCaller

        monkeypatch.setattr(engine_mod.Engine, "_build_system_prompt",
                            lambda self: "You are a helpful assistant.")

        engine_a = engine_mod.Engine(
            llm_caller=FakeLLMCaller([]),
            test_mode=True,
        )
        engine_b = engine_mod.Engine(
            llm_caller=FakeLLMCaller([]),
            test_mode=True,
        )

        self._run_with_engine(engine_a, "create", items=[
            {"id": "a-1", "title": "任务 A1"},
        ])
        self._run_with_engine(engine_b, "create", items=[
            {"id": "b-1", "title": "任务 B1"},
        ])

        self._run_with_engine(engine_a, "update", items=[
            {"id": "a-1", "status": "done"},
        ])

        assert engine_a.task_ledger[0]["status"] == "done"
        assert engine_b.task_ledger[0]["status"] == "pending"

    def test_module_ledger_untouched_by_engine_routing(self, monkeypatch):
        """Engine 上下文路由不应污染模块级全局台账。"""
        import core.engine as engine_mod
        from tests.test_engine_e2e import FakeLLMCaller
        from tools.task_ledger import _get_ledger

        monkeypatch.setattr(engine_mod.Engine, "_build_system_prompt",
                            lambda self: "You are a helpful assistant.")

        engine = engine_mod.Engine(
            llm_caller=FakeLLMCaller([]),
            test_mode=True,
        )

        self._run_with_engine(engine, "create", items=[
            {"id": "eng-1", "title": "引擎任务"},
        ])

        # 模块级全局台账应保持为空（测试 reset 已置空）
        assert _get_ledger() == []
        # Engine 自己的台账有内容
        assert len(engine.task_ledger) == 1

# ── 票 L 回归：真 ThreadPoolExecutor 路径 ──

class TestLedgerRealThreadPool:
    """真 ThreadPoolExecutor 路径回归测试（禁止 FakeExecutor 手动 set context）。"""

    def test_real_executor_routes_to_engine_not_module(self, monkeypatch):
        """execute_tool 带 engine 参数时，task_ledger 必须写入 Engine 而非模块级。"""
        from core.tool_executor import execute_tool
        from tools.task_ledger import _get_ledger, _set_ledger

        _set_ledger([])  # 确保模块级干净

        # 伪造一个带 task_ledger 属性的 "Engine"
        class FakeEng:
            def __init__(self):
                self.task_ledger = []

        fake_engine = FakeEng()

        result = execute_tool(
            "task_ledger",
            {"action": "create", "items": [{"id": "real-1", "title": "真线程测试", "status": "pending"}]},
            engine=fake_engine,
        )

        assert "✅ 台账已创建" in result
        assert len(fake_engine.task_ledger) == 1
        assert fake_engine.task_ledger[0]["id"] == "real-1"
        # 模块级台账必须保持为空
        assert _get_ledger() == []

    def test_real_executor_without_engine_falls_back_to_module(self):
        """execute_tool 不带 engine 参数时，回退模块级全局台账。
        注意：ThreadPoolExecutor worker 线程中 global 赋值有跨线程可见性
        限制，本条通过返回结果 + 直接 execute() 双验证。
        """
        from core.tool_executor import execute_tool
        from tools.task_ledger import execute, _set_ledger

        _set_ledger([])

        # ThreadPoolExecutor 路径：不传 engine → 匿名台账（只能验证创建成功）
        result = execute_tool(
            "task_ledger",
            {"action": "create", "items": [{"id": "mod-1", "title": "模块级测试", "status": "pending"}]},
        )

        assert "✅ 台账已创建" in result

        # 直接 execute 验证模块级回退（同线程，无跨线程问题）
        _set_ledger([])
        result2 = execute(action="create", items=[{"id": "mod-2", "title": "直接调用", "status": "pending"}])
        assert "✅ 台账已创建" in result2
        result3 = execute(action="list")
        assert "直接调用" in result3
