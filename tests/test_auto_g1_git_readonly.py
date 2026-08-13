"""TICKET-AUTO-G1：AUTO 决策树 git 只读命令误杀修复测试。

背景（2026-08-13 自暴露）：AUTO 模式下 git rev-parse/describe/show-ref 等纯读
命令被误判"外部不可逆（无法确认可回滚）"全拒，git status/log 等虽在只读集合
但集合过窄。修复：扩充纯只读 git 子命令全集 + 混合子命令（branch/stash/remote/
tag/config）只读形式细分；写操作（push/reset/rebase/clean 等）维持 AUTO 决策不变。

覆盖：
1. 分类层：只读 git 放行（pure-read + is_auto_readonly）、写 git 维持原判定、
   混合子命令写形式不放行、非 git 命令零变化
2. 决策层（实弹）：engine._confirm 在 auto 开时 git 只读零拦截、git push 仍拦、
   auto 关行为零变化
"""

import pytest

from core.command_safety import classify_side_effect, is_auto_readonly_command


@pytest.fixture
def engine():
    """构造非 test_mode 的 Engine（pytest 下 conftest 默认 test_mode=True，
    会短路 _confirm 全流程；此处显式关闭，确保测到 auto 决策树）。"""
    from core.engine import Engine
    from core.tool_executor import execute_tool
    from tests.mock_llm import MockLLMCaller, text_response

    caller = MockLLMCaller([text_response("Hello! I am Bobo.")])
    eng = Engine(caller, execute_tool, test_mode=False)
    eng.test_mode = False  # pytest 环境强制覆盖，确保测到 _confirm 全流程
    return eng


# ── 1. 分类层：TICKET-AUTO-G1 扩充的只读 git 命令 ──

class TestG1ReadonlyGitClassify:
    """修复后必须判 pure-read 且 is_auto_readonly_command=True（AUTO 零拦截）。"""

    @pytest.mark.parametrize("cmd", [
        # 原有只读集合（回归锚点）
        "git status", "git status --short", "git log --oneline -3", "git diff",
        "git show HEAD", "git blame main.py", "git ls-files", "git ls-tree HEAD",
        # G1 扩充：纯只读子命令
        "git rev-parse HEAD", "git rev-parse --abbrev-ref HEAD",
        "git describe --tags", "git show-ref", "git ls-remote origin",
        "git for-each-ref", "git name-rev HEAD", "git count-objects",
        "git shortlog -5", "git whatchanged -3", "git cherry HEAD",
        "git check-ignore x", "git check-attr a", "git rev-list HEAD~3",
        "git cat-file -p HEAD", "git verify-pack -v x.idx", "git version", "git help",
        # G1 扩充：混合子命令只读形式
        "git branch --show-current", "git branch -a", "git branch -r",
        "git stash list", "git stash show", "git remote -v",
        "git tag -l", "git config --get user.name",
        # 全局选项前缀不影响
        "git -C /tmp/repo rev-parse HEAD", "git --no-pager log -3",
    ])
    def test_readonly_git_allowed(self, cmd):
        level, _reason = classify_side_effect(cmd)
        assert level == "pure-read", f"{cmd} 应判 pure-read（当前 {level}）"
        assert is_auto_readonly_command(cmd), f"{cmd} 应被 is_auto_readonly_command 放行"

    def test_readonly_chain_allowed(self):
        """链式全读（git status && git rev-parse HEAD）→ 放行。"""
        cmd = "git status && git rev-parse HEAD"
        level, _reason = classify_side_effect(cmd)
        assert level == "pure-read"
        assert is_auto_readonly_command(cmd)


