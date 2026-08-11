"""TICKET-O3 · O3-3 测试：受保护路径快照（guardsnap，O3-1 施工验收）。

票 O3-1（设计稿 v0.3.1 路线图）：
- 决策时刻快照：office 角色会话中，写类工具通过决策链后对受保护路径做
  md5 快照 → data/guardsnap_<sid>.json（sid 维度滚动保留 7 天）；
- 收工闸比对：回合收工比对当前 md5，不一致 → office.snap 审计 + 告警
  （抓漏不执法：不阻断收工）；
- 无角色（普通模式）：整段跳过，零开销零行为变化（对照组铁律）。

覆盖（每条带无角色对照组）：
  1. 写后快照生成（guardsnap 文件 + files 映射）
  2. 收工比对一致 → 零告警零差异
  3. 篡改后 → 差异列表 + office.snap 审计
  4. 7 天滚动清理（过期 guardsnap 被删除）
  5. 无角色对照组：_confirm 不触发快照（零开销零行为变化）
"""

import json
import os
import sys
import time
import uuid

import pytest

sys.path.insert(0, ".")

from core.engine import Engine
from core.tool_executor import execute_tool
from tests.mock_llm import MockLLMCaller, text_response


def make_engine(role=None):
    """构造 test_mode=False 的引擎（pytest 下 __init__ 强制 test_mode=True，
    需手动置 False 才能走到决策链/快照钩子）；role 显式注入。"""
    caller = MockLLMCaller([text_response("ok")])
    eng = Engine(caller, execute_tool, test_mode=False)
    eng.test_mode = False
    eng.office_role = role
    eng.sid = f"test-guardsnap-{uuid.uuid4().hex[:8]}"
    return eng


def _mk_protected(tmp_path):
    """tmp_path 下造一个受保护文件，返回 (目录, 文件路径)。"""
    d = tmp_path / "prot"
    d.mkdir()
    f = d / "engine.py"
    f.write_text("v1-content")
    return d, f


def _patch_globs(monkeypatch, d):
    """让 load_protected_paths 只返回 tmp 保护目录（隔离真实清单）。"""
    monkeypatch.setattr(
        "core.engine.load_protected_paths",
        lambda: [str(d / "**")],
    )


# ── 1. 写后快照生成 ──

class TestSnapshotGeneration:
    def test_snapshot_file_created_with_md5(self, monkeypatch, tmp_path):
        """写类工具通过决策链后：guardsnap_<sid>.json 生成，含 files→md5 映射"""
        d, f = _mk_protected(tmp_path)
        _patch_globs(monkeypatch, d)
        eng = make_engine("staff")

        snap = eng._snapshot_protected_paths()

        assert snap is not None
        path = eng._guardsnap_path()
        assert os.path.exists(path)
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        assert data["sid"] == eng.sid
        assert str(f) in data["files"]
        assert data["files"][str(f)] == __import__("hashlib").md5(
            b"v1-content").hexdigest()

    def test_confirm_hook_triggers_snapshot(self, monkeypatch, tmp_path):
        """_confirm allow 路径：office 角色 + 写工具 → 快照钩子触发"""
        eng = make_engine("staff")
        called = []
        eng._office_decide = lambda *a, **k: ("allow", "")   # 简化执法
        eng._snapshot_protected_paths = lambda: called.append(1)
        eng._all_confirmed = True

        assert eng._confirm("edit_file", {}, "test") is True
        assert called == [1]

    def test_no_role_confirm_skips_snapshot(self, monkeypatch, tmp_path):
        """无角色对照组：office_role=None → _confirm 不触发快照（零开销）"""
        eng = make_engine(None)
        called = []
        eng._snapshot_protected_paths = lambda: called.append(1)
        eng._all_confirmed = True

        assert eng._confirm("edit_file", {}, "test") is True
        assert called == []

    def test_read_tool_does_not_snapshot(self, monkeypatch, tmp_path):
        """非写工具（读类）→ 不触发快照"""
        eng = make_engine("staff")
        called = []
        eng._office_decide = lambda *a, **k: ("allow", "")
        eng._snapshot_protected_paths = lambda: called.append(1)
        eng._all_confirmed = True

        assert eng._confirm("read_local_file", {}, "test") is True
        assert called == []


