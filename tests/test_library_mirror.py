"""tools/library_mirror 单向镜像测试（票 R2 / R2b 三道铁闸）。

闸 3 测试隔离铁律（TICKET-R2b §二）：
  - 凡调用 sync_library_to_obsidian() 必须显式传 vault_dir=<tmp>；
  - 不传 vault_dir 的调用一律 monkeypatch.delenv("OBSIDIAN_VAULT") 且断言 skipped=True。
  血案重放 test_r2b_massacre_scenario_blocked 完整复现 08-09 灭库场景。

覆盖：全量同步一致 / 增量新增 / 删除传播 / 闸1 vault 解析禁区 /
      闸2 批量删除熔断 / 安全闸（vault 外 symlink 拒绝）/ 未配置 vault 静默跳过。
"""

import os
from pathlib import Path

import pytest

from tools.library_mirror import (
    sync_library_to_obsidian,
    _is_within,
    _MIRROR_HEADER,
    _REPO_ROOT,
)


def make_lib(root: Path, files: dict[str, str]) -> Path:
    """在 root 下按 {相对路径: 内容} 建主库文件，返回主库目录。"""
    lib = root / "main_lib"
    for rel, content in files.items():
        p = lib / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return lib


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


class TestFullSync:
    def test_full_mirror_including_subdirs_and_history(self, tmp_path):
        lib = make_lib(tmp_path, {
            "index.md": "<!-- AUTO-GENERATED -->\n# index\n",
            "agent开发/主题A.md": "# 主题A\n内容\n",
            ".history/agent开发/主题A/v1.md": "# v1\n",
            "工作方式/规则.md": "# 规则\n",
        })
        vault = tmp_path / "vault"
        vault.mkdir()

        r = sync_library_to_obsidian(library_dir=lib, vault_dir=vault, sid="t1")

        assert r["ok"] is True
        assert r["skipped"] is False
        assert r["blocked"] is None
        assert len(r["synced"]) == 4
        assert r["removed"] == []
        # 镜像内容 = 头 + 主库内容（index.md 除外）
        assert read(vault / "library" / "index.md") == "<!-- AUTO-GENERATED -->\n# index\n"
        assert read(vault / "library" / "agent开发" / "主题A.md") == _MIRROR_HEADER + "# 主题A\n内容\n"
        assert read(vault / "library" / ".history" / "agent开发" / "主题A" / "v1.md") == _MIRROR_HEADER + "# v1\n"

    def test_idempotent_second_run_no_rewrites(self, tmp_path):
        lib = make_lib(tmp_path, {"a.md": "aaa"})
        vault = tmp_path / "vault"
        vault.mkdir()

        r1 = sync_library_to_obsidian(library_dir=lib, vault_dir=vault)
        assert len(r1["synced"]) == 1
        r2 = sync_library_to_obsidian(library_dir=lib, vault_dir=vault)
        assert r2["synced"] == []  # 幂等：内容未变不重写

    def test_does_not_touch_other_vault_dirs(self, tmp_path):
        lib = make_lib(tmp_path, {"a.md": "aaa"})
        vault = tmp_path / "vault"
        (vault / "00_Inbox").mkdir(parents=True)
        (vault / "00_Inbox" / "user-note.md").write_text("用户笔记", encoding="utf-8")

        sync_library_to_obsidian(library_dir=lib, vault_dir=vault)

        assert (vault / "00_Inbox" / "user-note.md").exists()  # vault 其他目录零触碰
        assert read(vault / "00_Inbox" / "user-note.md") == "用户笔记"


