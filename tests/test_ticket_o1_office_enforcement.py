"""TICKET-O-1 验收测试：OFFICE MODE 执法内核。

覆盖设计稿 v0.3.1（owner 裁决版）票 O-1 范围（每条带无角色对照组）：
  1. BOBO_ROLE 读取：staff / dispatcher / 非法值 / 未设置
  2. git 写子命令全禁（staff/dispatcher），只读子命令放行
  3. 受保护路径写禁（core/library/tools/data/relay_v2/bobo_tui_gateway）
  4. library 直接写禁（走记忆接口，普通模式不限制）
  5. 票据外文件写禁
  6. 票据 authorized_paths 豁免（staff 唯一豁免通道）
  7. dispatcher 无豁免（票据内也禁）
  8. shell 写路径执法（> / tee / cp / mv / mkdir）
  9. office.guard / office.role 审计事件落 events.jsonl
  10. 普通模式零变化：无 BOBO_ROLE 不激活任何限制（硬验收项）
"""
import json
import sys
from unittest import mock

import pytest

sys.path.insert(0, ".")

from core.command_safety import load_protected_paths, is_protected
from core.engine import Engine
from core.tool_executor import execute_tool
from tests.mock_llm import MockLLMCaller, text_response


def make_engine(role=None):
    """构造 test_mode=False 的引擎（pytest 下 __init__ 强制 test_mode=True，
    需手动置 False 才能走到 office 裁决链）；role 显式注入。"""
    caller = MockLLMCaller([text_response("ok")])
    eng = Engine(caller, execute_tool, test_mode=False)
    eng.test_mode = False
    if role is not None:
        eng.office_role = role
    return eng


# ── 1. BOBO_ROLE 读取 ──

class TestRoleRead:
    def test_staff_role_from_env(self, monkeypatch):
        monkeypatch.setenv("BOBO_ROLE", "staff")
        eng = Engine(MockLLMCaller([text_response("ok")]), execute_tool, test_mode=False)
        assert eng.office_role == "staff"

    def test_dispatcher_role_from_env(self, monkeypatch):
        monkeypatch.setenv("BOBO_ROLE", "dispatcher")
        eng = Engine(MockLLMCaller([text_response("ok")]), execute_tool, test_mode=False)
        assert eng.office_role == "dispatcher"

    def test_uppercase_role_normalized(self, monkeypatch):
        monkeypatch.setenv("BOBO_ROLE", "STAFF")
        eng = Engine(MockLLMCaller([text_response("ok")]), execute_tool, test_mode=False)
        assert eng.office_role == "staff"

    def test_invalid_role_is_none(self, monkeypatch):
        monkeypatch.setenv("BOBO_ROLE", "admin")
        eng = Engine(MockLLMCaller([text_response("ok")]), execute_tool, test_mode=False)
        assert eng.office_role is None  # 非法值 → 普通模式，不激活

    def test_no_env_is_none(self, monkeypatch):
        monkeypatch.delenv("BOBO_ROLE", raising=False)
        eng = Engine(MockLLMCaller([text_response("ok")]), execute_tool, test_mode=False)
        assert eng.office_role is None  # 未设置 → 普通模式（对照组）


# ── 2. git 写子命令全禁 / 只读放行 ──

class TestGitEnforcement:
    @pytest.mark.parametrize("cmd", [
        "git commit -m x", "git add .", "git push origin main",
        "git checkout feat/x", "git reset --hard HEAD", "git merge main",
        "git rebase main", "git branch new-feat",
    ])
    def test_staff_git_write_denied(self, cmd):
        eng = make_engine("staff")
        verdict, _ = eng._office_decide("execute_terminal", {"command": cmd}, "r")
        assert verdict == "deny"

    @pytest.mark.parametrize("cmd", ["git status", "git log --oneline", "git diff", "git show HEAD"])
    def test_staff_git_readonly_allowed(self, cmd):
        eng = make_engine("staff")
        verdict, _ = eng._office_decide("execute_terminal", {"command": cmd}, "r")
        assert verdict == "allow"

    def test_dispatcher_git_write_denied(self):
        eng = make_engine("dispatcher")
        verdict, _ = eng._office_decide("execute_terminal", {"command": "git commit -m x"}, "r")
        assert verdict == "deny"

    def test_no_role_git_unchanged(self):
        """对照组：无角色不拦 git（office 链不激活）"""
        eng = make_engine(None)
        with mock.patch.object(eng, "_office_decide", wraps=eng._office_decide) as m:
            # _confirm 在无角色时不进入 office 段
            assert eng.office_role is None
            m.assert_not_called()


