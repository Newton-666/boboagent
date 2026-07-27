"""时间衰减 + 时效标注 + 草稿生命周期的测试。

feat/memory-time-decay 分支。测试构造伪造时间戳的条目，验证 time_decay、
时效标注、草稿归档的行为。
"""

import json
import os
import sys
from datetime import datetime, timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── helpers ──────────────────────────────────────────────────────

def _days_ago(n: int) -> str:
    """返回 N 天前的 datetime 字符串（YYYY-MM-DD HH:MM 格式）。"""
    dt = datetime.now() - timedelta(days=n)
    return dt.strftime("%Y-%m-%d %H:%M")


def _today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


# ── fixtures ─────────────────────────────────────────────────────

@pytest.fixture
def clean_db(tmp_path, monkeypatch):
    """隔离的知识库，无预置条目。"""
    import tools.v5_memory as vm

    db = tmp_path / "knowledge_base_time_decay.json"
    db.write_text('{"entries": [], "folders": []}', encoding="utf-8")
    monkeypatch.setattr(vm, "MEMORY_DB", str(db))
    monkeypatch.setattr(vm, "_MEMORY_BACKUP", str(tmp_path / "kb_time_decay.bak"))
    # 清空模块级 _load 缓存副作用
    return db


# ══════════════════════════════════════════════════════════════════
# 测试 1：时间衰减 — 8 天前的条目被衰减，今天的条目不受影响
# ══════════════════════════════════════════════════════════════════

class TestTimeDecay:
    def test_old_entry_decays_today_entry_does_not(self, clean_db):
        import tools.v5_memory as vm

        # 手动插入：8 天前的条目
        data = vm._load()
        old = {
            "id": 1,
            "text": "8 天前的事实",
            "type": "general",
            "tags": [],
            "folder": "",
            "timestamp": _days_ago(8),
            "signal_score": 100,
            "last_matched": _days_ago(8),
            "last_time_decay": "",
            "archived": False,
            "is_draft": False,
        }
        # 手动插入：今天的条目
        new = {
            "id": 2,
            "text": "今天的事实",
            "type": "general",
            "tags": [],
            "folder": "",
            "timestamp": _days_ago(0),
            "signal_score": 100,
            "last_matched": _days_ago(0),
            "last_time_decay": "",
            "archived": False,
            "is_draft": False,
        }
        data["entries"].extend([old, new])
        vm._save(data)

        # 执行时间衰减
        vm.time_decay()

        # 验证：旧条目被扣分，新条目不变
        entries = vm.get_entries()
        old_after = next(e for e in entries if e["id"] == 1)
        new_after = next(e for e in entries if e["id"] == 2)
        assert old_after["signal_score"] == 95, f"Expected 95 (100 - 5), got {old_after['signal_score']}"
        assert new_after["signal_score"] == 100, f"Expected 100 (unchanged), got {new_after['signal_score']}"

    def test_30_day_entry_decays_harder(self, clean_db):
        import tools.v5_memory as vm

        data = vm._load()
        old = {
            "id": 3,
            "text": "30 天前的事实",
            "type": "general",
            "tags": [],
            "folder": "",
            "timestamp": _days_ago(30),
            "signal_score": 100,
            "last_matched": _days_ago(30),
            "last_time_decay": "",
            "archived": False,
            "is_draft": False,
        }
        data["entries"].append(old)
        vm._save(data)

        vm.time_decay()
        e = next(e for e in vm.get_entries() if e["id"] == 3)
        assert e["signal_score"] == 90, f"Expected 90 (100 - 10), got {e['signal_score']}"


# ══════════════════════════════════════════════════════════════════
# 测试 2：幂等 — 同日重复调用不重复扣分
# ══════════════════════════════════════════════════════════════════