class TestIncremental:
    def test_new_file_appears_on_next_sync(self, tmp_path):
        lib = make_lib(tmp_path, {"a.md": "aaa"})
        vault = tmp_path / "vault"
        vault.mkdir()
        sync_library_to_obsidian(library_dir=lib, vault_dir=vault)

        (lib / "b.md").write_text("bbb", encoding="utf-8")
        r = sync_library_to_obsidian(library_dir=lib, vault_dir=vault)

        assert "b.md" in r["synced"]
        assert read(vault / "library" / "b.md") == _MIRROR_HEADER + "bbb"

    def test_modified_file_updated(self, tmp_path):
        lib = make_lib(tmp_path, {"a.md": "v1"})
        vault = tmp_path / "vault"
        vault.mkdir()
        sync_library_to_obsidian(library_dir=lib, vault_dir=vault)

        (lib / "a.md").write_text("v2", encoding="utf-8")
        r = sync_library_to_obsidian(library_dir=lib, vault_dir=vault)

        assert "a.md" in r["synced"]
        assert read(vault / "library" / "a.md") == _MIRROR_HEADER + "v2"


class TestDeletion:
    def _make_large_lib(self, tmp_path, n=10):
        """主库 n 个文件（镜像侧同规模，删 1 个 = 10% < 30%，不触发比例熔断）。"""
        return make_lib(tmp_path, {f"topic{i}.md": f"# T{i}\n" for i in range(n)})

    def test_orphan_removed_from_mirror(self, tmp_path):
        lib = self._make_large_lib(tmp_path)
        vault = tmp_path / "vault"
        vault.mkdir()
        sync_library_to_obsidian(library_dir=lib, vault_dir=vault)

        # 镜像侧手动加一个多余文件（模拟旧化石/手写残留）→ 1 个 ≤5 且 ≤30%，正常删
        (vault / "library" / "orphan.md").write_text("残留", encoding="utf-8")
        r = sync_library_to_obsidian(library_dir=lib, vault_dir=vault)

        assert r["blocked"] is None
        assert r["removed"] == ["orphan.md"]
        assert not (vault / "library" / "orphan.md").exists()

    def test_deleted_source_propagates(self, tmp_path):
        lib = self._make_large_lib(tmp_path)
        vault = tmp_path / "vault"
        vault.mkdir()
        sync_library_to_obsidian(library_dir=lib, vault_dir=vault)

        (lib / "topic0.md").unlink()
        r = sync_library_to_obsidian(library_dir=lib, vault_dir=vault)

        assert r["blocked"] is None
        assert r["removed"] == ["topic0.md"]
        assert not (vault / "library" / "topic0.md").exists()


# ── 闸 1：vault 解析禁区 ──────────────────────────────

class TestGate1VaultZone:
    def test_gate1_vault_is_cwd(self, tmp_path, monkeypatch):
        """血案根因路径：vault 解析后 == cwd → 拦截，零写入零删除。"""
        lib = make_lib(tmp_path, {"a.md": "aaa"})
        monkeypatch.chdir(tmp_path)
        r = sync_library_to_obsidian(library_dir=lib, vault_dir=str(tmp_path))
        assert r["blocked"] == "vault_is_cwd"
        assert r["skipped"] is True
        assert r["synced"] == [] and r["removed"] == []

    def test_gate1_vault_is_repo_root(self, tmp_path, monkeypatch):
        lib = make_lib(tmp_path, {"a.md": "aaa"})
        # pytest cwd=项目根 → vault=项目根 会先命中 vault_is_cwd；chdir 隔离后验证 repo_root
        monkeypatch.chdir(tmp_path)
        r = sync_library_to_obsidian(library_dir=lib, vault_dir=str(_REPO_ROOT))
        assert r["blocked"] == "vault_is_repo_root"
        assert r["synced"] == [] and r["removed"] == []

    def test_gate1_vault_is_library_dir(self, tmp_path):
        lib = make_lib(tmp_path, {"a.md": "aaa"})
        r = sync_library_to_obsidian(library_dir=lib, vault_dir=str(lib))
        assert r["blocked"] == "vault_is_library_dir"
        assert r["synced"] == [] and r["removed"] == []

    def test_gate1_vault_is_library_ancestor(self, tmp_path):
        """vault = 主库的祖先目录（主库是 vault 的子目录）→ 拦截。"""
        lib = make_lib(tmp_path, {"a.md": "aaa"})
        r = sync_library_to_obsidian(library_dir=lib, vault_dir=str(tmp_path.parent))
        assert r["blocked"] == "library_inside_vault"
        assert r["synced"] == [] and r["removed"] == []

    def test_gate1_vault_inside_library(self, tmp_path):
        """vault = 主库的子目录 → 拦截。"""
        lib = make_lib(tmp_path, {"a.md": "aaa"})
        vault = lib / "sub_vault"
        vault.mkdir(parents=True)
        r = sync_library_to_obsidian(library_dir=lib, vault_dir=str(vault))
        assert r["blocked"] == "vault_inside_library"
        assert r["synced"] == [] and r["removed"] == []

    def test_gate1_dst_overlaps_library(self, tmp_path):
        """dst_root（vault/library）与主库重叠 → 拦截。"""
        vault = tmp_path / "vault"
        # 主库放在 vault/library 内 → dst_root 与主库重叠
        lib = make_lib(vault, {"a.md": "aaa"})
        r = sync_library_to_obsidian(library_dir=lib, vault_dir=str(vault))
        assert r["blocked"] is not None  # library_inside_vault 或 dst_overlaps_library
        assert r["synced"] == [] and r["removed"] == []


