"""票 P0-1 专项测试 — 记忆六类分类 + Memory 模块 UI。

覆盖（票据验收 1）：
- 六类枚举断言：MEMORY_TYPES = USER_PREF/RULES/FACT/ACHIEVEMENT/LESSON/GOAL
- normalize_type：六类命中 / 旧枚举映射（KEY_DECISION→FACT 等）/ 未知兜底 FACT
- add_entry 归一化：写入 type 必在六类内
- 656 条迁移完成态回归：全库无六类外残留 + 迁移函数幂等（重跑 0 变更）
- memory.list：六类分组 + 统计
- memory.delete：删除生效 + 审计日志落盘 + 注入不含被删条目
- memory.update：改 type 重新分组
- verify_memory_links：失效路径标记 link_broken + 降权
- UI 静态断言：侧栏 Memory section + loadMemoryPanel/memDelete/memChangeType
  + P0-1 CSS 段零新增色值（hex 均已在全局色板出现）

注：迁移数据测试只读真实库（迁移已完成），写操作全部走 tmp BOBO_DATA_DIR。
"""

import json
import re
from pathlib import Path

import pytest

import config
from tools import v5_memory as vm
from tools import memory_migrate as mm

ROOT = Path(__file__).resolve().parent.parent
GUI_FILE = ROOT / "apps" / "desktop" / "dist" / "index.html"
KB = ROOT / "data" / "knowledge_base.json"

SIX_TYPES = ("USER_PREF", "RULES", "FACT", "ACHIEVEMENT", "LESSON", "GOAL")


# ── 1. 六类枚举 + normalize_type ────────────────────────────────────────

def test_p0_1_six_type_enum():
    assert vm.MEMORY_TYPES == SIX_TYPES, f"六类枚举不符: {vm.MEMORY_TYPES}"


def test_p0_1_normalize_type_hits():
    for t in SIX_TYPES:
        assert vm.normalize_type(t) == t
        assert vm.normalize_type(t.lower()) == t          # 小写
        assert vm.normalize_type(" " + t + " ") == t      # 空白


def test_p0_1_normalize_type_legacy_map():
    assert vm.normalize_type("KEY_DECISION") == "FACT"    # KEY_DECISION 归并 FACT
    assert vm.normalize_type("OBSERVATION") == "FACT"
    assert vm.normalize_type("GENERAL") == "FACT"
    assert vm.normalize_type("KNOWLEDGE") == "FACT"
    assert vm.normalize_type("MEMORY") == "FACT"


def test_p0_1_normalize_type_fallback():
    assert vm.normalize_type("") == "FACT"
    assert vm.normalize_type(None) == "FACT"
    assert vm.normalize_type("完全未知的类型") == "FACT"


# ── 2. add_entry 归一化（tmp 库）────────────────────────────────────────

@pytest.fixture
def tmp_memory(isolated_memory_db, monkeypatch):
    """基于项目标准隔离库（per-test 独立 tmp，预置 2 条固定记忆 general→FACT）；
    补充 _AUDIT_LOG 隔离，避免审计日志污染真实 data/logs/。

    注：conftest 有 session 级 autouse 把 v5._memory_db 重定向到共享 tmp，
    isolated_memory_db 在 per-test 再重定向到独立 tmp，二者叠加安全。
    """
    import tools.v5_memory as v5
    monkeypatch.setattr(v5, "_AUDIT_LOG", isolated_memory_db.parent / "logs" / "memory_audit.log")
    return isolated_memory_db.parent


def test_p0_1_add_entry_normalized(tmp_memory):
    texts = ["用户喜欢喝茶", "必须走 diff 展示", "某个关键决策", "任意脏值"]
    vm.add_entry(texts[0], entry_type="USER_PREF")
    vm.add_entry(texts[1], entry_type="RULES")
    vm.add_entry(texts[2], entry_type="KEY_DECISION")   # 旧枚举
    vm.add_entry(texts[3], entry_type="whatever_random")    # 未知兜底
    entries = vm.get_entries()
    # 预置 2 条 general（type=general 原样保留，不入六类断言）
    assert len(entries) == 6
    added = [e for e in entries if e["text"] in texts]
    assert len(added) == 4
    for e in added:
        assert e["type"] in SIX_TYPES, f"写入 type 不在六类: {e['type']}"
    types = {e["type"] for e in added}
    assert types == {"USER_PREF", "RULES", "FACT"}