class TestG1WriteGitUnchanged:
    """写操作必须维持现有 AUTO 决策（不放行为 pure-read）。"""

    @pytest.mark.parametrize("cmd", [
        # 外部不可逆：维持 external-irreversible（AUTO 下即时 deny）
        "git push origin main", "git push",
        "git reset --hard HEAD~1", "git rebase main", "git clean -fd",
        # 本地可回滚：维持 local-reversible（AUTO 下快照放行，语义不升级为纯读）
        "git commit -m fix", "git add .", "git checkout main",
        "git merge feature", "git fetch origin", "git tag v1.0",
        # 混合子命令写形式：不得误判只读
        "git branch -d old", "git branch -D old", "git branch -m new",
        "git stash pop", "git stash drop", "git stash push -m x",
        "git remote add origin u", "git remote remove origin",
        "git tag -a v1.0 -m x", "git config user.name x", "git config --unset x",
    ])
    def test_write_git_not_readonly(self, cmd):
        level, _reason = classify_side_effect(cmd)
        assert level != "pure-read", f"{cmd} 是写操作，不得判 pure-read（当前 {level}）"
        assert not is_auto_readonly_command(cmd), f"{cmd} 不得被 is_auto_readonly_command 放行"

    def test_chain_with_write_tail_not_allowed(self):
        """链式含写段（git status && git push）→ 整条不放行。"""
        cmd = "git status && git push origin main"
        level, _reason = classify_side_effect(cmd)
        assert level == "external-irreversible"
        assert not is_auto_readonly_command(cmd)

    def test_command_substitution_still_blocked(self):
        """命令替换注入（$(...)/反引号）仍一律不放行（不因 git 只读扩充放宽）。"""
        assert not is_auto_readonly_command("git status && echo $(rm -rf x)")
        assert not is_auto_readonly_command("git log `id`")


class TestG1NonGitZeroChange:
    """非 git 命令分类零变化（回归锚点）。"""

    @pytest.mark.parametrize("cmd,want_level", [
        ("ls -la", "pure-read"),
        ("cat a.txt", "pure-read"),
        ("pwd", "pure-read"),
        ("mkdir -p /tmp/x", "local-reversible"),
        ("cp a b", "local-reversible"),
        ("pip install x", "local-reversible"),
    ])
    def test_non_git_classify_unchanged(self, cmd, want_level):
        level, _reason = classify_side_effect(cmd)
        assert level == want_level, f"{cmd}: 期望 {want_level}，实际 {level}"


# ── 2. 决策层（实弹）：engine._confirm 端到端 ──

class TestG1EngineDecision:
    """验收 1/2：AUTO 开时 git 只读零拦截、git 写仍拦；auto 关零变化。"""

    def test_auto_readonly_git_zero_intercept(self, engine):
        """验收 1：auto 开 + git rev-parse/status/log → 直接放行，不调 callback。"""
        engine._auto_mode_getter = lambda: True
        engine.confirm_callback = lambda *a: pytest.fail("只读 git 不应进确认流程")
        for cmd in ("git status", "git log --oneline -3", "git rev-parse HEAD",
                    "git branch --show-current", "git stash list", "git remote -v"):
            assert engine._confirm("execute_terminal", {"command": cmd}, "gray") is True, cmd

    def test_auto_write_git_still_denied(self, engine):
        """验收 2：auto 开 + git push / reset --hard → 仍即时 deny。"""
        engine._auto_mode_getter = lambda: True
        engine.confirm_callback = lambda *a: pytest.fail("auto 下外部不可逆应即时拒绝，不弹窗")
        for cmd in ("git push origin main", "git reset --hard HEAD~1", "git rebase main"):
            assert engine._confirm("execute_terminal", {"command": cmd}, "gray") is False, cmd

    def test_auto_local_reversible_git_still_allowed(self, engine):
        """本地可回滚 git（commit/checkout）维持快照放行。"""
        engine._auto_mode_getter = lambda: True
        engine.confirm_callback = lambda *a: pytest.fail("本地可回滚应快照放行")
        for cmd in ("git commit -m fix", "git checkout main", "git fetch origin"):
            assert engine._confirm("execute_terminal", {"command": cmd}, "gray") is True, cmd

    def test_auto_off_zero_change(self, engine):
        """auto 关：git push 走原确认流程（callback），零变化。"""
        engine._auto_mode_getter = lambda: False
        engine._all_confirmed = False
        engine.confirm_callback = lambda *a: True
        assert engine._confirm("execute_terminal", {"command": "git push"}, "gray") is True
        engine._all_confirmed = True
        assert engine._confirm("execute_terminal", {"command": "git push"}, "gray") is True
