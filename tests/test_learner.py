"""C2/C3 落笔与生命周期单元测试。"""
import json
import sys
import tempfile
from pathlib import Path

import unittest.mock as um

from core.learner import write_lesson, prune_memory


def _mk_db():
    tmp = Path(tempfile.mkdtemp(prefix="learner_"))
    db = tmp / "kb.json"
    import tools.v5_memory as vm
    return tmp, db, vm


def test_write_lesson_creates_lesson_entry():
    tmp, db, vm = _mk_db()
    with um.patch.object(vm, "_memory_db", lambda: str(db)):
        ok = write_lesson("edit_file", "regex", 3)
        assert ok
        entries = vm._load()["entries"]
        assert entries and entries[0]["type"] == "LESSON"
        assert "edit_file" in entries[0]["text"] and "regex" in entries[0]["text"]


def test_prune_archives_lowest_when_over_capacity():
    tmp, db, vm = _mk_db()
    with um.patch.object(vm, "_memory_db", lambda: str(db)):
        # 塞满容量（MAX_TOTAL_CHARS=100000 太大——用 50 字符测试）
        for i in range(10):
            vm.save_to_knowledge_base("x" * 20 + str(i), entry_type="FACT")
        total = sum(len(e["text"]) for e in vm._load()["entries"])
        assert total > 50
        n = prune_memory(max_total_chars=50)
        assert n >= 1, "应归档至少 1 条"
        data = vm._load()
        # 可逆语义：归档条目仍在存储（不占 token，但占存储）；容量控制作用于活跃条目
        remaining = sum(len(e["text"]) for e in data["entries"] if not e.get("archived"))
        assert remaining <= 50
        # 可逆：归档不是删除
        archived = [e for e in data["entries"] if e.get("archived")]
        assert archived, "归档条目应保留（可逆）"


def test_prune_noop_within_capacity():
    tmp, db, vm = _mk_db()
    with um.patch.object(vm, "_memory_db", lambda: str(db)):
        vm.save_to_knowledge_base("short", entry_type="FACT")
        assert prune_memory(max_total_chars=100000) == 0


def test_write_lesson_requires_save():
    tmp, db, vm = _mk_db()
    with um.patch.object(vm, "_memory_db", lambda: str(db)):
        assert write_lesson("run_tests", "path", 5) is True
        assert len(vm._load()["entries"]) == 1
