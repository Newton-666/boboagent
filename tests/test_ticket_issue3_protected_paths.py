"""Issue #3：protected_paths 恢复生效 + AUTO 文件写/删授权语义。

验收：
- 仓内 core/ / tools/ / gateway 默认策略下不可被 Agent 静默改写
- load_protected_paths / is_protected 有配置与单测
- AUTO 下写/删不因「有快照可回滚」而默认放行
- 未授权改内核路径被拒绝；授权路径（非 protected）行为符合预期

残余（本票不拦，归 issue #4）：execute_terminal 改内核路径仍走确认链；
shell 绕写（python -c / sed -i / tee 等）不是本闸的覆盖面。
"""

import json
from pathlib import Path

import pytest

from core.command_safety import (
    load_protected_paths,
    is_protected,
    effective_protected_globs,
    file_tool_mutation,
    is_write_denied,
)
from core.engine import Engine
from core.event_bus import EventBus
from core.file_safety import reset_protected_paths_cache
from core.tool_executor import execute_tool
from tests.mock_llm import MockLLMCaller, text_response

_REPO = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _cwd_repo(monkeypatch):
    """全量 suite 里其他测试可能 chdir；本文件一律在仓库根判定相对路径。"""
    monkeypatch.chdir(_REPO)


def _engine():
    caller = MockLLMCaller([text_response("ok")])
    eng = Engine(caller, execute_tool, test_mode=False, auto_mode_getter=lambda: True)
    eng.test_mode = False
    return eng


KERNEL_PATHS = [
    "core/engine.py",
    "core/file_safety.py",
    "tools/edit_file.py",
    "tools/file_operation.py",
    "bobo_tui_gateway/server.py",
]


def _abs(rel: str) -> str:
    return str(_REPO / rel)


# ── 配置 / is_protected ──────────────────────────────────────────────

class TestProtectedPathsConfig:
    def test_load_protected_paths_nonempty(self):
        globs = load_protected_paths()
        assert isinstance(globs, list) and globs
        joined = " ".join(globs)
        assert "core" in joined
        assert "tools" in joined
        assert "bobo_tui_gateway" in joined

    def test_effective_globs_include_kernel_defaults(self):
        globs = effective_protected_globs()
        assert "core/**" in globs
        assert "tools/**" in globs
        assert "bobo_tui_gateway/**" in globs

    def test_load_missing_file_returns_empty_no_crash(self, tmp_path):
        reset_protected_paths_cache()
        missing = tmp_path / "nope.json"
        assert load_protected_paths(str(missing)) == []

    def test_load_corrupt_json_returns_empty_no_crash(self, tmp_path):
        reset_protected_paths_cache()
        bad = tmp_path / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        assert load_protected_paths(str(bad)) == []

    def test_missing_config_kernel_still_protected(self, tmp_path):
        """配置缺失不得炸启动，且内核兜底仍生效（fail-closed）。"""
        reset_protected_paths_cache()
        missing = str(tmp_path / "absent.json")
        assert load_protected_paths(missing) == []
        globs = effective_protected_globs(missing)
        assert is_protected("core/engine.py", globs)
        assert is_protected("tools/edit_file.py", globs)
        assert is_protected("bobo_tui_gateway/server.py", globs)
        assert not is_protected("tests/test_foo.py", globs)

    @pytest.mark.parametrize("path", KERNEL_PATHS)
    def test_is_protected_kernel_paths(self, path):
        assert is_protected(path), path

    def test_is_protected_absolute_kernel_path(self):
        assert is_protected(_abs("core/engine.py"))

    def test_authorized_paths_not_protected(self, tmp_path):
        assert not is_protected("tests/test_ticket_issue3_protected_paths.py")
        assert not is_protected("docs/SELF.md")
        assert not is_protected("/etc/hosts")
        assert not is_protected(str(tmp_path / "scratch.md"))

    def test_custom_globs_only_when_explicit(self):
        assert not is_protected(_abs("core/engine.py"), globs=["docs/**"])
        assert is_protected(_abs("docs/SELF.md"), globs=["docs/**"])


# ── is_write_denied / 工具层 ─────────────────────────────────────────