class TestTimeDecayIdempotent:
    def test_same_day_no_double_decay(self, clean_db):
        import tools.v5_memory as vm

        data = vm._load()
        entry = {
            "id": 10,
            "text": "幂等测试条目",
            "type": "general",
            "tags": [],
            "folder": "",
            "timestamp": _days_ago(10),
            "signal_score": 100,
            "last_matched": _days_ago(10),
            "last_time_decay": "",
            "archived": False,
            "is_draft": False,
        }
        data["entries"].append(entry)
        vm._save(data)

        # 第一次调用
        vm.time_decay()
        e1 = next(e for e in vm.get_entries() if e["id"] == 10)
        assert e1["signal_score"] == 95

        # 同日第二次调用
        vm.time_decay()
        e2 = next(e for e in vm.get_entries() if e["id"] == 10)
        assert e2["signal_score"] == 95, (
            f"幂等失败：同日重复扣分，{e2['signal_score']} != 95"
        )


# ══════════════════════════════════════════════════════════════════
# 测试 3：时效标注 — ≥14 天带标注，新条目干净
# ══════════════════════════════════════════════════════════════════

class TestAgingAnnotation:
    def test_old_memory_has_annotation_young_does_not(self, clean_db):
        import tools.v5_memory as vm

        data = vm._load()
        old = {
            "id": 20,
            "text": "旧记忆",
            "type": "general",
            "tags": [],
            "folder": "",
            "timestamp": _days_ago(20),
            "signal_score": 100,
            "last_matched": _days_ago(20),
            "last_time_decay": "",
            "archived": False,
            "is_draft": False,
        }
        young = {
            "id": 21,
            "text": "新记忆",
            "type": "general",
            "tags": [],
            "folder": "",
            "timestamp": _days_ago(2),
            "signal_score": 100,
            "last_matched": _days_ago(2),
            "last_time_decay": "",
            "archived": False,
            "is_draft": False,
        }
        data["entries"].extend([old, young])
        vm._save(data)

        # get_top_memories 应附加 _age_days
        top = vm.get_top_memories(limit=10)

        old_mem = next(m for m in top if m["id"] == 20)
        young_mem = next(m for m in top if m["id"] == 21)

        assert old_mem.get("_age_days", 0) >= 14, f"旧记忆应有 ≥14 的 _age_days"
        assert young_mem.get("_age_days", 0) < 14, f"新记忆 _age_days 应 < 14"

        # 模拟 proactive 的注入文本拼装逻辑
        def build_conn(mem):
            age = mem.get("_age_days", 0)
            stale_hint = f"（{age} 天前，可能过时）" if age >= 14 else ""
            text = mem.get("text", mem.get("content", ""))
            conn = f"[记忆] {text}{stale_hint}"
            if mem.get("id"):
                conn += f" (id:{mem['id']})"
            return conn

        old_conn = build_conn(old_mem)
        young_conn = build_conn(young_mem)

        assert "可能过时" in old_conn, f"旧记忆应带时效标注: {old_conn}"
        assert "可能过时" not in young_conn, f"新记忆不应带时效标注: {young_conn}"
        assert f"（{old_mem['_age_days']} 天前，可能过时）" in old_conn


# ══════════════════════════════════════════════════════════════════
# 测试 4：草稿生命周期 — 旧草稿自动归档，被引用过的草稿不归档
# ══════════════════════════════════════════════════════════════════

