"""GitHub #2：超时取消内层工作 + 写路径不可双执行。

复现口径：
  写类工具超时 → 立即用相同参数重试 → 文件系统副作用只出现一次。
  终端命令外层超时（内层 timeout 更大）→ 子进程被 killpg，无长期孤儿。

运行：
  python -m pytest tests/test_tool_timeout_lifecycle.py -q
"""

import os
import threading
import time

import pytest

from core import tool_lifecycle as lifecycle
from core.tool_executor import execute_tool
from tools import TOOL_FUNCTIONS


@pytest.fixture(autouse=True)
def _reset_lifecycle():
    lifecycle.reset_for_tests()
    yield
    lifecycle.reset_for_tests()


class TestTimeoutConfig:
    def test_config_tool_timeout_is_default(self, monkeypatch):
        monkeypatch.setattr("config.TOOL_TIMEOUT", 7)
        assert lifecycle.resolve_timeout("read_local_file") == 7
        assert lifecycle.resolve_timeout("grep_code") == 7

    def test_long_running_overrides_preserved(self):
        assert lifecycle.resolve_timeout("execute_terminal") == 120
        assert lifecycle.resolve_timeout("spawn_worker") == 310

    def test_executor_uses_config_tool_timeout(self):
        import core.tool_executor as te
        from config import TOOL_TIMEOUT as cfg
        assert te.TOOL_TIMEOUT == cfg
        assert lifecycle.resolve_timeout("get_current_time") == int(cfg)


class TestTerminalTimeoutKillsOrphans:
    def test_outer_timeout_kills_inner_process(self, tmp_path, monkeypatch):
        """内层 timeout=30、外层 1s：必须 killpg，sleep 不得残留，echo 不得落地。"""
        marker = tmp_path / "hit.txt"
        pidfile = tmp_path / "pid.txt"
        cmd = f"echo $$ > '{pidfile}'; sleep 30; echo HIT > '{marker}'"

        def _timeout(name, arguments=None):
            return 1 if name == "execute_terminal" else 20
        monkeypatch.setattr(lifecycle, "resolve_timeout", _timeout)
        monkeypatch.setattr("core.tool_executor.resolve_timeout", _timeout)
        # 走 execute_tool，不是直接 execute()：这才是外层 future.result 超时路径
        result = execute_tool("execute_terminal", {"command": cmd, "timeout": 30})

        assert "超过" in result or "取消" in result or "已终止" in result, result
        deadline = time.time() + 3
        pid = None
        while time.time() < deadline:
            if pidfile.exists() and pidfile.read_text().strip().isdigit():
                pid = int(pidfile.read_text().strip())
                break
            time.sleep(0.05)
        if pid is not None:
            # 给 killpg + wait 一点时间
            dead = False
            for _ in range(40):
                try:
                    os.kill(pid, 0)
                except OSError:
                    dead = True
                    break
                time.sleep(0.1)
            assert dead, f"孤儿进程仍在运行 pid={pid}"
        # sleep 被杀则 HIT 不应出现；即便竞态写入，重试路径另测
        time.sleep(0.3)
        assert not marker.exists() or marker.read_text().strip() != "HIT"

    def test_terminal_retry_after_timeout_writes_once(self, tmp_path, monkeypatch):
        """timeout → 重试同一条追加命令 → 文件只出现一次预期行。"""
        target = tmp_path / "append.txt"
        line = "ONCE-ONLY-MARKER"
        cmd = f"sleep 2; echo {line} >> '{target}'"

        def _timeout(name, arguments=None):
            return 1 if name == "execute_terminal" else 20
        monkeypatch.setattr(lifecycle, "resolve_timeout", _timeout)
        monkeypatch.setattr("core.tool_executor.resolve_timeout", _timeout)
        first = execute_tool("execute_terminal", {"command": cmd, "timeout": 30})
        second = execute_tool("execute_terminal", {"command": cmd, "timeout": 30})

        # 第一次应超时/取消；第二次或是拒绝、或是等第一次结束后去重/再跑一次
        assert "超过" in first or "取消" in first or "仍在执行" in first, first

        # 等到内层（若未被杀掉）收束
        time.sleep(3.5)
        text = target.read_text() if target.exists() else ""
        count = text.count(line)
        assert count <= 1, f"追加了 {count} 次: {text!r}\nfirst={first}\nsecond={second}"

        # 若第一次已杀掉，文件为空是合法的；此时再以足够超时跑一次应只写一行
        if count == 0:
            def _longer(name, arguments=None):
                return 10 if name == "execute_terminal" else 20
            monkeypatch.setattr(lifecycle, "resolve_timeout", _longer)
            monkeypatch.setattr("core.tool_executor.resolve_timeout", _longer)
            third = execute_tool("execute_terminal", {"command": cmd, "timeout": 5})
            time.sleep(0.2)
            text = target.read_text() if target.exists() else ""
            assert text.count(line) == 1, f"最终应恰好一行，得到 {text!r}\nthird={third}"