# ── 闸 2：批量删除熔断 ──────────────────────────────

class TestGate2MassDeleteFuse:
    def test_fuse_over_abs_limit(self, tmp_path):
        """待删 8 个 > 5 → 熔断，删除阶段放弃（写入照常）。"""
        lib = make_lib(tmp_path, {"a.md": "aaa"})
        vault = tmp_path / "vault"
        (vault / "library").mkdir(parents=True)
        for i in range(8):
            (vault / "library" / f"orphan{i}.md").write_text("x", encoding="utf-8")

        r = sync_library_to_obsidian(library_dir=lib, vault_dir=vault)

        assert r["blocked"] == "mass_delete_fuse"
        assert r["removed"] == []
        for i in range(8):
            assert (vault / "library" / f"orphan{i}.md").exists()  # 一个没删
        assert (vault / "library" / "a.md").exists()  # 写入阶段照常

    def test_fuse_over_ratio(self, tmp_path):
        """待删 2 个 ≤5 但 = 镜像侧 66% > 30% → 靠比例熔断。"""
        lib = make_lib(tmp_path, {"a.md": "aaa"})
        vault = tmp_path / "vault"
        (vault / "library").mkdir(parents=True)
        (vault / "library" / "a.md").write_text(_MIRROR_HEADER + "aaa", encoding="utf-8")
        (vault / "library" / "orphan1.md").write_text("x", encoding="utf-8")
        (vault / "library" / "orphan2.md").write_text("x", encoding="utf-8")

        r = sync_library_to_obsidian(library_dir=lib, vault_dir=vault)

        assert r["blocked"] == "mass_delete_fuse"
        assert r["removed"] == []
        assert (vault / "library" / "orphan1.md").exists()

    def test_allow_mass_delete_override(self, tmp_path):
        """显式人工 override 放行（仅手动入口语义）。"""
        lib = make_lib(tmp_path, {"a.md": "aaa"})
        vault = tmp_path / "vault"
        (vault / "library").mkdir(parents=True)
        for i in range(8):
            (vault / "library" / f"orphan{i}.md").write_text("x", encoding="utf-8")

        r = sync_library_to_obsidian(library_dir=lib, vault_dir=vault,
                                     allow_mass_delete=True)

        assert r["blocked"] is None
        assert len(r["removed"]) == 8
        assert not (vault / "library" / "orphan0.md").exists()

    def test_small_delete_still_works(self, tmp_path):
        """≤5 且 ≤30% 的常规删除不受熔断影响（R2 删除传播不破）。"""
        # 镜像 10 文件（9 真 + 1 孤儿）→ 删 1 个 = 10% < 30%，不熔断
        lib = make_lib(tmp_path, {f"topic{i}.md": f"# T{i}\n" for i in range(9)})
        vault = tmp_path / "vault"
        (vault / "library").mkdir(parents=True)
        for i in range(9):
            (vault / "library" / f"topic{i}.md").write_text(
                _MIRROR_HEADER + f"# T{i}\n", encoding="utf-8")
        (vault / "library" / "orphan.md").write_text("x", encoding="utf-8")

        r = sync_library_to_obsidian(library_dir=lib, vault_dir=vault)

        assert r["blocked"] is None
        assert r["removed"] == ["orphan.md"]
        assert not (vault / "library" / "orphan.md").exists()


