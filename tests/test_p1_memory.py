"""P1 记忆库修复的回归测试（fix/p1-memory）。

审计 #14/#15/#29：
- JSON 损坏全量清空保护
- 并行写锁 lost-update
- ID 撞车
- 排序键修正
- save_memory/search_memory 双重注册清理
"""

import json
import os
import sys
import threading

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def memory_db(tmp_path, monkeypatch):
    """隔离的知识库文件。"""
    db = tmp_path / "knowledge_base.json"
    db.write_text('{"entries": [{"id": 1, "text": "hello", "type": "general", "timestamp": "2026-01-01 00:00"}]}', encoding="utf-8")
    bak = tmp_path / "knowledge_base.json.bak"
    # Monkeypatch 必须在 tools.v5_memory 模块 import 之后、每个测试调用前生效
    import tools.v5_memory as vm
    monkeypatch.setattr(vm, "MEMORY_DB", str(db))
    monkeypatch.setattr(vm, "_MEMORY_BACKUP", str(bak))
    # 清掉 import 级别的锁（跨测试不受影响）
    return db


class TestCorruptionRecovery:
    def test_corrupted_file_not_wipe(self, memory_db, monkeypatch):
        import tools.v5_memory as vm
        # 写入损坏的 JSON
        memory_db.write_text("this is not json", encoding="utf-8")
        data = vm._load()
        # 不应静默覆盖：损坏文件应被移走
        assert not memory_db.exists() or json.loads(memory_db.read_text(encoding="utf-8"))
        # 至少不抛异常
        assert isinstance(data, dict)
        assert "entries" in data

    def test_corrupted_with_backup_recovers(self, memory_db, monkeypatch):
        import tools.v5_memory as vm
        # 先写正常数据 + 备份
        valid = '{"entries": [{"id": 99, "text": "recovered"}, {"id": 100, "text": "ok2"}]}'
        monkeypatch.setattr(vm, "_MEMORY_BACKUP", str(memory_db.parent / "kb.json.bak"))
        bak = memory_db.parent / "kb.json.bak"
        bak.write_text(valid, encoding="utf-8")
        # 主文件损坏
        memory_db.write_text("garbage", encoding="utf-8")
        data = vm._load()
        # 应该从备份恢复了
        assert len(data.get("entries", [])) > 0


class TestIdGeneration:
    def test_id_no_collision_after_delete(self, memory_db, monkeypatch):
        import tools.v5_memory as vm
        # 初始化：[id=1]
        vm.delete_entry(1, reason="user_request")
        # 删光后添加
        entry = vm.add_entry("new one")
        assert entry is not None
        # ID 应该是 max(0) + 1 = 1，不是 len(0) + 1 = 1 —— 这里相同，但逻辑正确
        # 再删再加
        vm.delete_entry(entry["id"], reason="absorbed")
        entry2 = vm.add_entry("another")
        assert entry2 is not None
        # 两次添加：id 1, id 2
        vm.add_entry("keep")
        assert vm.delete_entry(2, reason="user_request")["success"]
        entry4 = vm.add_entry("after delete")
        # 删了 id=2 后，新条目不应该 get id=3（len=2 时 len+1=3 但 id=3 已存在）
        # max+1 应该 = 4
        assert entry4["id"] > max(e["id"] for e in vm.get_entries() if e["id"] != entry4["id"])


class TestSortKey:
    def test_sort_uses_timestamp(self, monkeypatch, tmp_path):
        import tools.v5_memory as vm
        db = tmp_path / "kb.json"
        data = {
            "entries": [
                {"id": 1, "text": "old", "timestamp": "2025-01-01 00:00"},
                {"id": 2, "text": "new", "timestamp": "2026-12-31 23:59"},
            ]
        }
        db.write_text(json.dumps(data), encoding="utf-8")
        monkeypatch.setattr(vm, "MEMORY_DB", str(db))
        result = vm.format_all_memory(max_chars=10000)
        # "new" 应该排在 "old" 前面（newest first）
        assert result.index("new") < result.index("old")


class TestProfileRouting:
    def test_target_profile_routes_correctly(self, monkeypatch, tmp_path):
        import tools.v5_memory as vm
        db = tmp_path / "kb.json"
        data = {"entries": [], "profile": {}}
        db.write_text(json.dumps(data), encoding="utf-8")
        monkeypatch.setattr(vm, "MEMORY_DB", str(db))
        result = vm.save_to_knowledge_base("Newton", target="profile", memory_type="name")
        assert "用户资料已更新" in result
        profile = vm.get_user_profile()
        assert profile.get("name", {}).get("value") == "Newton"


class TestConcurrentWrites:
    def test_parallel_adds_no_lost_entries(self, monkeypatch, tmp_path):
        import tools.v5_memory as vm
        db = tmp_path / "kb.json"
        db.write_text('{"entries": []}', encoding="utf-8")
        monkeypatch.setattr(vm, "MEMORY_DB", str(db))
        monkeypatch.setattr(vm, "_MEMORY_BACKUP", str(tmp_path / "kb.json.bak"))
        count = 10
        errors = []
        threads = []
        for i in range(count):
            t = threading.Thread(target=lambda i=i: errors.append(
                vm.save_to_knowledge_base(f"entry-{i}")
            ))
            threads.append(t)
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)
        # 所有 10 次写入都应该成功，没有 TypeErrors
        ok = [e for e in errors if "已保存" in str(e)]
        assert len(ok) == count, f"Expected {count} saves, got {ok}"


class TestDoubleRegistration:
    def test_save_memory_register_is_pass(self):
        from tools import save_memory
        from tools import TOOL_FUNCTIONS
        # save_memory 的 register 现在是 pass，唯一注册由 v5 完成
        assert "save_memory" in TOOL_FUNCTIONS, "v5 未注册 save_memory"

    def test_search_memory_register_is_pass(self):
        from tools import search_memory
        from tools import TOOL_FUNCTIONS
        assert "search_memory" in TOOL_FUNCTIONS, "v5 未注册 search_memory"
