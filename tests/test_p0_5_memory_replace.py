"""票 P0-5 专项测试 — 记忆偏好变更替换 + memory.changed 事件 + 前端实时刷新。

覆盖（票据验收 1-4）：
- 替换触发：同主题 + 反转关键词 → 旧条 archived + signal_score 归零 + 新条
  写入 + 审计 REPLACE（from_id→to_id 留痕）
- 不触发：普通新增（无反转词）/ 同主题但不相反 → 旧条不动
- 确定性：同一输入两次跑，库状态与审计结果一致（零 LLM 判据）
- 事件：add / delete / replace 后 event_bus 收到 memory.changed
- 前端静态断言：dist/index.html 含 on('memory.changed') handler + 打开重载
- 零动作回归：替换路径不写 signal_log.jsonl（P0-2 只记录不动作不受影响）

注：写操作全部走 tmp BOBO_DATA_DIR（isolated_memory_db），真实库只读。
"""

import json
from pathlib import Path

import pytest

from tools import v5_memory as vm

ROOT = Path(__file__).resolve().parent.parent
GUI_FILE = ROOT / "apps" / "desktop" / "dist" / "index.html"


@pytest.fixture
def tmp_memory(isolated_memory_db, monkeypatch):
    """基于项目标准隔离库（per-test 独立 tmp）；审计日志同步隔离。"""
    monkeypatch.setattr(vm, "_AUDIT_LOG", isolated_memory_db.parent / "logs" / "memory_audit.log")
    return isolated_memory_db.parent


def _entry_by_id(data, eid):
    for e in data.get("entries", []):
        if e.get("id") == eid:
            return e
    return None


# ── 1. 替换触发（owner 实弹场景）──────────────────────────────────────

def test_p0_5_replace_trigger(tmp_memory):
    """说"不喜欢冰美式了，喜欢 dirty" → 旧条归档 + score 归零 + 新条写入。"""
    old = vm.add_entry("用户喜欢喝冰美式", entry_type="USER_PREF")
    assert old is not None, "预置旧条失败"
    old_id = old["id"]

    new = vm.add_entry("咖啡偏好从冰美式改为 dirty，不再喜欢冰美式", entry_type="USER_PREF")
    assert new is not None
    assert new["id"] != old_id

    data = vm.get_all()
    old_entry = _entry_by_id(data, old_id)
    new_entry = _entry_by_id(data, new["id"])

    # 旧条：archived + signal_score 归零 + 可回溯指针
    assert old_entry["archived"] is True, "旧条应归档"
    assert old_entry["signal_score"] == 0, "旧条信号分应归零"
    assert old_entry["replaced_by"] == new["id"], "旧条应记录 replaced_by"
    # 新条：活条 + 满分
    assert new_entry["archived"] is False
    assert new_entry["signal_score"] == 100

    # 审计 REPLACE 留痕（from_id→to_id）
    log = tmp_memory / "logs" / "memory_audit.log"
    assert log.exists(), "审计日志应落盘"
    lines = log.read_text(encoding="utf-8").splitlines()
    replace_lines = [ln for ln in lines if "REPLACE" in ln and str(old_id) in ln]
    assert len(replace_lines) >= 1, f"应有 REPLACE 审计: {lines}"
    assert f"to_id={new['id']}" in replace_lines[-1], "REPLACE 应记 to_id"


def test_p0_5_replace_owner_scenario(tmp_memory):
    """owner 原话场景（票背景）：旧条消失于活视图 + 新条在列。

    注：isolated_memory_db 预置 2 条固定记忆（skill 流程/隔离条目二），
    断言按内容过滤，不依赖预置条数。
    """
    vm.add_entry("用户喜欢喝冰美式", entry_type="USER_PREF")
    vm.add_entry("咖啡偏好从冰美式改为 dirty", entry_type="USER_PREF")

    data = vm.get_all()
    active = [e for e in data["entries"] if not e.get("archived", False)]
    archived = [e for e in data["entries"] if e.get("archived", False)]
    # 替换语义：冰美式旧条归档，dirty 新条存活，不并存
    dirty_active = [e for e in active if "dirty" in e["text"]]
    bingmei_archived = [e for e in archived if "冰美式" in e["text"]]
    assert len(dirty_active) == 1, "dirty 新条应存活"
    assert len(bingmei_archived) == 1, "冰美式旧条应归档"

    # list_memories（面板数据源）过滤 archived → 旧条不在面板 → 前端 diff 红删
    panel = vm.list_memories()
    panel_ids = [en["id"] for g in panel["groups"].values() for en in g["entries"]]
    assert bingmei_archived[0]["id"] not in panel_ids, "归档旧条不应出现在面板"
    assert dirty_active[0]["id"] in panel_ids
    assert panel["stats"]["total_entries"] == len(panel_ids), "stats 应为活记忆数"


# ── 2. 不触发（防误替换）──────────────────────────────────────────────

def test_p0_5_no_trigger_plain_add(tmp_memory):
    """普通新增（无反转关键词）→ 旧条不动。"""
    old = vm.add_entry("用户喜欢喝冰美式", entry_type="USER_PREF")
    new = vm.add_entry("用户还喜欢喝咖啡", entry_type="USER_PREF")

    data = vm.get_all()
    assert _entry_by_id(data, old["id"])["archived"] is False, "旧条不得归档"
    assert _entry_by_id(data, new["id"])["archived"] is False, "新条正常入库"