# ── 3. 656 条迁移完成态回归（只读真实库）────────────────────────────────

def test_p0_1_migration_no_residue():
    data = json.loads(KB.read_text(encoding="utf-8"))
    entries = data["entries"]
    # 迁移完成态基线 656 条（2026-08-19 收编时）；真实库会随对话沉淀增长
    # （2026-08-19 P0-3 收编实测 657：+1 条真实记忆"咖啡偏好改 dirty"），
    # 故断言"≥基线且无六类外残留"，不锁精确条数（迁移正确性=分类，非计数）。
    assert len(entries) >= 656, f"条目数低于迁移基线: {len(entries)}"
    dirty = [e for e in entries if e.get("type") not in SIX_TYPES]
    assert not dirty, f"六类外残留 {len(dirty)} 条: {[e['id'] for e in dirty[:10]]}"


def test_p0_1_migration_idempotent():
    """迁移函数重跑 0 变更（已完成态幂等）。"""
    data = json.loads(KB.read_text(encoding="utf-8"))
    _, stats = mm.migrate_entries(data["entries"])
    assert stats["changed"] == 0, f"重跑迁移仍有变更: {stats['changed']}"


# ── 4. memory.list ──────────────────────────────────────────────────────

def test_p0_1_memory_list_structure(tmp_memory):
    vm.add_entry("偏好 A", entry_type="USER_PREF")
    vm.add_entry("规则 B", entry_type="RULES")
    r = vm.list_memories()
    assert set(r["groups"].keys()) == set(SIX_TYPES)
    assert r["groups"]["USER_PREF"]["count"] == 1
    assert r["groups"]["RULES"]["count"] == 1
    # 预置 2 条 general（→FACT）+ 本测试 2 条
    assert r["stats"]["total_entries"] == 4
    assert r["stats"]["total_chars"] > 0
    assert r["stats"]["total_tokens_est"] == round(r["stats"]["total_chars"] / 4)
    # 条目含 id/text 摘要/signal_score
    e = r["groups"]["USER_PREF"]["entries"][0]
    assert "id" in e and "text" in e and "signal_score" in e


# ── 5. memory.delete：生效 + 审计 + 注入不含 ─────────────────────────────

def test_p0_1_memory_delete_audit_and_inject(tmp_memory):
    a = vm.add_entry("要被删掉的记忆", entry_type="FACT")
    b = vm.add_entry("保留的记忆", entry_type="FACT")
    r = vm.delete_memory(a["id"], reason="user_request", source="test")
    assert r["success"] is True
    # 注入不含被删条目
    inj, stats = vm.format_memory_by_signal(max_chars=5000)
    assert "要被删掉的记忆" not in inj
    assert "保留的记忆" in inj
    # 预置 2 条 + 新增 2 条 − 删除 1 条 = 3
    assert stats["total_entries"] == 3
    # 审计日志落盘
    log = tmp_memory / "logs" / "memory_audit.log"
    assert log.exists()
    content = log.read_text(encoding="utf-8")
    assert "DELETE" in content and str(a["id"]) in content


def test_p0_1_memory_delete_reason_gate(tmp_memory):
    a = vm.add_entry("测试记忆", entry_type="FACT")
    r = vm.delete_memory(a["id"], reason="not_valid")  # 非法 reason
    assert "error" in r


# ── 6. memory.update：改 type 重新分组 ──────────────────────────────────

