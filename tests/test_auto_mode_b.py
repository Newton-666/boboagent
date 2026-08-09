"""票 B：灰名单风险评估与命令回滚测试。

覆盖（验收口径）：
1. 副作用三级分类：git status→放行；git commit→快照后放行；git push→弹窗
2. 逐段判定：`git add . && git commit -m x`→快照放行；`git commit && git push`→弹窗
3. 快照时序：快照在决策阶段完成（_confirm 返回时审计已含 snapshot_ref，且不弹窗）
4. 超时 deny：_wait_for_confirmation 超时返回 False（钉死）+ 拒绝留痕
5. auto 关闭时行为零变化回归断言
6. 决策树顺序不破坏（test_mode → auto → _all_confirmed）
7. 审计事件四新字段齐全（side_effect_level / snapshot_ref / rollback_path / verdict=escalated）
8. 全量回归（基线 1629/2）
"""

import json
import threading
import pytest
from core.engine import Engine
from core.command_safety import classify_side_effect
from core.event_bus import EventBus
from core.engine_adapter import _wait_for_confirmation


@pytest.fixture
def engine():
    """构造非 test_mode 的 Engine（pytest 下 test_mode 默认 True，需显式关闭）。"""
    from tests.mock_llm import MockLLMCaller, text_response
    caller = MockLLMCaller([text_response("ok")])
    from core.tool_executor import execute_tool
    eng = Engine(caller, execute_tool, test_mode=False)
    eng.test_mode = False
    return eng


# ── 1. 副作用三级分类（B-1） ──

class TestSideEffectClassification:
    PURE_READ = [
        "git status",
        "git log --oneline -3",
        "git diff HEAD",
        "ls -la",
        "cat README.md",
        "git status && echo ok",
    ]
    LOCAL_REVERSIBLE = [
        "git commit -m fix",
        "git add .",
        "git checkout -b feat/x",
        "git stash",
        "mkdir newdir",
        "pip install requests",
        "git add . && git commit -m x",
    ]
    EXTERNAL_IRREVERSIBLE = [
        "git push",
        "git push origin main",
        "npm publish",
        "scp a.txt user@host:/tmp",
        "curl -X POST http://api.example.com/data",
        "git commit && git push",
        "git status && rm -rf x",
    ]

    @pytest.mark.parametrize("cmd", PURE_READ)
    def test_pure_read(self, cmd):
        level, _ = classify_side_effect(cmd)
        assert level == "pure-read", f"{cmd} 应为 pure-read"

    @pytest.mark.parametrize("cmd", LOCAL_REVERSIBLE)
    def test_local_reversible(self, cmd):
        level, _ = classify_side_effect(cmd)
        assert level == "local-reversible", f"{cmd} 应为 local-reversible"

    @pytest.mark.parametrize("cmd", EXTERNAL_IRREVERSIBLE)
    def test_external_irreversible(self, cmd):
        level, _ = classify_side_effect(cmd)
        assert level == "external-irreversible", f"{cmd} 应为 external-irreversible"

    def test_chain_any_external_escalates_whole(self):
        """验收 2：`git commit && git push` 整条 external-irreversible（防整链误放）。"""
        assert classify_side_effect("git commit && git push")[0] == "external-irreversible"

    def test_chain_local_allowed_with_snapshot(self):
        """验收 2：`git add . && git commit -m x` 整条 local-reversible。"""
        assert classify_side_effect("git add . && git commit -m x")[0] == "local-reversible"


# ── 2/3. engine 级：三级行为 + 快照时序（B-2） ──