# ── 闸 3：测试隔离 + 血案回归 ──────────────────────────

class TestGate3Isolation:
    def test_never_touches_real_paths(self, tmp_path, monkeypatch):
        """守卫：sync 的写入/删除绝不落在真实 library/、真实 vault、项目根内。

        用 tmp cwd + 危险 vault 指向重放：全部被闸 1 拦截，主库文件零改动。
        """
        lib = make_lib(tmp_path, {"a.md": "aaa", "b.md": "bbb"})
        before = {p: read(p) for p in lib.rglob("*") if p.is_file()}
        monkeypatch.chdir(tmp_path)

        # vault = cwd
        r = sync_library_to_obsidian(library_dir=lib, vault_dir=str(tmp_path))
        assert r["blocked"] == "vault_is_cwd"
        # vault = 主库本身
        r = sync_library_to_obsidian(library_dir=lib, vault_dir=str(lib))
        assert r["blocked"] == "vault_is_library_dir"
        # vault = 主库祖先
        r = sync_library_to_obsidian(library_dir=lib, vault_dir=str(tmp_path.parent))
        assert r["blocked"] == "library_inside_vault"

        after = {p: read(p) for p in lib.rglob("*") if p.is_file()}
        assert before == after  # 主库零改动

    def test_r2b_massacre_scenario_blocked(self, tmp_path, monkeypatch):
        """完整重放 08-09 血案：delenv + tmp 小库 + cwd 隔离 → 主库零删除。

        血案根因（罪证链 §一.1-3）：OBSIDIAN_VAULT 未配置时 Path("")→Path(".")，
        vault 落为 cwd（pytest 的 cwd = 项目根）→ 同步目标 = 主库本体 →
        删除传播 unlink 主库 20+ 篇 + .history/。
        闸 1a（empty_vault）必须在此场景直接跳过，主库一个字节都不许动。
        """
        lib = make_lib(tmp_path, {
            "agent开发/主题A.md": "# A",
            "agent开发/主题B.md": "# B",
            ".history/agent开发/主题A/v1.md": "# v1",
            "MEMORY.md": "# MEMORY\n",
        })
        before = {p: read(p) for p in lib.rglob("*") if p.is_file()}
        assert len(before) == 4

        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        monkeypatch.chdir(elsewhere)          # 模拟 pytest cwd=项目根
        monkeypatch.delenv("OBSIDIAN_VAULT", raising=False)

        r = sync_library_to_obsidian(library_dir=lib)  # 不传 vault_dir（血案路径）

        assert r["skipped"] is True
        assert r["blocked"] == "empty_vault"
        assert r["synced"] == [] and r["removed"] == []
        after = {p: read(p) for p in lib.rglob("*") if p.is_file()}
        assert before == after                # 主库零删除零写入


# ── 既有安全闸（R2）──────────────────────────────