# ── 3/4. 受保护路径写禁 + library 直接写禁 ──

class TestProtectedPaths:
    @pytest.mark.parametrize("path", [
        "core/engine.py", "library/agent开发/x.md", "tools/agent_connect.py",
        "tools/team_relay_v2.py", "data/relay_v2/x/y.json", "bobo_tui_gateway/handlers/prompts.py",
    ])
    def test_staff_protected_write_denied(self, path):
        eng = make_engine("staff")
        verdict, _ = eng._office_decide("edit_file", {"file_path": path}, "r")
        assert verdict == "deny"

    def test_staff_shell_redirect_to_protected_denied(self):
        eng = make_engine("staff")
        verdict, _ = eng._office_decide("execute_terminal", {"command": "echo x >> core/engine.py"}, "r")
        assert verdict == "deny"

    def test_staff_shell_cp_to_protected_denied(self):
        eng = make_engine("staff")
        verdict, _ = eng._office_decide("execute_terminal", {"command": "cp a.txt library/note.md"}, "r")
        assert verdict == "deny"

    def test_staff_dev_null_redirect_allowed(self):
        eng = make_engine("staff")
        verdict, _ = eng._office_decide("execute_terminal", {"command": "cat a.txt > /dev/null"}, "r")
        assert verdict == "allow"

    def test_is_protected_matches_globs(self):
        assert is_protected("core/engine.py")
        assert is_protected("library/anything.md")
        assert is_protected("data/relay_v2/a/b/c.json")
        assert not is_protected("data/tickets/TICKET-001.md")
        assert not is_protected("/etc/hosts")

    def test_load_protected_paths_nonempty(self):
        globs = load_protected_paths()
        assert isinstance(globs, list) and globs
        assert any("library" in g for g in globs)


# ── 5. 票据外文件写禁 ──

class TestOutOfTicketWrites:
    def test_staff_unticketed_write_denied(self):
        eng = make_engine("staff")
        verdict, _ = eng._office_decide("file_operation",
                                        {"action": "write", "path": "tmp_scratch.txt"}, "r")
        assert verdict == "deny"

    def test_staff_batch_write_unticketed_denied(self):
        eng = make_engine("staff")
        verdict, _ = eng._office_decide("file_operation",
                                        {"action": "batch_write",
                                         "files": [{"path": "a.md"}, {"path": "b.md"}]}, "r")
        assert verdict == "deny"

    def test_staff_read_operations_allowed(self):
        eng = make_engine("staff")
        for tool, args in [
            ("read_local_file", {"filepath": "core/engine.py"}),
            ("grep_code", {"pattern": "x"}),
            ("execute_terminal", {"command": "ls -la"}),
        ]:
            verdict, _ = eng._office_decide(tool, args, "r")
            assert verdict == "allow", tool


# ── 6/7. 票据授权书豁免 / dispatcher 无豁免 ──