class TestAutoDecideV2:
    def test_git_status_allow_no_popup(self, engine):
        """验收 1：git status → 直接放行，不弹窗。"""
        engine._auto_mode_getter = lambda: True
        engine.confirm_callback = lambda *a: pytest.fail("pure-read 不应弹窗")
        assert engine._confirm("execute_terminal", {"command": "git status"}, "gray") is True

    def test_git_commit_snapshot_then_allow(self, engine, tmp_path):
        """验收 1+3：git commit → 决策时刻快照后放行（不弹窗，审计含 snapshot_ref）。"""
        EventBus.reset(log_dir=str(tmp_path))
        engine.sid = "b_sid_commit"
        engine._auto_mode_getter = lambda: True
        engine.confirm_callback = lambda *a: pytest.fail("local-reversible 不应弹窗（快照放行）")
        assert engine._confirm("execute_terminal", {"command": "git commit -m fix"}, "gray") is True

        lines = [json.loads(l) for l in (tmp_path / "events.jsonl").read_text().splitlines()]
        ev = [e for e in lines if e.get("type") == "auto.decide"][0]
        # 快照在决策阶段完成：_confirm 返回时审计已落 snapshot_ref（phase 1 串行，非执行线程）
        assert ev["verdict"] == "allow"
        assert ev["side_effect_level"] == "local-reversible"
        assert ev["snapshot_ref"], "快照引用必须在决策时刻写入审计"
        assert ev["rollback_path"], "回滚路径必须在决策时刻写入审计"
        assert ev["snapshot_ref"].startswith("HEAD="), "git 快照应记录 HEAD 摘要"

    def test_git_push_escalates_popup(self, engine, tmp_path):
        """验收 1：git push → 转弹窗（escalated 留痕），弹窗拒绝 → deny 留痕。"""
        EventBus.reset(log_dir=str(tmp_path))
        engine.sid = "b_sid_push"
        engine._auto_mode_getter = lambda: True
        engine.confirm_callback = lambda *a: False  # 模拟无人应答/拒绝
        assert engine._confirm("execute_terminal", {"command": "git push"}, "gray") is False

        lines = [json.loads(l) for l in (tmp_path / "events.jsonl").read_text().splitlines()]
        events = [e for e in lines if e.get("type") == "auto.decide"]
        escalated = [e for e in events if e.get("verdict") == "escalated"]
        denied = [e for e in events if e.get("verdict") == "deny"]
        assert escalated, "弹窗转交必须留痕 verdict=escalated"
        assert escalated[0]["side_effect_level"] == "external-irreversible"
        assert denied, "拒绝必须留痕 verdict=deny"
        assert "外部不可逆" in denied[0]["reason"]

    def test_snapshot_not_in_execution_thread(self, engine, monkeypatch):
        """验收 3 强化：快照调用发生在决策路径内（_confirm 返回前完成，无执行线程介入）。"""
        engine._auto_mode_getter = lambda: True
        engine.confirm_callback = lambda *a: pytest.fail("不应弹窗")
        snapshot_called = []
        monkeypatch.setattr(engine, "_snapshot_for_rollback",
                            lambda cmd: (snapshot_called.append(cmd), {
                                "kind": "git", "ref": "HEAD=abc", "rollback": "reset"})[1])
        assert engine._confirm("execute_terminal", {"command": "git commit -m x"}, "gray") is True
        assert snapshot_called, "快照必须在决策阶段（_confirm 内）被调用"


# ── 4. 超时 deny（B-3） ──

class TestTimeoutDeny:
    def test_wait_for_confirmation_timeout_is_false(self):
        """验收 4：钉死超时行为——无人应答 → event.wait 超时 → False（安全默认 deny）。"""
        event = threading.Event()  # 永不 set，模拟无人应答
        assert _wait_for_confirmation(event, timeout=0.01) is False

    def test_wait_for_confirmation_set_is_true(self):
        """对照：用户确认（set）→ True，不误伤正常确认路径。"""
        event = threading.Event()
        event.set()
        assert _wait_for_confirmation(event, timeout=0.01) is True

    def test_timeout_deny_leaves_audit(self, engine, tmp_path):
        """验收 4：超时拒绝留痕（reason 明示外部不可逆未获确认）。"""
        EventBus.reset(log_dir=str(tmp_path))
        engine.sid = "b_sid_timeout"
        engine._auto_mode_getter = lambda: True
        engine.confirm_callback = lambda *a: False  # 模拟 _wait_for_confirmation 超时 → False
        assert engine._confirm("execute_terminal", {"command": "git push"}, "gray") is False

        lines = [json.loads(l) for l in (tmp_path / "events.jsonl").read_text().splitlines()]
        denied = [e for e in lines if e.get("type") == "auto.decide" and e.get("verdict") == "deny"]
        assert denied and "未获确认" in denied[0]["reason"]


# ── 5. auto 关闭零变化回归（强制） ──

class TestAutoOffRegressionB:
    def test_auto_off_git_status_popup_as_before(self, engine):
        """验收 5：auto 关（getter=None）→ git status 也走原弹窗流程（行为与现状一致）。"""
        engine._auto_mode_getter = None
        calls = []
        engine.confirm_callback = lambda *a: calls.append(a) or True
        assert engine._confirm("execute_terminal", {"command": "git status"}, "gray") is True
        assert calls, "auto 关时必须走 confirm_callback（原流程）"

    def test_auto_off_git_commit_popup_as_before(self, engine):
        engine._auto_mode_getter = None
        calls = []
        engine.confirm_callback = lambda *a: calls.append(a) or True
        assert engine._confirm("execute_terminal", {"command": "git commit -m x"}, "gray") is True
        assert calls

    def test_auto_off_git_push_popup_as_before(self, engine):
        engine._auto_mode_getter = None
        calls = []
        engine.confirm_callback = lambda *a: calls.append(a) or True
        assert engine._confirm("execute_terminal", {"command": "git push"}, "gray") is True
        assert calls


# ── 6. 决策树顺序不破坏 ──

