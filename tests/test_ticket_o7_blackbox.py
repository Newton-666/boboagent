"""TICKET-O7：崩溃取证黑匣子验收测试。

验收 1：node 前端 stderr 持久化到 data/logs/frontend_<pid>.log（追加 + 时间戳头）。
验收 2：前端异常退出 → gateway 写 CRITICAL（退出码 + stderr 尾部 50 行内联）。
验收 3：frontend_*.log 滚动——保留最近 20 份，超出清理。
验收 4：_tail_lines 尾部读取（CRITICAL 内联的数据源）。
"""

import os
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

from bobo_tui_gateway import entry as gateway_entry


class BlackBoxStderrTest(unittest.TestCase):
    """验收 1+2：端到端——main() 启动前端，stderr 落盘 + 异常退出 CRITICAL 内联。"""

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="bobo_o7_")
        self._logs = os.path.join(self._tmp, "logs")
        os.makedirs(self._logs, exist_ok=True)
        # 黑匣子目录重定向到 tmp，不碰真实 data/logs
        self._patch_logdir = mock.patch.object(gateway_entry, "_LOG_DIR", self._logs)
        self._patch_logdir.start()
        # TUI 路径注入：main() 不会真去 Popen 仓库 ui-tui/dist/entry.js
        fake_tui = os.path.join(self._tmp, "fake-entry.js")
        with open(fake_tui, "w", encoding="utf-8") as fh:
            fh.write("// fake tui")
        self._patch_tui = mock.patch.object(
            gateway_entry, "_find_tui_path", return_value=fake_tui)
        self._patch_tui.start()
        # 防止 main() 改动测试进程的信号处理
        self._patch_signal = mock.patch.object(gateway_entry.signal, "signal")
        self._patch_signal.start()
        # 防止测试把 info/critical 写进真实 data/logs/bobo.log
        self._patch_info = mock.patch.object(gateway_entry.logger, "info")
        self._patch_info.start()
        # main() 在 BOBO_BACKEND=1 时会走 _run_backend() 后端主循环挂起；
        # 测试进程可能继承该变量（TUI spawn 的后端环境），必须临时移除。
        self._env_backup = os.environ.pop("BOBO_BACKEND", None)

    def tearDown(self):
        if self._env_backup is not None:
            os.environ["BOBO_BACKEND"] = self._env_backup
        self._patch_info.stop()
        self._patch_signal.stop()
        self._patch_tui.stop()
        self._patch_logdir.stop()

    def _run_main_with_fake_frontend(self, stderr_text="BOOM-前端崩溃模拟", exit_code=3):
        """以真 python 子进程模拟 node 前端：写 stderr 后按指定码退出。"""
        real_popen = subprocess.Popen
        script = (
            "import sys; "
            f"sys.stderr.write({stderr_text!r} + chr(10)); "
            f"sys.exit({exit_code})"
        )

        def fake_popen(cmd, *args, **kwargs):
            # 忽略原 node 命令，换成 python 模拟前端；保留 stderr 重定向
            kwargs.pop("preexec_fn", None)
            return real_popen([sys.executable, "-c", script], *args, **kwargs)

        with mock.patch("subprocess.Popen", side_effect=fake_popen):
            gateway_entry.main()

    def test_stderr_persisted_and_critical_inlined(self):
        captured = {}
        with mock.patch.object(
                gateway_entry.logger, "critical",
                side_effect=lambda *a, **k: captured.setdefault("msg", a)):
            self._run_main_with_fake_frontend()

        # 落盘：恰好 1 个 frontend_<pid>.log，含时间戳头 + 模拟前端 stderr 输出
        frontend_logs = [f for f in os.listdir(self._logs)
                         if f.startswith("frontend_") and f.endswith(".log")]
        self.assertEqual(len(frontend_logs), 1,
                         f"应有 1 个 frontend_<pid>.log，实际: {frontend_logs}")
        log_path = os.path.join(self._logs, frontend_logs[0])
        with open(log_path, "r", encoding="utf-8", errors="replace") as fh:
            content = fh.read()
        self.assertIn("=== frontend stderr log started at", content, "应有启动时间戳头")
        self.assertIn("BOOM-前端崩溃模拟", content, "前端 stderr 应持久化落盘")

        # CRITICAL 内联：退出码 + stderr 尾部
        self.assertIn("msg", captured, "前端异常退出应触发 logger.critical")
        msg = captured["msg"]
        self.assertIn("前端子进程异常退出", msg[0], "CRITICAL 标题应包含异常退出")
        self.assertEqual(msg[2], 3, "CRITICAL 应包含退出码 3")
        self.assertIn("BOOM-前端崩溃模拟", msg[3], "CRITICAL 应内联 stderr 尾部")

    def test_normal_exit_no_critical(self):
        captured = {}
        with mock.patch.object(
                gateway_entry.logger, "critical",
                side_effect=lambda *a, **k: captured.setdefault("msg", a)):
            self._run_main_with_fake_frontend(
                stderr_text="normal shutdown", exit_code=0)
        self.assertNotIn("msg", captured, "正常退出不应触发 CRITICAL")


class PruneFrontendLogsTest(unittest.TestCase):
    """验收 3：滚动清理——保留最近 20 份，超出清理。"""

    def test_prune_keeps_latest_20(self):
        tmp = tempfile.mkdtemp(prefix="bobo_o7_prune_")
        now = time.time()
        for i in range(25):
            p = os.path.join(tmp, f"frontend_{1000 + i}.log")
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(f"log {i}\n")
            # i 越大 mtime 越新
            os.utime(p, (now - (25 - i) * 10, now - (25 - i) * 10))
        with mock.patch.object(gateway_entry, "_LOG_DIR", tmp):
            gateway_entry._prune_frontend_logs(keep=20)
        remaining = sorted(os.listdir(tmp))
        self.assertEqual(len(remaining), 20, f"应保留 20 份，实际: {remaining}")
        names = sorted(int(f.split("_")[1].split(".")[0]) for f in remaining)
        self.assertEqual(names, list(range(1005, 1025)), "应保留最新 20 份")

    def test_prune_under_limit_no_cleanup(self):
        tmp = tempfile.mkdtemp(prefix="bobo_o7_prune_")
        for i in range(5):
            with open(os.path.join(tmp, f"frontend_{i}.log"), "w",
                      encoding="utf-8") as fh:
                fh.write("x")
        with mock.patch.object(gateway_entry, "_LOG_DIR", tmp):
            gateway_entry._prune_frontend_logs(keep=20)
        self.assertEqual(len(os.listdir(tmp)), 5, "未超限不应清理")


class TailLinesTest(unittest.TestCase):
    """验收 4：_tail_lines 尾部读取（CRITICAL 内联的数据源）。"""

    def test_tail_last_n_lines(self):
        tmp = tempfile.mkdtemp(prefix="bobo_o7_tail_")
        p = os.path.join(tmp, "x.log")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write("\n".join(f"line{i}" for i in range(100)) + "\n")
        with open(p, "rb") as fh:
            lines = gateway_entry._tail_lines(fh, 10)
        self.assertEqual(lines, [f"line{i}" for i in range(90, 100)])

    def test_tail_empty_file(self):
        tmp = tempfile.mkdtemp(prefix="bobo_o7_tail_")
        p = os.path.join(tmp, "empty.log")
        with open(p, "w", encoding="utf-8"):
            pass
        with open(p, "rb") as fh:
            self.assertEqual(gateway_entry._tail_lines(fh, 50), [])


if __name__ == "__main__":
    unittest.main()