# ── 2/3. 收工比对：一致零告警 / 篡改告警 ──

class TestSnapshotVerify:
    def test_verify_consistent_zero_diff(self, monkeypatch, tmp_path):
        """快照后无改动 → 收工比对零差异零告警"""
        d, f = _mk_protected(tmp_path)
        _patch_globs(monkeypatch, d)
        eng = make_engine("staff")
        eng._snapshot_protected_paths()

        diffs = eng._verify_snapshot()
        assert diffs == []

    def test_verify_detects_tamper_and_audits(self, monkeypatch, tmp_path):
        """快照后篡改 → 差异列表 + office.snap 审计落库"""
        d, f = _mk_protected(tmp_path)
        _patch_globs(monkeypatch, d)
        eng = make_engine("staff")
        eng._snapshot_protected_paths()

        f.write_text("v2-tampered")   # 模拟漏网改写

        audits = []
        eng._write_office_audit = lambda et, dt: audits.append((et, dt))
        diffs = eng._verify_snapshot()

        assert len(diffs) == 1
        assert diffs[0]["path"] == str(f)
        assert diffs[0]["before"] != diffs[0]["after"]
        assert audits and audits[0][0] == "snap"
        assert str(f) in audits[0][1]

    def test_verify_no_snapshot_returns_empty(self, monkeypatch, tmp_path):
        """无快照文件 → 比对空（静默，不告警不审计）"""
        eng = make_engine("staff")
        assert eng._verify_snapshot() == []


# ── 4. 7 天滚动 ──

class TestSnapshotRetention:
    def test_prune_old_guardsnap(self, monkeypatch, tmp_path):
        """超过 7 天的 guardsnap_*.json 被清理（sid 维度滚动保留）"""
        eng = make_engine("staff")
        old = eng._guardsnap_path().replace(eng.sid, "old-session-aaaa")
        with open(old, "w", encoding="utf-8") as fh:
            json.dump({"sid": "old-session-aaaa", "files": {}}, fh)
        old_time = time.time() - 8 * 86400
        os.utime(old, (old_time, old_time))

        eng._prune_guardsnap()

        assert not os.path.exists(old)

    def test_prune_keeps_fresh_guardsnap(self, monkeypatch, tmp_path):
        """7 天内的 guardsnap 保留"""
        eng = make_engine("staff")
        fresh = eng._guardsnap_path().replace(eng.sid, "fresh-session-bbbb")
        with open(fresh, "w", encoding="utf-8") as fh:
            json.dump({"sid": "fresh-session-bbbb", "files": {}}, fh)

        eng._prune_guardsnap()

        assert os.path.exists(fresh)
        os.remove(fresh)


# ── 5. 收工闸告警文本（不阻断收工） ──

class TestSnapshotGate:
    def test_gate_appends_warning_not_block(self, monkeypatch, tmp_path):
        """收工闸：不一致 → 告警文本追加到 pending_content，不 deny 不阻断"""
        d, f = _mk_protected(tmp_path)
        _patch_globs(monkeypatch, d)
        eng = make_engine("staff")
        eng._snapshot_protected_paths()
        f.write_text("v3-tampered")

        eng._pending_content = "正常收工汇报"
        # 模拟收工闸代码路径（与 engine 内嵌逻辑同条件）
        if eng.office_role is not None and eng._pending_content:
            _snap_diffs = eng._verify_snapshot()
            if _snap_diffs:
                eng._pending_content += "\n\n⚠️ OFFICE MODE 快照告警：受保护路径在回合内被改写"

        assert "快照告警" in eng._pending_content
        assert "正常收工汇报" in eng._pending_content

    def test_gate_no_diff_no_warning(self, monkeypatch, tmp_path):
        """收工闸：一致 → 不追加告警"""
        d, f = _mk_protected(tmp_path)
        _patch_globs(monkeypatch, d)
        eng = make_engine("staff")
        eng._snapshot_protected_paths()

        eng._pending_content = "正常收工汇报"
        _snap_diffs = eng._verify_snapshot()
        if _snap_diffs:
            eng._pending_content += "\n\n⚠️ OFFICE MODE 快照告警"

        assert "快照告警" not in eng._pending_content
