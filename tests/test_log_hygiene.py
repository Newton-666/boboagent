"""TICKET-E1b：log 卫生——stack_dump 环形快照验收测试。

验收 1：环形快照——覆盖写、体积不累积（文件恒定只留最新一屏）。
验收 2：BOBO_STACK_DUMP=1 → 连拍（append）模式，与旧版一致。
验收 3：人为造线程阻塞（sleep 600），下一屏快照能看到该线程堆栈。
验收 4：docs/战役卷宗/ 含归档 .gz，原 data/logs/ 对应文件已移出。
"""

import glob
import os
import sys
import tempfile
import threading
import time
import unittest

from bobo_tui_gateway import entry as gateway_entry


class RingSnapshotTest(unittest.TestCase):
    """验收 1：环形快照——覆盖写 + 体积不累积。"""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.dump_path = os.path.join(self._tmp, "stack_dump.log")

    def test_ring_overwrites_and_no_growth(self):
        # 短间隔跑快照循环，等 ≥2 个写周期
        loop = threading.Thread(
            target=gateway_entry._snapshot_loop,
            args=(self.dump_path, 0.3),
            daemon=True,
        )
        loop.start()
        time.sleep(0.8)

        size1 = os.path.getsize(self.dump_path)
        mtime1 = os.path.getmtime(self.dump_path)
        self.assertGreater(size1, 0, "第一屏快照应为非空")

        time.sleep(0.7)  # 再等 1 周期
        size2 = os.path.getsize(self.dump_path)
        mtime2 = os.path.getmtime(self.dump_path)

        # mtime 更新 = 覆盖写发生
        self.assertGreater(mtime2, mtime1, "快照应持续覆盖写")
        # 体积不累积（同屏 dump 内容量级一致）
        self.assertLessEqual(abs(size2 - size1), 512, "环形快照体积不应累积")


class AppendModeTest(unittest.TestCase):
    """验收 2：BOBO_STACK_DUMP=1 → 连拍（append）模式。"""

    def test_setup_returns_append(self):
        os.environ["BOBO_STACK_DUMP"] = "1"
        try:
            tmp = tempfile.mkdtemp()
            mode = gateway_entry._setup_stack_dump(tmp)
            self.assertEqual(mode, "append")
            # 连拍模式下文件被创建（a 模式打开即创建）
            self.assertTrue(os.path.exists(os.path.join(tmp, "stack_dump.log")))
        finally:
            os.environ.pop("BOBO_STACK_DUMP", None)

    def test_setup_default_returns_ring(self):
        os.environ.pop("BOBO_STACK_DUMP", None)
        tmp = tempfile.mkdtemp()
        mode = gateway_entry._setup_stack_dump(tmp)
        self.assertEqual(mode, "ring")


class StuckThreadVisibleTest(unittest.TestCase):
    """验收 3：人为造线程阻塞（sleep 600），快照能看到该线程堆栈。"""

    def test_stuck_thread_stack_visible(self):
        tmp = tempfile.mkdtemp()
        dump_path = os.path.join(tmp, "stack_dump.log")

        def stuck():
            time.sleep(600)  # 模拟卡死

        threading.Thread(target=stuck, name="artificial-stuck-thread", daemon=True).start()

        loop = threading.Thread(
            target=gateway_entry._snapshot_loop, args=(dump_path, 0.3), daemon=True
        )
        loop.start()
        time.sleep(0.8)

        content = open(dump_path, encoding="utf-8", errors="replace").read()
        # 阻塞线程的堆栈帧必须在快照中可见（Python 3.11+ 均成立）
        self.assertIn("stuck", content, "阻塞线程的堆栈帧应在快照中可见")
        # 线程名 [name] 是 Python 3.14 faulthandler 才有的输出；3.11/3.12/3.13 仅显示 Thread 0x 地址
        if sys.version_info >= (3, 14):
            self.assertIn("artificial-stuck-thread", content, "阻塞线程名应出现在快照中")


class BattleArchiveTest(unittest.TestCase):
    """验收 4：大战卷宗归档。"""

    def test_archives_gzipped_and_originals_moved(self):
        archive_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "docs",
            "战役卷宗",
        )
        self.assertTrue(os.path.isdir(archive_dir), "docs/战役卷宗/ 应存在")
        gz_files = sorted(glob.glob(os.path.join(archive_dir, "*.gz")))
        # 实际存在的卷宗（07-31、08-01）都已归档；07-27~07-30 在 data/logs 中不存在
        self.assertGreaterEqual(len(gz_files), 1, "战役卷宗应至少含 1 个 .gz")
        for gz in gz_files:
            self.assertGreater(os.path.getsize(gz), 0, f"{gz} 应为非空 gzip")

        # 原文件已移出 data/logs
        logs_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "logs"
        )
        for f in ("bobo.log.2026-07-31", "bobo.log.2026-08-01"):
            self.assertFalse(
                os.path.exists(os.path.join(logs_dir, f)),
                f"原文件 {f} 应已移出 data/logs",
            )


if __name__ == "__main__":
    unittest.main()
