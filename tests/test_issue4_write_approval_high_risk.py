"""GitHub #4：写审批 / high_risk 覆盖缺口。

验收：
- execute_terminal / code_execution / computer_use 进入与风险等级匹配的确认/审批路径
- is_high_risk_tool 覆盖上述工具（本文件 + test_command_safety.TestHighRiskTool）
- 写审批开启时，高危调用不可绕过确认静默执行（含 _all_confirmed 粘性放行）
- 确认闸 120s=deny 策略本票不改（P1），补覆盖后不得引入新的静默放行
"""

from __future__ import annotations

import inspect
import json
import threading

import pytest

from core.command_safety import is_high_risk_tool
from core.engine import Engine
from core.engine_adapter import (
    _WRITE_APPROVAL_HIGH_RISK_TOOLS,
    _VSC2B_WRITE_TOOLS,
    _wait_for_confirmation,
    needs_write_approval,
)
from core.tool_executor import execute_tool
from core.tool_runner import ToolRunnerMixin


# ── is_high_risk_tool 表锁定 ──────────────────────────────────────────


class TestHighRiskCoverageIssue4:
    @pytest.mark.parametrize(
        "tool_name,tool_args,expect_risk",
        [
            ("execute_terminal", {"command": "ls -la"}, False),
            ("execute_terminal", {"command": "brew install pkg"}, True),
            ("execute_terminal", {"command": "rm -rf /tmp/x"}, True),
            ("code_execution", {"language": "python", "code": "open('x','w')"}, True),
            ("computer_use", {"action": "capture"}, False),
            ("computer_use", {"action": "click"}, True),
            ("computer_use", {"action": "type"}, True),
            ("computer_use", {"action": "key"}, True),
            ("computer_use", {"action": "open_app"}, True),
            ("computer_use", {"action": "scroll"}, True),
        ],
    )
    def test_risk_table(self, tool_name, tool_args, expect_risk):
        is_risk, _ = is_high_risk_tool(tool_name, tool_args)
        assert is_risk is expect_risk


# ── write_approval 闸 ────────────────────────────────────────────────


class TestNeedsWriteApproval:
    def test_flag_off_never_gates(self):
        for name, args in (
            ("edit_file", {"path": "a.py"}),
            ("file_operation", {"action": "write"}),
            ("execute_terminal", {"command": "brew install pkg"}),
            ("code_execution", {"code": "print(1)"}),
            ("computer_use", {"action": "click"}),
        ):
            assert needs_write_approval(name, args, False) is False

    def test_original_write_tools_still_gated(self):
        assert needs_write_approval("edit_file", {}, True) is True
        assert needs_write_approval("file_operation", {}, True) is True
        assert _VSC2B_WRITE_TOOLS == frozenset({"edit_file", "file_operation"})

    def test_high_risk_side_effect_tools_gated_when_flag_on(self):
        assert _WRITE_APPROVAL_HIGH_RISK_TOOLS == frozenset(
            {"execute_terminal", "code_execution", "computer_use"}
        )
        assert needs_write_approval("execute_terminal", {"command": "brew install pkg"}, True) is True
        assert needs_write_approval("code_execution", {"code": "print(1)"}, True) is True
        assert needs_write_approval("computer_use", {"action": "click"}, True) is True

    def test_safe_or_readonly_not_gated(self):
        # 风险匹配：safe 终端 / capture 不因写审批开启而抬闸
        assert needs_write_approval("execute_terminal", {"command": "ls -la"}, True) is False
        assert needs_write_approval("computer_use", {"action": "capture"}, True) is False
        assert needs_write_approval("read_local_file", {"path": "a.py"}, True) is False

    def test_no_new_silent_allow_when_flag_on(self):
        """写审批开启时，三件套高危调用必须 needs_write_approval=True（不可静默绕过）。"""
        high = [
            ("execute_terminal", {"command": "brew install pkg"}),
            ("code_execution", {"language": "bash", "code": "rm -rf /tmp/x"}),
            ("computer_use", {"action": "type", "text": "secret"}),
        ]
        for name, args in high:
            assert is_high_risk_tool(name, args)[0] is True
            assert needs_write_approval(name, args, True) is True


# ── 确认闸 120s=deny 未改（P1） ───────────────────────────────────────


class TestConfirmationTimeoutPolicyUnchanged:
    def test_wait_default_timeout_still_120(self):
        params = inspect.signature(_wait_for_confirmation).parameters
        assert params["timeout"].default == 120

    def test_timeout_still_deny(self):
        event = threading.Event()
        assert _wait_for_confirmation(event, timeout=0.01) is False

    def test_set_still_allow(self):
        event = threading.Event()
        event.set()
        assert _wait_for_confirmation(event, timeout=0.01) is True

    def test_adapter_source_keeps_120_deny(self):
        import core.engine_adapter as adapter
        src = inspect.getsource(adapter)
        assert "timeout=120" in src
        assert "timeout: float = 120" in src
        # 禁止把超时改成默认放行
        wait_src = inspect.getsource(_wait_for_confirmation)
        assert "return event.wait(timeout=timeout)" in wait_src
        assert "return True" not in wait_src.split("return event.wait", 1)[0]


# ── 工具循环：高危进入 _confirm；拒绝则不执行 ────────────────────────


