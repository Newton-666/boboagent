"""票 LN-1：MEMORY.md 双向镜像的验收测试。

覆盖 9 项验收：
  1. 新增条目 → 镜像出现对应行（锚点 id 与 JSON 一致）
  2. 覆盖条目 → 镜像行更新，其他行不变
  3. 删除条目 → 镜像行消失
  4. 手改 md 某行 text → JSON 对应条目更新 + human_edited: true + .bak 备份
  5. md 新增无 #id 的行 → JSON 新条目（新 id、信号 100、human_edited）
  6. md 改坏（乱格式）→ JSON 与改前逐字节一致 + 事件 memory.mirror_import_failed
  7. 幂等：连续两次重生成镜像逐字节相同（内容未变不刷新 mtime）
  8. library/ 只读 → add_entry 正常返回（镜像失败静默降级，主流程不受影响）
  9. 全量回归：本票改动不破坏既有测试（由 run_tests 单独跑全量套件验证）

关键约定：knowledge_base.json 仍是运行时真源，md 是用户入口。
"""

import json
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tools.v5_memory as vm
import tools.memory_mirror as mm


@pytest.fixture
def mirror_env(tmp_path, monkeypatch):
    """隔离的知识库 + 镜像环境（monkeypatch 掉真实 data/ 路径）。"""
    db = tmp_path / "knowledge_base.json"
    db.write_text(json.dumps({
        "entries": [
            {
                "id": 1, "text": "hello", "type": "general",
                "timestamp": "2026-01-01 00:00", "signal_score": 100,
                "last_matched": "2026-01-01 00:00", "last_time_decay": "",
                "archived": False, "is_draft": False,
            },
        ],
        "folders": [],
    }, ensure_ascii=False), encoding="utf-8")
    bak = tmp_path / "knowledge_base.json.bak"
    mirror = tmp_path / "library" / "MEMORY.md"

    monkeypatch.setattr(vm, "MEMORY_DB", str(db))
    monkeypatch.setattr(vm, "_MEMORY_BACKUP", str(bak))
    monkeypatch.setattr(mm, "MEMORY_DB", str(db))
    monkeypatch.setattr(mm, "_MEMORY_BACKUP", str(bak))
    monkeypatch.setattr(mm, "MIRROR_PATH", mirror)
    monkeypatch.setattr(mm, "LIBRARY_DIR", mirror.parent)
    return {"db": db, "bak": bak, "mirror": mirror}


def _touch_newer(path, ref_path):
    """把 path 的 mtime 拉到 ref_path 之后，模拟"刚被手改"。"""
    t = os.stat(ref_path).st_mtime + 10
    os.utime(path, (t, t))


def _read_entries(db_path):
    return json.loads(db_path.read_text(encoding="utf-8"))["entries"]


# ── 验收 1：新增条目 → 镜像同步 ──────────────────────

def test_add_entry_writes_mirror(mirror_env):
    entry = vm.add_entry("新记忆ABC", entry_type="knowledge")
    assert entry is not None
    assert mirror_env["mirror"].exists()
    content = mirror_env["mirror"].read_text(encoding="utf-8")
    assert f"[#{entry['id']}] 新记忆ABC" in content
    # 小节按 type 分
    assert "## knowledge" in content


# ── 验收 2：覆盖条目 → 镜像行更新，其他行不变 ─────────

def test_update_entry_syncs_mirror(mirror_env):
    vm.add_entry("陪跑条目")
    assert vm.update_entry(1, "新文本Y") is not None
    content = mirror_env["mirror"].read_text(encoding="utf-8")
    assert "[#1] 新文本Y" in content
    assert "[#1] hello" not in content
    assert "陪跑条目" in content  # 其他行不受影响


# ── 验收 3：删除条目 → 镜像行消失 ─────────────────────

def test_delete_entry_syncs_mirror(mirror_env):
    entry = vm.add_entry("待删除条目")
    assert "待删除条目" in mirror_env["mirror"].read_text(encoding="utf-8")
    result = vm.delete_entry(entry["id"], reason="user_request")
    assert result.get("success") is True
    content = mirror_env["mirror"].read_text(encoding="utf-8")
    assert "待删除条目" not in content
    assert "[#1] hello" in content  # 其他行不受影响


# ── 验收 4：手改 md → JSON 更新 + human_edited + .bak ─