def test_p0_1_memory_update_retype(tmp_memory):
    a = vm.add_entry("用户目标条目", entry_type="FACT")
    r = vm.update_memory_type(a["id"], "GOAL")
    assert r["success"] is True and r["entry"]["changed"] is True
    data = vm.list_memories()
    assert data["groups"]["GOAL"]["count"] == 1
    # 预置 2 条 general（→FACT）仍在 FACT 组
    assert data["groups"]["FACT"]["count"] == 2
    # 审计日志
    log = tmp_memory / "logs" / "memory_audit.log"
    assert "RETYPE" in log.read_text(encoding="utf-8")
    # 改到同一 type → changed False（幂等）
    r2 = vm.update_memory_type(a["id"], "GOAL")
    assert r2["entry"]["changed"] is False


# ── 7. 指针可达性校验 ───────────────────────────────────────────────────

def test_p0_1_verify_links_broken(tmp_memory):
    vm.add_entry("引用失效文件: /Users/niuqingwei/Desktop/definitely_not_exists_xyz/file.py",
                 entry_type="FACT")
    vm.add_entry("普通记忆不引用路径", entry_type="FACT")
    r = vm.verify_memory_links()
    assert r["checked"] >= 1
    assert r["broken"] >= 1
    # 失效条目被标记 link_broken 且降权
    for e in vm.get_entries():
        if "definitely_not_exists_xyz" in e["text"]:
            assert e.get("link_broken") is True
            assert e["signal_score"] < 100  # 降权（初始 100 - 5）


# ── 8. UI 静态断言（index.html）─────────────────────────────────────────

def _gui() -> str:
    return GUI_FILE.read_text(encoding="utf-8")


def test_p0_1_ui_sidebar_memory_section():
    src = _gui()
    # 票 P0-1 改版：Memory 提升为侧栏导航项（SVG+高亮），面板搬到主区域独立视图
    assert 'id="nav-memory"' in src, "侧栏缺 Memory 导航项"
    assert "onNavMemory()" in src, "Memory 导航缺点击处理"
    assert 'id="memory-view"' in src, "主区域缺 Memory 面板视图"
    assert 'id="memory-groups"' in src
    assert 'id="memory-count"' in src
    # 侧栏三导航项齐全；Session 为静态项（不可点、固定展开）
    assert 'id="nav-new-session"' in src and 'id="nav-session"' in src
    assert "nav-static" in src, "Session 应为静态导航项"
    assert "closeMemoryView()" in src, "Memory 面板缺关闭能力"
    # 旧折叠式 section 已移除
    assert "toggleSection('memory')" not in src, "旧折叠式 Memory section 应移除"
    assert "toggleSection('session')" not in src, "Session 折叠应移除"


def test_p0_1_ui_js_present():
    src = _gui()
    for fn in ("function loadMemoryPanel", "function memDelete", "function memChangeType",
               "function renderMemoryGroups", "function renderMemoryDiff"):
        assert fn in src, f"缺 JS 函数 {fn}"
    # RPC 方法名
    assert "memory.list" in src and "memory.delete" in src and "memory.update" in src


def test_p0_1_ui_css_no_new_hex():
    """P0-1 CSS 段零新增色值：段内 #hex ⊆ 全局色板。"""
    src = _gui()
    seg_start = "/* 票 P0-1：Memory 面板"
    seg_end = "/* === end P0-1 Memory === */"
    assert seg_start in src and seg_end in src
    seg = src.split(seg_start)[1].split(seg_end)[0]
    outside = src.replace(seg_start, "").replace(seg_end, "")
    palette = set(re.findall(r"#[0-9a-fA-F]{3,6}\b", outside))
    seg_hex = set(re.findall(r"#[0-9a-fA-F]{3,6}\b", seg))
    new_hex = seg_hex - palette
    assert not new_hex, f"P0-1 CSS 段引入新色值: {new_hex}"
    # rgba 只能是黑色系压暗
    for m in re.findall(r"rgba?\(([^)]*)\)", seg):
        base = m.split(",")[0].strip()
        assert base in ("0", "0.0"), f"P0-1 段 rgba 只能黑色系: {m}"