class TestSafetyGate:
    def test_symlink_to_outside_not_followed_on_write(self, tmp_path):
        lib = make_lib(tmp_path, {"evil.md": "主库内容"})
        vault = tmp_path / "vault"
        (vault / "library").mkdir(parents=True)
        outside = tmp_path / "outside"
        outside.mkdir()
        target = outside / "target.md"
        target.write_text("外部文件", encoding="utf-8")
        (vault / "library" / "evil.md").symlink_to(target)

        r = sync_library_to_obsidian(library_dir=lib, vault_dir=vault)

        assert "evil.md" not in r["synced"]
        assert read(target) == "外部文件"  # 外部文件未被污染

    def test_symlink_to_outside_not_deleted(self, tmp_path):
        lib = make_lib(tmp_path, {"a.md": "aaa"})
        vault = tmp_path / "vault"
        (vault / "library").mkdir(parents=True)
        outside = tmp_path / "outside"
        outside.mkdir()
        target = outside / "target.md"
        target.write_text("外部文件", encoding="utf-8")
        (vault / "library" / "evil.md").symlink_to(target)

        r = sync_library_to_obsidian(library_dir=lib, vault_dir=vault)

        assert "evil.md" not in r["removed"]
        assert (vault / "library" / "evil.md").is_symlink()
        assert read(target) == "外部文件"

    def test_is_within_pure(self, tmp_path):
        parent = tmp_path / "lib"
        parent.mkdir()
        inside = parent / "sub" / "f.md"
        outside = tmp_path / "outside.md"
        assert _is_within(inside, parent) is True
        assert _is_within(parent, parent) is True
        assert _is_within(outside, parent) is False
        # 前缀混淆：/tmp/lib2 不应算在 /tmp/lib 内
        sibling = tmp_path / "lib2" / "f.md"
        assert _is_within(sibling, parent) is False


class TestUnconfiguredVault:
    def test_silent_skip_when_env_missing(self, tmp_path, monkeypatch):
        """OBSIDIAN_VAULT 未配置 → skipped=True + blocked=empty_vault（零动作）。"""
        monkeypatch.delenv("OBSIDIAN_VAULT", raising=False)
        lib = make_lib(tmp_path, {"a.md": "aaa"})

        r = sync_library_to_obsidian(library_dir=lib)

        assert r["skipped"] is True
        assert r["blocked"] == "empty_vault"
        assert r["synced"] == []
        assert r["removed"] == []


# ── 挂钩加固（R2b §三）：blocked 降级不阻塞 ──────────────

class TestLivingNotesHook:
    def test_hook_blocked_degrades_without_blocking(self, tmp_path, monkeypatch):
        """living_notes 挂钩：sync 触发 blocked → 降级 notes.error，written=True 不阻塞。

        同时铁证挂钩永远不许传 allow_mass_delete=True（闸 2 熔断自动场景常开）。
        """
        import json
        import tools.library_mirror as lm
        from tools import living_notes as ln

        # 隔离 library 路径（闸 3 铁律：绝不碰真实主库）
        library = tmp_path / "library"
        monkeypatch.setattr(ln, "LIBRARY_DIR", library)
        monkeypatch.setattr(ln, "INDEX_PATH", library / "index.md")

        calls = {"n": 0}
        def fake_llm(messages, use_tools=False, **kw):
            calls["n"] += 1
            if calls["n"] == 1:
                judge = {"topic": "挂钩测试", "domain": "agent开发",
                         "section": "- x", "match": None}
                return {"choices": [{"message": {"content": json.dumps(judge, ensure_ascii=False)}}]}
            return {"choices": [{"message": {"content": (
                "---\ntopic: 挂钩测试\ndomain: agent开发\ncreated: 2026-08-09\n---\n\n"
                "# 挂钩测试\n\n## 概述\nx\n\n## 关键结论\nx\n\n## 决策与原因\nx\n\n"
                "## 待办与未决\nx\n\n## 时间线\n- 09:00 x\n")}}]}

        blocked_payload = {"ok": False, "synced": [], "removed": [],
                           "skipped": True, "blocked": "empty_vault"}
        def fake_sync(**kw):
            assert kw.get("allow_mass_delete") is False  # 挂钩永远不许传 True
            return blocked_payload
        monkeypatch.setattr(lm, "sync_library_to_obsidian", fake_sync)

        result = ln.write_living_notes(["要点"], "消息", "sid-hook", fake_llm,
                                       full_reply="# 挂钩测试\nx")

        assert result["written"] is True  # blocked 不阻塞主流程
        assert calls["n"] == 2             # 成文正常完成