class TestWriteDeniedKernel:
    @pytest.mark.parametrize("path", KERNEL_PATHS)
    def test_is_write_denied_kernel(self, path):
        denied, reason = is_write_denied(path)
        assert denied is True
        assert "受保护" in reason

    def test_is_write_denied_authorized_tmp(self, tmp_path):
        target = tmp_path / "ok.md"
        denied, _ = is_write_denied(str(target))
        assert denied is False

    def test_is_write_denied_authorized_tests_path(self):
        denied, _ = is_write_denied("tests/test_ticket_issue3_protected_paths.py")
        assert denied is False

    def test_edit_file_denies_kernel_without_writing(self):
        from tools.edit_file import execute
        target = _REPO / "core/engine.py"
        original = target.read_bytes()
        try:
            result = execute(str(target), "Engine", "HackedEngine")
            assert "禁止" in result or "受保护" in result
        finally:
            assert target.read_bytes() == original

    def test_file_operation_write_denies_kernel(self):
        from tools.file_operation import execute
        target = _REPO / "core/file_safety.py"
        original = target.read_bytes()
        try:
            result = execute(action="write", path=str(target), content="hack")
            assert "禁止" in result or "受保护" in result
        finally:
            assert target.read_bytes() == original

    def test_file_operation_write_authorized_tmp(self, tmp_path):
        from tools.file_operation import execute
        target = tmp_path / "authorized.txt"
        result = execute(action="write", path=str(target), content="hello")
        assert "已写入" in result
        assert target.read_text(encoding="utf-8") == "hello"

    def test_file_operation_batch_write_mixed(self, tmp_path):
        from tools.file_operation import execute
        ok = tmp_path / "ok.txt"
        kernel = _REPO / "core/engine.py"
        original = kernel.read_bytes()
        result = execute(action="batch_write", files=[
            {"path": str(ok), "content": "yes"},
            {"path": str(kernel), "content": "hack"},
        ])
        assert "禁止" in result or "受保护" in result
        assert ok.read_text(encoding="utf-8") == "yes"
        assert kernel.read_bytes() == original


# ── file_tool_mutation ───────────────────────────────────────────────

class TestFileToolMutation:
    def test_edit_file_is_mutating(self):
        mutating, paths = file_tool_mutation(
            "edit_file", {"file_path": "core/engine.py"})
        assert mutating is True
        assert paths == ["core/engine.py"]

    def test_file_operation_read_not_mutating(self):
        mutating, paths = file_tool_mutation(
            "file_operation", {"action": "read", "path": "core/engine.py"})
        assert mutating is False
        assert paths == ["core/engine.py"]

    def test_file_operation_write_mutating(self):
        mutating, _ = file_tool_mutation(
            "file_operation", {"action": "write", "path": "notes/a.md"})
        assert mutating is True

    def test_batch_write_collects_paths(self):
        mutating, paths = file_tool_mutation(
            "file_operation",
            {"action": "batch_write", "files": [{"path": "a.md"}, {"path": "b.md"}]})
        assert mutating is True
        assert paths == ["a.md", "b.md"]

    def test_delete_file_mutating(self):
        mutating, paths = file_tool_mutation("delete_file", {"path": "tmp/x"})
        assert mutating is True
        assert paths == ["tmp/x"]


# ── AUTO 决策链 ──────────────────────────────────────────────────────

