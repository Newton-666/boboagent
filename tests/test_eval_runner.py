"""TICKET-EV1 EVAL 跑道 v1 —— 执行器自测。

验收 1：五种 judge 规则各有单测（tool_call_count / event_exists / file_md5 /
       reply_contains / pytest_green），全部可判定。
验收 2：md5 闸门——快照正确性 + 真实库前后一致（隔离红线）。
验收 3：题库 yaml 完整性——15 题、judge 类型覆盖五种、blocked 题带原因。
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import eval_runner as er


def _mk_ev(reply="", tool_calls=None, events=None, state=None):
    return {
        "reply": reply,
        "tool_calls": tool_calls or [],
        "events": events or [],
        "state": state or {},
    }


class JudgeToolCallCountTest(unittest.TestCase):
    """验收 1a：tool_call_count。"""

    def test_count_equal(self):
        ev = _mk_ev(tool_calls=[
            {"name": "read_obsidian", "args": {}},
            {"name": "search_obsidian", "args": {}},
            {"name": "get_current_time", "args": {}},
        ])
        ok, detail = er._j_tool_count({"type": "tool_call_count",
                                       "tool": "(read_obsidian|search_obsidian)",
                                       "op": "==", "value": 2}, ev)
        self.assertTrue(ok)
        self.assertEqual(detail["actual"], 2)

    def test_count_zero(self):
        ev = _mk_ev(tool_calls=[{"name": "get_current_time", "args": {}}])
        ok, _ = er._j_tool_count({"type": "tool_call_count",
                                  "tool": ".*", "op": "==", "value": 0}, ev)
        self.assertFalse(ok)

    def test_count_le(self):
        ev = _mk_ev(tool_calls=[
            {"name": "read_obsidian", "args": {}},
            {"name": "read_obsidian", "args": {}},
            {"name": "get_current_time", "args": {}},
        ])
        ok, detail = er._j_tool_count({"type": "tool_call_count",
                                       "tool": "(read_obsidian|search_obsidian)",
                                       "op": "<=", "value": 2}, ev)
        self.assertTrue(ok)
        self.assertEqual(detail["actual"], 2)

    def test_unique_by_same_id(self):
        # E3：同一结果 id 的 load_result ≤1
        ev = _mk_ev(tool_calls=[
            {"name": "load_result", "args": {"id": "3_abc"}},
            {"name": "load_result", "args": {"id": "3_abc"}},
            {"name": "load_result", "args": {"id": "3_xyz"}},
        ])
        ok, detail = er._j_tool_count({"type": "tool_call_count",
                                       "tool": "load_result", "op": "<=",
                                       "value": 1,
                                       "unique_by": "result_id|id"}, ev)
        self.assertFalse(ok)  # 同一 id 出现 2 次 > 1
        self.assertEqual(detail["actual"], 2)


class JudgeEventExistsTest(unittest.TestCase):
    """验收 1b：event_exists。"""

    def test_event_with_field_value(self):
        ev = _mk_ev(events=[
            {"type": "goal_gate.deny",
             "data": {"reason": "ledger_backfill", "session_id": "s1"}},
        ])
        ok, _ = er._j_event({"type": "event_exists", "event": "goal_gate.deny",
                             "field": "reason", "value": "ledger_backfill"}, ev)
        self.assertTrue(ok)

    def test_event_absent(self):
        ev = _mk_ev(events=[{"type": "state.change", "data": {}}])
        ok, _ = er._j_event({"type": "event_exists", "event": "office.guard",
                             "absent": True}, ev)
        self.assertTrue(ok)

    def test_event_missing_field(self):
        ev = _mk_ev(events=[{"type": "goal_gate.deny", "data": {"reason": "other"}}])
        ok, _ = er._j_event({"type": "event_exists", "event": "goal_gate.deny",
                             "field": "reason", "value": "ledger_backfill"}, ev)
        self.assertFalse(ok)


class JudgeFileMd5Test(unittest.TestCase):
    """验收 1c：file_md5。"""

    def test_pair_equal(self):
        tmp = tempfile.mkdtemp()
        a, b = Path(tmp) / "a.js", Path(tmp) / "b.js"
        a.write_text("same", encoding="utf-8")
        b.write_text("same", encoding="utf-8")
        ev = _mk_ev(state={"files": {"a.js": er._md5_file(a),
                                     "b.js": er._md5_file(b)}})
        ok, _ = er._j_md5({"type": "file_md5", "pair": ["a.js", "b.js"]}, ev)
        self.assertTrue(ok)
        b.write_text("different", encoding="utf-8")
        ev = _mk_ev(state={"files": {"a.js": er._md5_file(a),
                                     "b.js": er._md5_file(b)}})
        ok, _ = er._j_md5({"type": "file_md5", "pair": ["a.js", "b.js"]}, ev)
        self.assertFalse(ok)
        shutil.rmtree(tmp)

    def test_unchanged(self):
        ev = _mk_ev(state={"file_md5_before": "abc", "file_md5_after": "abc"})
        ok, _ = er._j_md5({"type": "file_md5", "path": "x.py", "unchanged": True}, ev)
        self.assertTrue(ok)
        ev = _mk_ev(state={"file_md5_before": "abc", "file_md5_after": "def"})
        ok, _ = er._j_md5({"type": "file_md5", "path": "x.py", "unchanged": True}, ev)
        self.assertFalse(ok)


class JudgeReplyContainsTest(unittest.TestCase):
    """验收 1d：reply_contains。"""

    def test_match(self):
        ev = _mk_ev(reply="需要一张票据授权才能修改该文件。")
        ok, _ = er._j_reply({"type": "reply_contains",
                             "pattern": "(票据|授权|ticket)"}, ev)
        self.assertTrue(ok)

    def test_no_match(self):
        ev = _mk_ev(reply="好的，我马上改。")
        ok, _ = er._j_reply({"type": "reply_contains",
                             "pattern": "(票据|授权|ticket)"}, ev)
        self.assertFalse(ok)


class JudgePytestGreenTest(unittest.TestCase):
    """验收 1e：pytest_green（用临时目录里的真实小测试验证机制）。"""

    def test_green_and_red(self):
        tmp = Path(tempfile.mkdtemp())
        (tmp / "test_x.py").write_text(
            "def test_ok():\n    assert 1 == 1\n", encoding="utf-8")
        env = {"repo": tmp, "env": os.environ.copy()}
        ok, detail = er._j_pytest({"type": "pytest_green", "path": "test_x.py"},
                                  _mk_ev(), env)
        self.assertTrue(ok)
        self.assertGreaterEqual(detail["passed"], 1)
        self.assertEqual(detail["failed"], 0)

        (tmp / "test_x.py").write_text(
            "def test_bad():\n    assert 1 == 2\n", encoding="utf-8")
        ok, detail = er._j_pytest({"type": "pytest_green", "path": "test_x.py"},
                                  _mk_ev(), env)
        self.assertFalse(ok)
        self.assertGreaterEqual(detail["failed"], 1)
        shutil.rmtree(tmp)


class Md5GateTest(unittest.TestCase):
    """验收 2：md5 闸门。"""

    def test_md5_tree_snapshot_stable(self):
        tmp = Path(tempfile.mkdtemp())
        (tmp / "a.md").write_text("hello", encoding="utf-8")
        (tmp / "b.txt").write_text("world", encoding="utf-8")
        os.makedirs(tmp / "logs")
        (tmp / "logs" / "run.log").write_text("noise", encoding="utf-8")
        snap = er._md5_tree(tmp)
        self.assertIn("a.md", snap)
        self.assertIn("b.txt", snap)
        self.assertNotIn("logs/run.log", snap, "日志应被排除")
        snap2 = er._md5_tree(tmp)
        self.assertEqual(snap, snap2, "快照应稳定可复现")
        shutil.rmtree(tmp)

    def test_gate_diff_detects_change(self):
        tmp = Path(tempfile.mkdtemp())
        (tmp / "library").mkdir()
        (tmp / "library" / "lib.md").write_text("v1", encoding="utf-8")
        with mock.patch.object(er, "ROOT", tmp):
            before = er._gate_snapshot()
            # 模拟真实库被污染
            (tmp / "library" / "lib.md").write_text("v2", encoding="utf-8")
            after = er._gate_snapshot()
            diff = er._gate_diff(before, after)
            self.assertTrue(diff, "闸门应检测到真实库变化")
        shutil.rmtree(tmp)


class QuestionYamlIntegrityTest(unittest.TestCase):
    """验收 3：题库 yaml 完整性。"""

    def test_15_questions_and_judge_types(self):
        qs = er._load_questions()
        ids = [q["id"] for q in qs]
        self.assertEqual(len(ids), 15, f"应有 15 题，实际 {len(ids)}")
        expected = [f"A{i}" for i in range(1, 9)] + \
                   [f"B{i}" for i in range(1, 5)] + \
                   [f"E{i}" for i in range(1, 4)]
        self.assertEqual(sorted(ids), sorted(expected))

        def _iter_rules(q):
            j = q.get("judge", [])
            if isinstance(j, dict) and "any_of" in j:
                for group in j["any_of"]:
                    if isinstance(group, dict) and "all_of" in group:
                        yield from group["all_of"]
                    else:
                        yield group
            else:
                yield from j

        all_types = set()
        for q in qs:
            for rule in _iter_rules(q):
                all_types.add(rule.get("type"))
        self.assertEqual(all_types, {"tool_call_count", "event_exists",
                                     "file_md5", "reply_contains", "pytest_green"},
                         "五种 judge 类型应全覆盖")

    def test_blocked_questions_have_reason(self):
        qs = er._load_questions()
        blocked = [q for q in qs if q.get("status") == "blocked"]
        self.assertTrue(blocked, "A5/A7/A8 应标 blocked")
        for q in blocked:
            self.assertTrue(q.get("blocked_reason"), f"{q['id']} 缺 blocked_reason")

    def test_scene_and_expected_present(self):
        qs = er._load_questions()
        for q in qs:
            self.assertTrue(q.get("scene"), f"{q['id']} 缺 scene")
            self.assertTrue(q.get("expected"), f"{q['id']} 缺 expected")


if __name__ == "__main__":
    unittest.main()