def test_p0_5_no_trigger_same_topic_no_reverse(tmp_memory):
    """同主题但不反转（"我也喜欢喝冰美式"）→ 不替换（票验收：测试覆盖）。"""
    old = vm.add_entry("用户喜欢喝冰美式", entry_type="USER_PREF")
    vm.add_entry("我也喜欢喝冰美式", entry_type="USER_PREF")

    data = vm.get_all()
    assert _entry_by_id(data, old["id"])["archived"] is False, "同主题不反转不得归档"


def test_p0_5_no_trigger_different_topic(tmp_memory):
    """反转关键词但不同主题（"改为" + 无共享显著 token）→ 不替换。"""
    old = vm.add_entry("用户喜欢喝冰美式", entry_type="USER_PREF")
    vm.add_entry("汇报风格改为分条人话摘要", entry_type="RULES")

    data = vm.get_all()
    assert _entry_by_id(data, old["id"])["archived"] is False, "不同主题不得误替换"


# ── 3. 确定性（零 LLM 判据）───────────────────────────────────────────

def test_p0_5_deterministic(tmp_memory):
    """同一输入两次跑，库状态一致（判据为确定性字符串规则，无 LLM 随机）。

    第二轮相同文本走 add_entry 的 dedupe（相同内容直接返回既有条，不重复
    写、不级联替换）→ 最终态与第一轮一致：1 条 dirty 活条 + 1 条冰美式
    归档。预置 2 条不含"冰美式/dirty"，按内容过滤即可。
    """
    for _ in range(2):
        vm.add_entry("用户喜欢喝冰美式", entry_type="USER_PREF")
        vm.add_entry("咖啡偏好从冰美式改为 dirty", entry_type="USER_PREF")

    data = vm.get_all()
    dirty_active = [e for e in data["entries"]
                    if not e.get("archived", False) and "dirty" in e["text"]]
    bingmei_archived = [e for e in data["entries"]
                        if e.get("archived", False) and "冰美式" in e["text"]]
    assert len(dirty_active) == 1, f"应只剩 1 条 dirty 活条，实得 {len(dirty_active)}"
    assert len(bingmei_archived) == 1, f"应有 1 条冰美式归档（幂等），实得 {len(bingmei_archived)}"


# ── 4. memory.changed 事件（event_bus 可观测）─────────────────────────

def test_p0_5_event_emitted(tmp_memory, monkeypatch):
    """add / replace / delete 后 event_bus 收到 memory.changed（失败静默不阻塞）。"""
    events = []

    class FakeBus:
        def write(self, event_type, data):
            events.append((event_type, dict(data)))

    import core.event_bus as eb_module
    monkeypatch.setattr(eb_module, "event_bus", FakeBus())

    e1 = vm.add_entry("用户喜欢喝冰美式", entry_type="USER_PREF")
    e2 = vm.add_entry("咖啡偏好从冰美式改为 dirty", entry_type="USER_PREF")

    types = [t for t, _ in events]
    assert "memory.changed" in types
    add_evts = [d for t, d in events if t == "memory.changed" and d["action"] == "add"]
    rep_evts = [d for t, d in events if t == "memory.changed" and d["action"] == "replace"]
    assert any(d["entry_id"] == e1["id"] for d in add_evts), "add 事件应带 entry_id"
    assert any(d["entry_id"] == e2["id"] and d.get("from_id") == e1["id"] for d in rep_evts), \
        "replace 事件应带 from_id→to_id"

    # delete 事件
    vm.delete_memory(e2["id"], reason="user_request")
    del_evts = [d for t, d in events if t == "memory.changed" and d["action"] == "delete"]
    assert any(d["entry_id"] == e2["id"] for d in del_evts), "delete 事件应发出"


def test_p0_5_event_failure_silent(tmp_memory, monkeypatch):
    """事件发射失败必须静默（记忆写入是主路径，事件是旁路）。"""
    import core.event_bus as eb_module

    class BoomBus:
        def write(self, *a, **k):
            raise RuntimeError("bus down")

    monkeypatch.setattr(eb_module, "event_bus", BoomBus())
    e = vm.add_entry("用户喜欢喝冰美式", entry_type="USER_PREF")
    assert e is not None, "事件失败不得阻塞记忆写入"


# ── 5. 前端静态断言 ───────────────────────────────────────────────────

def test_p0_5_frontend_handler_present():
    """dist/index.html 应含 on('memory.changed') handler + 面板打开重载逻辑。"""
    html = GUI_FILE.read_text(encoding="utf-8")
    assert "on('memory.changed'" in html, "缺少 memory.changed handler 注册"
    assert "loadMemoryPanel()" in html, "缺少面板重载调用"
    assert "memory-view" in html and "style.display !== 'none'" in html, \
        "缺少面板打开判断"


# ── 6. 零动作回归（P0-2 只记录不动作）─────────────────────────────────

def test_p0_5_no_signal_side_effect(tmp_memory):
    """替换路径不触碰 signal_log.jsonl（P0-2 信号判定路径不受影响）。"""
    sig_log = tmp_memory / "logs" / "signal_log.jsonl"
    before = sig_log.read_text(encoding="utf-8") if sig_log.exists() else ""

    vm.add_entry("用户喜欢喝冰美式", entry_type="USER_PREF")
    vm.add_entry("咖啡偏好从冰美式改为 dirty", entry_type="USER_PREF")

    after = sig_log.read_text(encoding="utf-8") if sig_log.exists() else ""
    assert after == before, "替换路径不应写 signal_log.jsonl"