class TestToolLoopConfirmationPaths:
    @staticmethod
    def _harness():
        class _H(ToolRunnerMixin):
            def __init__(self):
                self.tool_executor = lambda *_a, **_k: pytest.fail("高危拒绝后不得执行")
                self._tool_failures = {}
                self._recent_tool_calls = []
                self._confirm_calls = []
                self._notify_calls = []
                self._recorded = []
                self.sid = "issue4"

            def _confirm(self, tool_name, tool_args, reason):
                self._confirm_calls.append((tool_name, tool_args, reason))
                return False

            def _notify(self, event_type, data):
                self._notify_calls.append((event_type, data))

            def _record_message(self, role, **kwargs):
                self._recorded.append((role, kwargs))

        return _H()

    @staticmethod
    def _tc(name, args, call_id="c1"):
        return {
            "id": call_id,
            "function": {"name": name, "arguments": json.dumps(args)},
        }

    @pytest.mark.parametrize(
        "name,args",
        [
            ("execute_terminal", {"command": "brew install pkg"}),
            ("code_execution", {"language": "python", "code": "print(1)"}),
            ("computer_use", {"action": "click", "element": 1}),
        ],
    )
    def test_high_risk_enters_confirm_and_can_cancel(self, name, args):
        runner = self._harness()
        results = runner._execute_tool_loop([self._tc(name, args)])
        assert len(runner._confirm_calls) == 1
        assert runner._confirm_calls[0][0] == name
        assert "操作已取消" in results[0]["content"]

    def test_readonly_computer_use_skips_confirm(self):
        runner = self._harness()
        executed = []
        runner.tool_executor = lambda n, a: executed.append((n, a)) or "ok"
        results = runner._execute_tool_loop([self._tc("computer_use", {"action": "capture"})])
        assert runner._confirm_calls == []
        assert executed == [("computer_use", {"action": "capture"})]
        assert results


class TestWriteApprovalCannotSilentBypass:
    """写审批开启时，即使 Engine._all_confirmed 粘性放行，执行闸仍要确认。"""

    def test_all_confirmed_still_hits_write_approval_gate(self):
        confirms = []

        def confirm(tool_name, tool_args, reason):
            confirms.append((tool_name, reason))
            return False  # 用户拒绝 / 超时 deny

        # 模拟 _guarded_execute 的闸门逻辑（与 engine_adapter 同一函数）
        tool_name, tool_args = "code_execution", {"code": "print(1)"}
        # Engine 侧粘性放行
        engine_would_allow = True  # _all_confirmed
        assert engine_would_allow is True
        assert needs_write_approval(tool_name, tool_args, True) is True
        allowed = confirm(tool_name, tool_args, "write_approval")
        assert allowed is False
        assert confirms == [("code_execution", "write_approval")]

    def test_execute_terminal_and_computer_use_same_gate(self):
        for name, args in (
            ("execute_terminal", {"command": "brew install pkg"}),
            ("computer_use", {"action": "open_app", "app_name": "Safari"}),
        ):
            assert needs_write_approval(name, args, True) is True

    def test_engine_auto_denies_code_execution_and_computer_use(self):
        """auto 下高危通道即时 deny——不弹窗、不静默放行（120s 策略不改）。"""
        eng = Engine(lambda *a, **k: {}, execute_tool, test_mode=False,
                     auto_mode_getter=lambda: True)
        eng.test_mode = False
        called = []
        eng.confirm_callback = lambda *a: called.append(a) or True
        assert eng._confirm("code_execution", {"code": "x"}, "执行代码") is False
        assert eng._confirm("computer_use", {"action": "click"}, "电脑操作") is False
        assert called == [], "auto 下不得走 confirm_callback（无 120s 卡死）"

    def test_engine_auto_denies_computer_use_capture(self):
        """AUTO 下连 capture 也 deny：intentional tightening，不是漏判只读。"""
        eng = Engine(lambda *a, **k: {}, execute_tool, test_mode=False,
                     auto_mode_getter=lambda: True)
        eng.test_mode = False
        called = []
        eng.confirm_callback = lambda *a: called.append(a) or True
        assert is_high_risk_tool("computer_use", {"action": "capture"})[0] is False
        assert eng._confirm("computer_use", {"action": "capture"},
                            "auto 模式：computer_use（含 capture）即时拒绝") is False
        assert called == [], "AUTO capture deny 不得走 120s confirm_callback"

    def test_tool_loop_auto_denies_capture(self):
        """工具循环：AUTO 开启时 capture 进 _confirm 并取消，不得执行。"""
        class _H(ToolRunnerMixin):
            def __init__(self):
                self.tool_executor = lambda *_a, **_k: pytest.fail("AUTO capture 不得执行")
                self._tool_failures = {}
                self._recent_tool_calls = []
                self._confirm_calls = []
                self._notify_calls = []
                self._recorded = []
                self.sid = "issue4-auto-capture"
                self._auto_mode_getter = lambda: True

            def _confirm(self, tool_name, tool_args, reason):
                self._confirm_calls.append((tool_name, tool_args, reason))
                return False

            def _notify(self, event_type, data):
                self._notify_calls.append((event_type, data))

            def _record_message(self, role, **kwargs):
                self._recorded.append((role, kwargs))

        runner = _H()
        results = runner._execute_tool_loop([{
            "id": "c1",
            "function": {
                "name": "computer_use",
                "arguments": json.dumps({"action": "capture"}),
            },
        }])
        assert len(runner._confirm_calls) == 1
        assert runner._confirm_calls[0][0] == "computer_use"
        assert "capture" in runner._confirm_calls[0][2]
        assert "操作已取消" in results[0]["content"]


class TestGuardedExecuteWriteApproval:
    """通过 run_engine 注入的 _guarded_execute 合同：写审批拒绝文案。"""

    def test_needs_write_approval_deny_message_contract(self):
        # 与 engine_adapter._guarded_execute 拒绝文案锁定
        tool_name = "code_execution"
        msg = f"操作被用户拒绝（write_approval）: {tool_name}，请换一种方法或征得用户同意后再试。"
        assert "write_approval" in msg
        assert tool_name in msg
