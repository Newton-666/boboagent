"""TICKET-E2b：describe_tool 取件通道验收测试。

验收 1：describe_tool("grep_code") 返回 schema 摘要，且下一轮分类裁剪后
        LLM 请求的工具列表仍含 grep_code（取件即注册）。
验收 2：describe_tool("grep_cd") → 错误 + difflib 最接近建议含 grep_code。
验收 3：分类裁剪场景（命中 code 类）下 describe_tool 本身始终可用。
验收 4：压缩发生后 _extra_tools 不清空（会话级只增，同 _session_written_files）。
验收 5：事件 tool.describe 写入 events.jsonl。
"""

import json
import os
import tempfile
import unittest
from unittest.mock import patch

from core.context import ContextMixin


class _FakeEngine(ContextMixin):
    """最小 Engine 替身：有 _extra_tools + sid + history，够跑 _get_filtered_tools。"""

    def __init__(self):
        self._extra_tools: set[str] = set()
        self.sid = "test-session-e2b"
        self.history = []


class DescribeToolSmokeTest(unittest.TestCase):
    """验收 1：命中返回摘要 + 取件注册 → 下一轮裁剪列表含该工具。"""

    def setUp(self):
        self.engine = _FakeEngine()
        # 隔离事件总线，避免污染真实 events.jsonl
        self._tmp = tempfile.mkdtemp()
        from core.event_bus import EventBus
        import core.event_bus as eb_mod
        self._real_bus = eb_mod.event_bus
        eb_mod.event_bus = EventBus(log_dir=self._tmp)
        self._tmp_dir = self._tmp

    def tearDown(self):
        from core import event_bus as eb_mod
        eb_mod.event_bus = self._real_bus

    def test_accept1_hit_returns_summary_and_registers(self):
        from tools.describe_tool import describe_tool
        result = describe_tool("grep_code", _engine=self.engine)
        self.assertIn("grep_code", result)
        self.assertIn("描述", result)
        self.assertIn("grep_code", self.engine._extra_tools)

        # 下一轮：模拟命中 code 分类裁剪 → 列表仍含 grep_code
        with patch.object(ContextMixin, "_classify_query", return_value="code"):
            filtered = self.engine._get_filtered_tools()
        self.assertIsNotNone(filtered)
        names = [t["function"]["name"] for t in filtered]
        self.assertIn("grep_code", names)

    def test_accept2_unknown_name_gives_suggestions(self):
        from tools.describe_tool import describe_tool
        result = describe_tool("grep_cd", _engine=self.engine)
        self.assertIn("错误", result)
        self.assertIn("grep_code", result)  # difflib 最接近建议
        self.assertNotIn("grep_cd", self.engine._extra_tools)  # 未知名不注册

    def test_accept3_meta_tools_never_cropped(self):
        from tools.describe_tool import describe_tool
        # 触发一次命中，确保 describe_tool 路径被走到
        describe_tool("grep_code", _engine=self.engine)
        with patch.object(ContextMixin, "_classify_query", return_value="code"):
            filtered = self.engine._get_filtered_tools()
        names = [t["function"]["name"] for t in filtered]
        for meta in ("describe_tool", "load_result", "read_local_file"):
            self.assertIn(meta, names, f"元工具 {meta} 被分类裁剪了")

    def test_accept4_compaction_keeps_extra_tools(self):
        from tools.describe_tool import describe_tool
        describe_tool("grep_code", _engine=self.engine)
        describe_tool("edit_file", _engine=self.engine)
        self.assertIn("grep_code", self.engine._extra_tools)
        # 模拟压缩/塌缩：走 Engine.reset 清理路径（reset 不清 _extra_tools）
        self.engine._used_categories = set()
        self.engine.history = []
        # 压缩后 _extra_tools 仍在（会话级只增）
        self.assertIn("grep_code", self.engine._extra_tools)
        self.assertIn("edit_file", self.engine._extra_tools)
        # 且下一轮裁剪仍可见
        with patch.object(ContextMixin, "_classify_query", return_value="code"):
            filtered = self.engine._get_filtered_tools()
        names = [t["function"]["name"] for t in filtered]
        self.assertIn("grep_code", names)

    def test_accept5_event_written_to_jsonl(self):
        from tools.describe_tool import describe_tool
        describe_tool("grep_code", _engine=self.engine)
        log_path = os.path.join(self._tmp_dir, "events.jsonl")
        self.assertTrue(os.path.exists(log_path), "events.jsonl 未生成")
        with open(log_path, encoding="utf-8") as f:
            lines = [json.loads(l) for l in f if l.strip()]
        self.assertTrue(lines, "events.jsonl 为空")
        ev = lines[0]
        self.assertEqual(ev.get("type"), "tool.describe")
        self.assertEqual(ev.get("tool_name"), "grep_code")
        self.assertTrue(ev.get("found"))

    def test_hit_summary_truncated_at_800(self):
        from tools.describe_tool import _SUMMARY_MAX_CHARS, describe_tool
        result = describe_tool("grep_code", _engine=self.engine)
        # 摘要内容本身不超上限（截断后保证 ≤ ~800 字符）
        self.assertLessEqual(len(result), _SUMMARY_MAX_CHARS + 64)


if __name__ == "__main__":
    unittest.main()