def test_manual_edit_imports_to_json(mirror_env):
    mm.sync_mirror()
    content = mirror_env["mirror"].read_text(encoding="utf-8")
    new_content = content.replace("[#1] hello", "[#1] 用户手改的记忆")
    mirror_env["mirror"].write_text(new_content, encoding="utf-8")
    _touch_newer(mirror_env["mirror"], mirror_env["db"])

    n = mm.import_from_md()
    assert n == 1
    entries = _read_entries(mirror_env["db"])
    e1 = [e for e in entries if e["id"] == 1][0]
    assert e1["text"] == "用户手改的记忆"
    assert e1.get("human_edited") is True
    # .bak 备份存在
    assert mirror_env["bak"].exists()
    # 导入后 mtime 对齐：再次导入不重复触发
    assert mm.import_from_md() == 0


# ── 验收 5：md 新增行 → JSON 新条目（新 id、信号 100）──

def test_new_line_imports_as_new_entry(mirror_env):
    mm.sync_mirror()
    mirror_env["mirror"].write_text(
        mirror_env["mirror"].read_text(encoding="utf-8") + "\n- 用户手写的新记忆\n",
        encoding="utf-8",
    )
    _touch_newer(mirror_env["mirror"], mirror_env["db"])

    n = mm.import_from_md()
    assert n == 1
    entries = _read_entries(mirror_env["db"])
    new = [e for e in entries if e["text"] == "用户手写的新记忆"]
    assert len(new) == 1
    assert new[0]["id"] == 2  # 新 id = max+1
    assert new[0]["signal_score"] == 100
    assert new[0].get("human_edited") is True


# ── 验收 6：md 改坏 → JSON 逐字节一致 + 事件落地 ──────

def test_parse_fail_degrade(mirror_env):
    mm.sync_mirror()
    before = mirror_env["db"].read_text(encoding="utf-8")
    broken = mirror_env["mirror"].read_text(encoding="utf-8").replace(
        "[#1] hello", "[#abc] 乱格式"
    )
    mirror_env["mirror"].write_text(broken, encoding="utf-8")
    _touch_newer(mirror_env["mirror"], mirror_env["db"])

    n = mm.import_from_md()
    assert n == -1
    # JSON 与改前逐字节一致（保守降级）
    assert mirror_env["db"].read_text(encoding="utf-8") == before
    # 事件 memory.mirror_import_failed 落地
    from core.event_bus import event_bus as _ebus
    log = _ebus._log_path.read_text(encoding="utf-8")
    assert "memory.mirror_import_failed" in log


# ── 验收 7：幂等 ─────────────────────────────────────

def test_idempotent_sync(mirror_env):
    vm.add_entry("记忆A")
    vm.add_entry("记忆B")
    mm.sync_mirror()
    content1 = mirror_env["mirror"].read_text(encoding="utf-8")
    mtime1 = os.stat(mirror_env["mirror"]).st_mtime_ns
    mm.sync_mirror()
    content2 = mirror_env["mirror"].read_text(encoding="utf-8")
    mtime2 = os.stat(mirror_env["mirror"]).st_mtime_ns
    assert content1 == content2  # 逐字节相同
    assert mtime1 == mtime2  # 内容未变不刷新 mtime（防启动导入误判）


# ── 验收 8：library/ 只读 → 静默降级，主流程不受影响 ──

def test_readonly_library_no_crash(mirror_env):
    mirror_env["mirror"].parent.mkdir(parents=True, exist_ok=True)
    os.chmod(mirror_env["mirror"].parent, 0o555)
    try:
        entry = vm.add_entry("只读降级测试")
        assert entry is not None  # 主流程不受影响
        # JSON 确实写入了
        entries = _read_entries(mirror_env["db"])
        assert any(e["text"] == "只读降级测试" for e in entries)
    finally:
        os.chmod(mirror_env["mirror"].parent, 0o755)


# ── 验收 4b：md 里新增 + 手改混合导入（一次导入多变更）──

def test_mixed_import_changes(mirror_env):
    mm.sync_mirror()
    content = mirror_env["mirror"].read_text(encoding="utf-8")
    content = content.replace("[#1] hello", "[#1] 改过的旧条目")
    content = content.rstrip("\n") + "\n- 另一条手写记忆\n"
    mirror_env["mirror"].write_text(content, encoding="utf-8")
    _touch_newer(mirror_env["mirror"], mirror_env["db"])

    n = mm.import_from_md()
    assert n == 2  # 1 更新 + 1 新增
    entries = _read_entries(mirror_env["db"])
    texts = {e["text"] for e in entries}
    assert "改过的旧条目" in texts
    assert "另一条手写记忆" in texts