class TestDraftLifecycle:
    def test_old_draft_auto_archives(self, clean_db):
        import tools.v5_memory as vm

        data = vm._load()
        draft = {
            "id": 30,
            "text": "未引用的旧草稿",
            "type": "general",
            "tags": [],
            "folder": "",
            "timestamp": _days_ago(10),
            "signal_score": 25,         # ≤ 30
            "last_matched": _days_ago(10),  # 从未被 bump
            "last_time_decay": "",
            "archived": False,
            "is_draft": True,
        }
        data["entries"].append(draft)
        vm._save(data)

        vm.time_decay()
        e = next(e for e in vm.get_entries() if e["id"] == 30)
        assert e["archived"] is True, "旧草稿应被自动归档"

        # 归档后不再在 get_top_memories 中出现
        top = vm.get_top_memories(limit=10)
        ids = [m["id"] for m in top]
        assert 30 not in ids, "归档草稿不应出现在 top memories 中"

    def test_bumped_draft_not_archived(self, clean_db):
        import tools.v5_memory as vm

        data = vm._load()
        draft = {
            "id": 31,
            "text": "被引用过的草稿",
            "type": "general",
            "tags": [],
            "folder": "",
            "timestamp": _days_ago(10),
            "signal_score": 25,
            "last_matched": _days_ago(1),  # 1 天前被 bump 过
            "last_time_decay": "",
            "archived": False,
            "is_draft": True,
        }
        data["entries"].append(draft)
        vm._save(data)

        vm.time_decay()
        e = next(e for e in vm.get_entries() if e["id"] == 31)
        assert e["archived"] is False, "被 bump 过的草稿不应归档"

    def test_high_score_draft_not_archived(self, clean_db):
        import tools.v5_memory as vm

        data = vm._load()
        draft = {
            "id": 32,
            "text": "高分旧草稿",
            "type": "general",
            "tags": [],
            "folder": "",
            "timestamp": _days_ago(10),
            "signal_score": 80,         # > 30，高分
            "last_matched": _days_ago(10),
            "last_time_decay": "",
            "archived": False,
            "is_draft": True,
        }
        data["entries"].append(draft)
        vm._save(data)

        vm.time_decay()
        e = next(e for e in vm.get_entries() if e["id"] == 32)
        assert e["archived"] is False, "高分草稿不应归档（仍活跃）"


# ══════════════════════════════════════════════════════════════════
# 测试 5：回归 — 现有信号分测试链路
# ══════════════════════════════════════════════════════════════════

class TestSignalScoreRegression:
    def test_decay_all_still_works(self, clean_db):
        """验证 decay_all 行为未被 time_decay 破坏。"""
        import tools.v5_memory as vm
        from datetime import datetime

        data = vm._load()
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        # 一个条目 last_matched < now（会衰减），一个 = now（不衰减）
        untouched = {
            "id": 40,
            "text": "未被匹配",
            "type": "general",
            "tags": [],
            "folder": "",
            "timestamp": "2025-01-01 00:00",
            "signal_score": 80,
            "last_matched": "2025-01-01 00:00",
            "last_time_decay": "",
            "archived": False,
            "is_draft": False,
        }
        matched = {
            "id": 41,
            "text": "刚被匹配",
            "type": "general",
            "tags": [],
            "folder": "",
            "timestamp": now,
            "signal_score": 80,
            "last_matched": now,  # 等于 "现在"
            "last_time_decay": "",
            "archived": False,
            "is_draft": False,
        }
        data["entries"].extend([untouched, matched])
        vm._save(data)

        vm.decay_all()
        e40 = next(e for e in vm.get_entries() if e["id"] == 40)
        e41 = next(e for e in vm.get_entries() if e["id"] == 41)
        assert e40["signal_score"] == 75, f"decay_all 应扣 5 分: {e40['signal_score']}"
        assert e41["signal_score"] == 80, f"本轮匹配过的不应扣分: {e41['signal_score']}"

    def test_score_never_negative(self, clean_db):
        """时间衰减不应将分数打到负数。"""
        import tools.v5_memory as vm

        data = vm._load()
        entry = {
            "id": 50,
            "text": "极低分条目",
            "type": "general",
            "tags": [],
            "folder": "",
            "timestamp": _days_ago(60),
            "signal_score": 2,
            "last_matched": _days_ago(60),
            "last_time_decay": "",
            "archived": False,
            "is_draft": False,
        }
        data["entries"].append(entry)
        vm._save(data)

        vm.time_decay()
        e = next(e for e in vm.get_entries() if e["id"] == 50)
        assert e["signal_score"] >= 0, f"分数不应为负: {e['signal_score']}"
