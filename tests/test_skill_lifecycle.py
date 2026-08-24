"""D 沉淀生命周期单元测试——状态机/保护/时间锚定/触发工具。"""
import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import unittest.mock as um

import core.skill_lifecycle as lc


def _mk_state_file():
    tmp = Path(tempfile.mkdtemp(prefix="lc_"))
    lc._LIFECYCLE_FILE = tmp / "lifecycle.json"
    return tmp


def _backdate(rec, days):
    rec["last_activity_at"] = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    return rec


def test_register_anchors_now():
    _mk_state_file()
    rec = lc.register_skill("test-skill")
    assert rec["state"] == "active"
    assert rec["agent_created"] is True
    assert rec["last_activity_at"]  # 锚定 now


def test_stale_then_archive():
    _mk_state_file()
    lc.register_skill("old-skill")
    data = lc._load()
    _backdate(data["old-skill"], 70)  # 超过归档线
    lc._save(data)
    counts = lc.apply_transitions()
    assert counts["archived"] == 1
    assert lc._load()["old-skill"]["state"] == "archived"


def test_reactivate_on_use():
    _mk_state_file()
    lc.register_skill("s2")
    data = lc._load()
    _backdate(data["s2"], 30)  # 超过 stale 线（21）未到归档线（60）
    lc._save(data)
    lc.apply_transitions()
    assert lc._load()["s2"]["state"] == "stale"
    lc.mark_used("s2")
    assert lc._load()["s2"]["state"] == "active"


def test_pinned_never_touched():
    _mk_state_file()
    lc.register_skill("pinned-skill")
    lc.set_pinned("pinned-skill")
    data = lc._load()
    _backdate(data["pinned-skill"], 100)
    lc._save(data)
    counts = lc.apply_transitions()
    assert counts["archived"] == 0
    assert lc._load()["pinned-skill"]["state"] == "active"


def test_sediment_skill_creates_routable():
    import tools.sediment_skill as ss
    tmp = Path(tempfile.mkdtemp(prefix="sed_"))
    ss._ROUTABLE_DIR = tmp
    r = ss.sediment_skill("测试流程", "按此流程处理测试", "1. 读测试\n2. 修\n3. 跑")
    assert "沉淀" in r
    files = list(tmp.rglob("standard.md"))
    assert files, "standard.md 应创建"
    assert "测试流程" in files[0].read_text(encoding="utf-8")