class TestOrderNotBroken:
    def test_test_mode_short_circuits_auto_b(self, engine):
        """验收 6：test_mode 下 auto 开关无效（第一行短路）。"""
        engine.test_mode = True
        engine._auto_mode_getter = lambda: True
        engine.confirm_callback = lambda *a: pytest.fail("test_mode 不应走 auto/弹窗")
        assert engine._confirm("execute_terminal", {"command": "git push"}, "gray") is True

    def test_auto_branch_before_all_confirmed_b(self, engine):
        """验收 6：auto 分支仍在 _all_confirmed 之前。"""
        engine._auto_mode_getter = lambda: True
        engine._all_confirmed = True
        engine.confirm_callback = lambda *a: pytest.fail("auto 分支应先于 _all_confirmed")
        assert engine._confirm("execute_terminal", {"command": "git status"}, "gray") is True

    def test_all_confirmed_auto_off_b(self, engine):
        """验收 6：auto 关 + _all_confirmed=true → 直接放行（原行为）。"""
        engine._auto_mode_getter = None
        engine._all_confirmed = True
        engine.confirm_callback = lambda *a: pytest.fail("_all_confirmed 不应再弹窗")
        assert engine._confirm("execute_terminal", {"command": "git push"}, "gray") is True


# ── 8. 危险黑名单最高优先级：命令替换注入钉死 ──

class TestDangerousHighestPriority:
    """命令替换注入（$( / 反引号）在任何模式下都不得 pure-read 放行。"""
    INJECTIONS = [
        "echo $(rm -rf x)",      # echo 白名单 + 命令替换注入
        "echo `id`",             # echo 白名单 + 反引号注入
        "cat $(whoami)",         # cat 白名单 + 命令替换注入
        "cat `ls /etc`",         # cat 白名单 + 反引号注入
        "git status && echo $(rm -rf x)",  # 链式：首段只读但注入段非只读
    ]

    @pytest.mark.parametrize("cmd", INJECTIONS)
    def test_classify_side_effect_never_pure_read(self, cmd):
        """classify_side_effect：注入命令不得判 pure-read，必须 external-irreversible。"""
        level, reason = classify_side_effect(cmd)
        assert level == "external-irreversible", f"{cmd} 必须转弹窗，实得 {level}（{reason}）"
        assert "危险黑名单" in reason, f"{cmd} 原因应指向危险黑名单"

    @pytest.mark.parametrize("cmd", INJECTIONS)
    def test_is_auto_readonly_command_never_allow(self, cmd):
        """is_auto_readonly_command：注入命令不得 pure-read 放行。"""
        from core.command_safety import is_auto_readonly_command
        assert is_auto_readonly_command(cmd) is False, f"{cmd} 不得 pure-read 放行"

    def test_engine_confirm_escalates_injection(self, engine, tmp_path):
        """engine 级：auto 下注入命令转弹窗，不留 allow。"""
        EventBus.reset(log_dir=str(tmp_path))
        engine.sid = "b_sid_inject"
        engine._auto_mode_getter = lambda: True
        engine.confirm_callback = lambda *a: False
        assert engine._confirm("execute_terminal", {"command": "echo $(rm -rf x)"}, "gray") is False

        lines = [json.loads(l) for l in (tmp_path / "events.jsonl").read_text().splitlines()]
        events = [e for e in lines if e.get("type") == "auto.decide"]
        assert events, "注入命令也应留审计"
        assert all(e["verdict"] != "allow" for e in events), "注入命令不得 allow"
        escalated = [e for e in events if e.get("verdict") == "escalated"]
        assert escalated and "危险黑名单" in escalated[0]["reason"]


# ── 7. 审计四新字段齐全（B-4） ──

class TestAuditFieldsB:
    def test_audit_fields_present_on_allow(self, engine, tmp_path):
        """验收 7：allow 审计含 side_effect_level + snapshot_ref + rollback_path。"""
        EventBus.reset(log_dir=str(tmp_path))
        engine.sid = "b_sid_fields"
        engine._auto_mode_getter = lambda: True
        engine.confirm_callback = lambda *a: pytest.fail("不应弹窗")
        assert engine._confirm("execute_terminal", {"command": "git commit -m x"}, "gray") is True

        lines = [json.loads(l) for l in (tmp_path / "events.jsonl").read_text().splitlines()]
        ev = [e for e in lines if e.get("type") == "auto.decide"][0]
        for field in ("side_effect_level", "snapshot_ref", "rollback_path"):
            assert field in ev, f"审计缺字段 {field}"

    def test_audit_escalated_verdict(self, engine, tmp_path):
        """验收 7：弹窗转交留痕 verdict=escalated + side_effect_level。"""
        EventBus.reset(log_dir=str(tmp_path))
        engine.sid = "b_sid_esc"
        engine._auto_mode_getter = lambda: True
        engine.confirm_callback = lambda *a: False
        engine._confirm("execute_terminal", {"command": "git push"}, "gray")
        lines = [json.loads(l) for l in (tmp_path / "events.jsonl").read_text().splitlines()]
        escalated = [e for e in lines if e.get("type") == "auto.decide" and e.get("verdict") == "escalated"]
        assert escalated and escalated[0]["side_effect_level"] == "external-irreversible"