class TestAutoFileAuth:
    def test_unauthorized_kernel_edit_denied(self, tmp_path):
        EventBus.reset(log_dir=str(tmp_path))
        eng = _engine()
        eng.sid = "i3_kernel"
        eng.confirm_callback = lambda *a: pytest.fail("AUTO 不得弹窗")
        allowed = eng._confirm(
            "edit_file",
            {"file_path": "core/engine.py", "old_string": "a", "new_string": "b"},
            "编辑文件",
        )
        assert allowed is False
        events = [json.loads(l) for l in (tmp_path / "events.jsonl").read_text().splitlines()
                  if l.strip()]
        decide = [e for e in events if e.get("type") == "auto.decide"]
        assert decide and decide[-1]["verdict"] == "deny"
        assert "快照可回滚≠已授权" in decide[-1]["reason"]

    @pytest.mark.parametrize("path", KERNEL_PATHS)
    def test_unauthorized_kernel_file_operation_write_denied(self, tmp_path, path):
        EventBus.reset(log_dir=str(tmp_path))
        eng = _engine()
        eng.confirm_callback = lambda *a: pytest.fail("AUTO 不得弹窗")
        assert eng._confirm(
            "file_operation", {"action": "write", "path": path, "content": "x"},
            "写文件") is False

    def test_unauthorized_kernel_delete_denied(self, tmp_path):
        EventBus.reset(log_dir=str(tmp_path))
        eng = _engine()
        assert eng._confirm(
            "file_operation", {"action": "delete", "path": "tools/edit_file.py"},
            "删文件") is False

    def test_authorized_tmp_edit_allowed_snapshot_is_not_auth(self, tmp_path):
        EventBus.reset(log_dir=str(tmp_path))
        eng = _engine()
        eng.sid = "i3_auth"
        target = str(tmp_path / "ok.md")
        allowed = eng._confirm(
            "edit_file",
            {"file_path": target, "old_string": "a", "new_string": "b"},
            "编辑文件",
        )
        assert allowed is True
        events = [json.loads(l) for l in (tmp_path / "events.jsonl").read_text().splitlines()
                  if l.strip()]
        decide = [e for e in events if e.get("type") == "auto.decide"][-1]
        assert decide["verdict"] == "allow"
        assert "不构成授权" in decide["reason"]
        assert "checkpoint" not in decide["reason"] or "不构成授权" in decide["reason"]
        assert decide["snapshot_ref"], "授权写仍可记快照（回滚保险）"
        assert decide["side_effect_level"] == "local-reversible"

    def test_authorized_file_operation_write_allowed(self, tmp_path):
        EventBus.reset(log_dir=str(tmp_path))
        eng = _engine()
        target = str(tmp_path / "notes.md")
        assert eng._confirm(
            "file_operation", {"action": "write", "path": target, "content": "x"},
            "写文件") is True

    def test_read_on_kernel_path_allowed(self, tmp_path):
        """读内核不是改写：AUTO 放行。"""
        EventBus.reset(log_dir=str(tmp_path))
        eng = _engine()
        assert eng._confirm(
            "file_operation", {"action": "read", "path": "core/engine.py"},
            "读文件") is True
        events = [json.loads(l) for l in (tmp_path / "events.jsonl").read_text().splitlines()
                  if l.strip()]
        decide = [e for e in events if e.get("type") == "auto.decide"][-1]
        assert decide["verdict"] == "allow"
        assert decide["side_effect_level"] == "pure-read"

    def test_write_without_path_denied(self, tmp_path):
        EventBus.reset(log_dir=str(tmp_path))
        eng = _engine()
        assert eng._confirm("edit_file", {"old_string": "a", "new_string": "b"}, "编辑") is False

    def test_snapshot_alone_does_not_authorize_kernel(self, tmp_path, monkeypatch):
        """即使快照函数可调用，未授权内核写仍 deny——快照≠授权。"""
        EventBus.reset(log_dir=str(tmp_path))
        eng = _engine()
        snaps = []
        monkeypatch.setattr(eng, "_snapshot_for_rollback",
                            lambda cmd: (snaps.append(cmd), {
                                "kind": "file", "ref": "snap", "rollback": "x"})[1])
        assert eng._confirm(
            "edit_file",
            {"file_path": "core/engine.py", "old_string": "a", "new_string": "b"},
            "编辑文件") is False
        assert snaps == [], "未授权路径不得走到快照放行"

    def test_auto_off_still_uses_confirm_callback(self, tmp_path):
        """对照组：AUTO 关时文件工具走原弹窗链（不在 auto.decide 里静默放行）。"""
        EventBus.reset(log_dir=str(tmp_path))
        caller = MockLLMCaller([text_response("ok")])
        calls = []
        eng = Engine(caller, execute_tool, test_mode=False, auto_mode_getter=None)
        eng.test_mode = False
        eng.confirm_callback = lambda *a: calls.append(a) or True
        # 授权路径：弹窗放行
        assert eng._confirm(
            "edit_file",
            {"file_path": str(tmp_path / "x.md"), "old_string": "a", "new_string": "b"},
            "编辑") is True
        assert calls, "AUTO 关必须走 confirm_callback"