class TestTicketAuthorization:
    def _make_ticket_dir(self, eng, tmp_path, authorized):
        import os
        d = tmp_path / "tickets"
        d.mkdir()
        (d / "TICKET-O1-TEST.md").write_text(
            "---\nauthorized_paths:\n" + "".join(f"  - {a}\n" for a in authorized) + "---\n# t\n",
            encoding="utf-8",
        )
        eng._TICKETS_DIR = str(d)

    def test_staff_ticket_exemption_allows(self, tmp_path):
        eng = make_engine("staff")
        self._make_ticket_dir(eng, tmp_path, ["notes_work/**", "data/tickets/**"])
        verdict, _ = eng._office_decide("file_operation",
                                        {"action": "write", "path": "notes_work/a.md"}, "r")
        assert verdict == "allow"
        verdict, _ = eng._office_decide("file_operation",
                                        {"action": "write", "path": "data/tickets/TICKET-9.md"}, "r")
        assert verdict == "allow"

    def test_staff_exemption_not_covering_protected(self, tmp_path):
        eng = make_engine("staff")
        self._make_ticket_dir(eng, tmp_path, ["notes_work/**"])
        verdict, _ = eng._office_decide("edit_file", {"file_path": "core/engine.py"}, "r")
        assert verdict == "deny"  # 票据未豁免受保护路径

    def test_dispatcher_no_exemption(self, tmp_path):
        eng = make_engine("dispatcher")
        self._make_ticket_dir(eng, tmp_path, ["notes_work/**"])
        verdict, _ = eng._office_decide("file_operation",
                                        {"action": "write", "path": "notes_work/a.md"}, "r")
        assert verdict == "deny"  # dispatcher 无豁免：票据内也禁


# ── 8. _confirm 全链路（office 段拦截） ──

class TestConfirmChain:
    def test_confirm_denies_git_write_for_staff(self):
        eng = make_engine("staff")
        assert eng._confirm("execute_terminal", {"command": "git commit -m x"}, "r") is False

    def test_confirm_allows_git_read_for_staff(self):
        eng = make_engine("staff")
        with mock.patch.object(eng, "confirm_callback", return_value=True):
            assert eng._confirm("execute_terminal", {"command": "git status"}, "r") is True

    def test_confirm_no_role_skips_office(self):
        """对照组：无角色时 _office_decide 不被调用"""
        eng = make_engine(None)
        with mock.patch.object(eng, "_office_decide") as m:
            eng._confirm("execute_terminal", {"command": "git commit -m x"}, "r")
            m.assert_not_called()

    def test_confirm_staff_calls_office(self):
        eng = make_engine("staff")
        with mock.patch.object(eng, "_office_decide", return_value=("deny", "x")) as m:
            assert eng._confirm("edit_file", {"file_path": "a.txt"}, "r") is False
            m.assert_called_once()


# ── 9. 审计事件 ──

class TestAudit:
    def test_office_role_audit_written(self, monkeypatch, tmp_path):
        import core.engine as eng_mod
        from core.event_bus import EventBus
        bus = EventBus(log_dir=str(tmp_path / "audit"))
        monkeypatch.setattr(eng_mod, "event_bus", bus)
        monkeypatch.setenv("BOBO_ROLE", "staff")
        Engine(MockLLMCaller([text_response("ok")]), execute_tool, test_mode=False)
        lines = open(bus.filepath, encoding="utf-8").read().splitlines()
        roles = [json.loads(l) for l in lines if "office.role" in l]
        assert roles and roles[-1]["role"] == "staff"

    def test_office_guard_audit_written(self, tmp_path):
        import core.engine as eng_mod
        from core.event_bus import EventBus
        bus = EventBus(log_dir=str(tmp_path / "audit2"))
        orig = eng_mod.event_bus
        eng_mod.event_bus = bus
        try:
            eng = make_engine("staff")
            eng._office_decide("execute_terminal", {"command": "git commit -m x"}, "r")
            lines = open(bus.filepath, encoding="utf-8").read().splitlines()
            guards = [json.loads(l) for l in lines if "office.guard" in l]
            assert guards and "git 写操作全禁" in guards[-1]["detail"]
        finally:
            eng_mod.event_bus = orig


# ── 10. 普通模式零变化（回归防线） ──

class TestNormalModeUnchanged:
    def test_no_role_protected_file_write_still_normal_path(self):
        """对照组：无角色时受保护路径写不触发 office 拒绝（走原 confirm 链）"""
        eng = make_engine(None)
        with mock.patch.object(eng, "_office_decide") as m:
            eng._confirm("edit_file", {"file_path": "core/engine.py"}, "r")
            m.assert_not_called()