class TestWriteToolTimeoutNoDoubleApply:
    def test_slow_write_timeout_retry_lands_once(self, tmp_path, monkeypatch):
        """写工具：sleep 后追加。外层超时 → 立即重试 → 文件只追加一次。"""
        target = tmp_path / "out.txt"
        marker = "WRITE-ONCE\n"
        started = threading.Event()
        original = TOOL_FUNCTIONS["file_operation"]

        def slow_write(**kwargs):
            started.set()
            # 不协作取消：模拟卡在写路径上的线程。互斥/去重必须拦住重试。
            time.sleep(1.5)
            with open(target, "a", encoding="utf-8") as f:
                f.write(kwargs.get("content") or marker)
            return f"已写入: {kwargs.get('path')}"

        monkeypatch.setitem(TOOL_FUNCTIONS, "file_operation", slow_write)
        monkeypatch.setattr(lifecycle, "CANCEL_GRACE_S", 0.2)
        monkeypatch.setattr("core.tool_executor.CANCEL_GRACE_S", 0.2)

        def _timeout(name, arguments=None):
            return 0.3 if name == "file_operation" else 20
        monkeypatch.setattr(lifecycle, "resolve_timeout", _timeout)
        monkeypatch.setattr("core.tool_executor.resolve_timeout", _timeout)
        args = {"action": "write", "path": str(target), "content": marker}

        first = execute_tool("file_operation", args)
        # 第一次应已进入 worker
        started.wait(timeout=2)
        second = execute_tool("file_operation", dict(args))

        assert "超过" in first or "取消" in first, first
        assert (
            "仍在执行" in second
            or "去重" in second
            or "取消" in second
            or "超过" in second
        ), second

        # 等待可能的僵尸线程把那一次写入落地
        time.sleep(2.0)
        text = target.read_text() if target.exists() else ""
        assert text.count(marker.strip()) <= 1, f"双写入: {text!r}\nfirst={first}\nsecond={second}"

        monkeypatch.setitem(TOOL_FUNCTIONS, "file_operation", original)

    def test_inflight_same_write_is_hard_rejected(self, tmp_path, monkeypatch):
        target = tmp_path / "lock.txt"
        release = threading.Event()
        entered = threading.Event()

        def blocker(**kwargs):
            entered.set()
            release.wait(timeout=5)
            with open(target, "a", encoding="utf-8") as f:
                f.write(kwargs.get("content", "x"))
            return "已写入: blocked"

        monkeypatch.setitem(TOOL_FUNCTIONS, "file_operation", blocker)
        monkeypatch.setattr(lifecycle, "resolve_timeout", lambda name, arguments=None: 8)
        monkeypatch.setattr("core.tool_executor.resolve_timeout", lambda name, arguments=None: 8)
        args = {"action": "write", "path": str(target), "content": "X"}

        def _run():
            execute_tool("file_operation", args)

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        assert entered.wait(timeout=2)
        rejected = execute_tool("file_operation", dict(args))
        assert "仍在执行" in rejected
        release.set()
        t.join(timeout=3)

    def test_read_is_not_gated(self, monkeypatch):
        """file_operation read 不应占用写槽。"""
        ident = lifecycle.write_identity(
            "file_operation", {"action": "read", "path": "/tmp/x"}
        )
        assert ident is None

    def test_code_execution_is_side_effect_gated(self):
        """code_execution 必须进写槽：同一脚本超时重试不得双跑。"""
        assert "code_execution" in lifecycle.SIDE_EFFECT_TOOLS
        assert "code_execution" in lifecycle.WRITE_TOOLS
        ident = lifecycle.write_identity(
            "code_execution",
            {"code": "open('x','a').write('a')", "language": "python", "type": "run"},
        )
        assert ident is not None
        ident2 = lifecycle.write_identity(
            "code_execution",
            {"code": "open('x','a').write('a')", "language": "python", "type": "run"},
        )
        assert ident == ident2

    def test_other_write_capable_tools_are_listed(self):
        for name in (
            "run_tests", "task_ledger", "restore_checkpoint",
            "write_obsidian", "append_obsidian", "refactor",
        ):
            assert name in lifecycle.SIDE_EFFECT_TOOLS, name
        # 远程写：写槽覆盖，但不能 killpg（见 docs/TOOL_TIMEOUT_LIFECYCLE.md）
        for name in ("github_create_pr", "notion_create_page", "computer_use"):
            assert name in lifecycle.SIDE_EFFECT_TOOLS, name

    def test_does_not_mutate_caller_arguments(self):
        import json
        args = {"action": "exists", "path": "/tmp"}
        execute_tool("file_operation", args)
        assert "_interrupt_event" not in args
        json.dumps(args)
