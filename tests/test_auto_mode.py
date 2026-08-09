"""票 A：AUTO MODE 语义改造测试。

覆盖：
1. is_auto_readonly_command 纯读判定（含逐段判定，火 4）
2. Engine._confirm 决策树顺序（test_mode → auto → _all_confirmed → 原流程）
3. auto 决策树 v1：纯读 git 放行 + 写命令走弹窗
4. auto 关闭时行为零变化（回归断言，v0.6 验收纪律）
5. /auto slash 命令翻转（gateway 层）
"""

import json
import pytest
from core.engine import Engine
from core.command_safety import is_auto_readonly_command, is_high_risk_tool
from core.tool_executor import execute_tool
from core.event_bus import event_bus


@pytest.fixture
def engine():
    """构造非 test_mode 的 Engine（pytest 下 test_mode 默认 True，需显式关闭）。"""
    from tests.mock_llm import MockLLMCaller, text_response
    caller = MockLLMCaller([text_response("ok")])
    eng = Engine(caller, execute_tool, test_mode=False)
    eng.test_mode = False  # pytest 环境强制覆盖，确保测到 _confirm 全流程
    return eng


# ── 1. is_auto_readonly_command 纯读判定 ──

class TestAutoReadonlyCommand:
    READONLY = [
        "git status",
        "git status --short",
        "git log --oneline -5",
        "git log --grep=push",       # 参数含 push 字样不误伤（只读子命令无破坏性操作）
        "git diff HEAD~1",
        "git diff --cached",
        "git show abc123",
        "git blame main.py",
        "git ls-files",
        "git ls-tree HEAD",
        "git -C /tmp/repo status",   # 全局选项 -C 跳过
        "git --no-pager log -3",     # 全局选项 --no-pager 跳过
        "git status && echo ok",     # 验收 3：链式但各段只读 → 放行（git 只读 + echo safe）
        "ls -la",                    # classify safe 段
        "cat README.md",             # classify safe 段
    ]
    NOT_READONLY = [
        "git commit -m fix",         # 写操作
        "git add .",
        "git push",
        "git push origin main",
        "git reset --hard HEAD~1",
        "git clean -fd",
        "git rebase main",
        "git merge feature",
        "git checkout -b new-branch",
        "git branch -d old-branch",
        "git status && rm -rf x",    # 验收 3：链式含危险段 → 不放行（火 4）
        "echo hi && git push",       # echo safe 但 git push 段非只读 → 整条不放行
        "git log; git push",
        "rm -rf /",                  # 非只读（dangerous）
    ]

    @pytest.mark.parametrize("cmd", READONLY)
    def test_readonly_commands(self, cmd):
        assert is_auto_readonly_command(cmd) is True, f"应放行: {cmd}"

    @pytest.mark.parametrize("cmd", NOT_READONLY)
    def test_non_readonly_commands(self, cmd):
        assert is_auto_readonly_command(cmd) is False, f"不应放行: {cmd}"

    def test_unbalanced_quotes_conservative(self):
        # 解析失败 → 不放行（保守，安全默认）
        assert is_auto_readonly_command('git log "unclosed') is False

    def test_empty_command(self):
        assert is_auto_readonly_command("") is False
        assert is_auto_readonly_command("   ") is False


# ── 2. Engine._confirm 决策树顺序 ──

class TestConfirmDecisionTree:
    def test_test_mode_short_circuits(self, engine):
        """test_mode 优先：即使 auto 开也直接放行，不调 callback。"""
        calls = []
        engine.test_mode = True
        engine._auto_mode_getter = lambda: True
        engine.confirm_callback = lambda *a: calls.append(a) or False
        assert engine._confirm("execute_terminal", {"command": "rm -rf /"}, "x") is True
        assert calls == []

    def test_auto_readonly_git_allowed(self, engine):
        """auto 开 + 纯读 git → 直接放行，不调 callback。"""
        engine._auto_mode_getter = lambda: True
        engine.confirm_callback = lambda *a: pytest.fail("纯读命令不应弹窗")
        assert engine._confirm("execute_terminal", {"command": "git status"}, "gray") is True

    def test_auto_write_command_goes_to_callback(self, engine):
        """auto 开 + external-irreversible 写命令 → 走 confirm_callback（票 B 弹窗）。"""
        engine._auto_mode_getter = lambda: True
        engine.confirm_callback = lambda *a: False
        # git commit 自票 B 起为 local-reversible 快照放行；git push（外部不可逆）才弹窗
        assert engine._confirm("execute_terminal", {"command": "git push"}, "gray") is False

    def test_auto_chain_with_destructive_tail_not_allowed(self, engine):
        """auto 开 + git status && rm -rf x → 逐段判定不放行，走 callback。"""
        engine._auto_mode_getter = lambda: True
        engine.confirm_callback = lambda *a: False
        assert engine._confirm("execute_terminal", {"command": "git status && rm -rf x"}, "gray") is False

    def test_auto_branch_before_all_confirmed(self, engine):
        """火 A-2：auto 分支必须排在 _all_confirmed 之前——
        用户点过 always 后，auto 下写命令仍必须走风险评估（callback），
        不能因 _all_confirmed=True 直接放行。"""
        engine._auto_mode_getter = lambda: True
        engine._all_confirmed = True  # 模拟用户之前点过 always
        engine.confirm_callback = lambda *a: False  # 弹窗被拒
        # 写命令：若 _all_confirmed 优先会直接 True，这里必须走 callback → False
        assert engine._confirm("execute_terminal", {"command": "git push"}, "gray") is False

    def test_non_terminal_tool_in_auto_goes_to_callback(self, engine):
        """auto 开 + 非 terminal 灰名单工具（如 delete_note）→ 走 callback。"""
        engine._auto_mode_getter = lambda: True
        engine.confirm_callback = lambda *a: True
        assert engine._confirm("delete_note", {"filename": "x.md"}, "文件操作") is True


