"""Tests for CheckpointManager — 对话回退系统的保存/查找/恢复/清理。"""

import tempfile
import os

import pytest

from core.checkpoint import CheckpointManager


def make_mgr():
    """构造 CheckpointManager 及其共享资源，返回 4 元组。"""
    history = [{"role": "user", "content": "hello"}]
    file_cps = {}
    tmpdir = tempfile.mkdtemp()
    mgr = CheckpointManager(
        history_getter=lambda: history,
        file_checkpoints_getter=lambda: file_cps,
        workspace_dir=tmpdir,
    )
    return mgr, history, file_cps, tmpdir


class TestSaveAndGet:
    def test_save_adds_checkpoint(self):
        mgr, history, _, __ = make_mgr()
        assert len(mgr.checkpoints) == 0
        mgr.save(label="step_1", current_depth=1, current_tool_round=0)
        assert len(mgr.checkpoints) == 1

    def test_save_captures_history_snapshot(self):
        mgr, history, _, __ = make_mgr()
        history.append({"role": "assistant", "content": "hi"})
        mgr.save(label="step_1", current_depth=1, current_tool_round=0)
        cp = mgr.checkpoints[0]
        assert cp["label"] == "step_1"
        assert len(cp["history"]) == 2
        assert cp["history"][0]["content"] == "hello"
        assert cp["history"][1]["content"] == "hi"

    def test_save_snapshot_is_deep_copy(self):
        """快照是深拷贝，后续修改 history 不影响已保存的快照。"""
        mgr, history, _, __ = make_mgr()
        mgr.save(label="step_1")
        history.append({"role": "assistant", "content": "new_msg"})
        cp = mgr.checkpoints[0]
        assert len(cp["history"]) == 1  # 不是 2


class TestMaxCheckpoints:
    def test_exceed_max_trims_oldest(self):
        mgr, history, _, __ = make_mgr()
        MAX = 20
        for i in range(25):
            history.append({"role": "assistant", "content": f"msg_{i}"})
            mgr.save(label=f"step_{i}")
        assert len(mgr.checkpoints) <= MAX
        # 最老的应该已被删除，最新的还在
        assert mgr.checkpoints[-1]["label"] == "step_24"
        assert mgr.checkpoints[0]["label"] != "step_0"


class TestUndo:
    def test_undo_restores_history(self):
        mgr, history, _, __ = make_mgr()
        mgr.save(label="step_1")
        original_len = len(history)

        # 修改 history
        history.append({"role": "assistant", "content": "new"})
        assert len(history) == original_len + 1

        success, msg, new_history, depth, tool_round, label = mgr.undo()
        assert success
        assert len(new_history) == original_len  # 回到快照
        assert "step_1" in msg

    def test_undo_with_no_checkpoints(self):
        mgr, history, _, __ = make_mgr()
        success, msg, *_ = mgr.undo()
        assert not success
        assert "没有可回退" in msg

    def test_undo_with_single_checkpoint(self):
        """只有一个快照时 undo → 回到该快照。"""
        mgr, history, _, __ = make_mgr()
        mgr.save(label="only")
        history.append({"role": "assistant", "content": "extra"})
        success, msg, new_history, *_ = mgr.undo()
        assert success
        assert len(new_history) == 1


class TestClear:
    def test_clear_empties_checkpoints(self):
        mgr, history, _, __ = make_mgr()
        mgr.save(label="a")
        mgr.save(label="b")
        assert len(mgr.checkpoints) == 2
        mgr.clear()
        assert len(mgr.checkpoints) == 0

    def test_bool_false_after_clear(self):
        mgr, history, _, __ = make_mgr()
        mgr.save(label="a")
        assert bool(mgr) is True
        mgr.clear()
        assert bool(mgr) is False