# ── 3. auto 关闭时行为零变化（回归断言，v0.6 验收纪律） ──

class TestAutoOffRegression:
    def test_all_confirmed_still_short_circuits(self, engine):
        """auto 关 + _all_confirmed=True → 直接放行，不调 callback（原逻辑）。"""
        engine._auto_mode_getter = lambda: False
        engine._all_confirmed = True
        engine.confirm_callback = lambda *a: pytest.fail("_all_confirmed 短路不应调 callback")
        assert engine._confirm("execute_terminal", {"command": "git push"}, "gray") is True

    def test_callback_still_called_when_not_confirmed(self, engine):
        """auto 关 + 无 _all_confirmed → 原确认流程（callback 被调）。"""
        engine._auto_mode_getter = lambda: False
        engine._all_confirmed = False
        engine.confirm_callback = lambda *a: True
        assert engine._confirm("execute_terminal", {"command": "git push"}, "gray") is True

    def test_no_callback_returns_false(self, engine):
        """auto 关 + 无 callback → False（原逻辑）。"""
        engine._auto_mode_getter = lambda: False
        engine.confirm_callback = None
        assert engine._confirm("execute_terminal", {"command": "git push"}, "gray") is False

    def test_auto_mode_getter_none_defaults_to_off(self, engine):
        """auto_mode_getter 未注入（None）→ 等同 auto 关，走原流程。"""
        engine._auto_mode_getter = None
        engine._all_confirmed = False
        engine.confirm_callback = lambda *a: True
        assert engine._confirm("execute_terminal", {"command": "git push"}, "gray") is True


# ── 4. auto 决策审计事件 ──

class TestAutoAudit:
    def test_auto_allow_writes_audit_event(self, engine, tmp_path):
        """auto 放行纯读命令 → events.jsonl 写 auto.decide，字段对齐票文（verdict/sid）。"""
        from core.event_bus import EventBus
        EventBus.reset(log_dir=str(tmp_path))
        engine.sid = "test_sid_001"
        engine._auto_mode_getter = lambda: True
        engine.confirm_callback = lambda *a: pytest.fail("纯读不应弹窗")
        assert engine._confirm("execute_terminal", {"command": "git status"}, "gray") is True

        lines = [json.loads(l) for l in (tmp_path / "events.jsonl").read_text().splitlines()]
        auto_events = [e for e in lines if e.get("type") == "auto.decide"]
        assert auto_events, "应写入 auto.decide 审计事件"
        # _build_event 把 data 展开成顶层字段（{"ts","type",**_data}）
        assert auto_events[0]["auto"] is True
        assert auto_events[0]["verdict"] == "allow"
        assert auto_events[0]["sid"] == "test_sid_001"
        assert auto_events[0]["command"] == "git status"

    def test_auto_deny_writes_audit_event(self, engine, tmp_path):
        """auto 拒绝写命令 → events.jsonl 写 auto.decide verdict=deny。"""
        from core.event_bus import EventBus
        EventBus.reset(log_dir=str(tmp_path))
        engine.sid = "test_sid_002"
        engine._auto_mode_getter = lambda: True
        engine.confirm_callback = lambda *a: False  # 弹窗被拒（external-irreversible）
        assert engine._confirm("execute_terminal", {"command": "git push"}, "gray") is False

        lines = [json.loads(l) for l in (tmp_path / "events.jsonl").read_text().splitlines()]
        auto_events = [e for e in lines if e.get("type") == "auto.decide"]
        assert auto_events, "拒绝也应写入审计事件"
        # 顺序：先 escalated（转交弹窗留痕），后 deny（拒绝留痕）
        denied = [e for e in auto_events if e.get("verdict") == "deny"]
        assert denied and denied[0]["auto"] is True


# ── 5. /auto slash 命令（gateway 层） ──

class TestAutoSlashCommand:
    @pytest.fixture
    def ctx(self):
        from bobo_tui_gateway.server import _ServerContext
        return _ServerContext()

    def _exec(self, ctx, sid, command):
        from bobo_tui_gateway.handlers.prompts import handle_slash_exec
        return handle_slash_exec({"command": command, "session_id": sid}, "rid1", ctx)

    def test_auto_toggles_on(self, ctx):
        sid = "s1"
        r = self._exec(ctx, sid, "auto")
        assert ctx.auto_mode.get(sid) is True
        assert "开启" in r["result"]["output"]

    def test_auto_toggles_off(self, ctx):
        sid = "s2"
        ctx.auto_mode[sid] = True
        r = self._exec(ctx, sid, "auto")
        assert ctx.auto_mode.get(sid) is False
        assert "关闭" in r["result"]["output"]

    def test_auto_on_explicit(self, ctx):
        sid = "s3"
        self._exec(ctx, sid, "auto on")
        assert ctx.auto_mode.get(sid) is True

    def test_auto_off_explicit(self, ctx):
        sid = "s4"
        ctx.auto_mode[sid] = True
        self._exec(ctx, sid, "auto off")
        assert ctx.auto_mode.get(sid) is False

    def test_auto_is_session_scoped(self, ctx):
        """会话级：一个会话翻转不影响另一个会话。"""
        self._exec(ctx, "s5", "auto on")
        assert ctx.auto_mode.get("s6", False) is False

    def test_auto_registered_in_catalog(self):
        from bobo_tui_gateway.handlers.prompts import _COMMANDS
        assert "/auto" in _COMMANDS["canon"]
