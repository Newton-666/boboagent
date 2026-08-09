"""tools/library_git 自动提交钩子测试（票 G1）。

测试隔离铁律（TICKET-G1 §三）：凡触发 write_living_notes 的测试，钩子指向 tmp 库，
严禁在真实 library/ 里产生测试提交。living_notes 挂钩传 library_dir=LIBRARY_DIR，
ln_env 类 fixture monkeypatch ln.LIBRARY_DIR 后自动传导到钩子。

覆盖：自动提交（含提交信息 action+topic+sid）/ 无变更不提交 / 无 .git 跳过 /
      git 失败静默降级 / 白名单拒绝非 add-commit 操作 / write_living_notes 集成。
"""

import json
import subprocess
from pathlib import Path

from tools.library_git import auto_commit, _run_git, _ALLOWED_GIT


def git_init(lib: Path):
    """在 lib 下 init 独立仓库（继承全局 user 配置）。"""
    subprocess.run(["git", "-C", str(lib), "init", "-b", "main"],
                   capture_output=True, check=True)


def git_log_count(lib: Path) -> int:
    out = subprocess.run(["git", "-C", str(lib), "rev-list", "--count", "HEAD"],
                         capture_output=True, text=True)
    return int(out.stdout.strip()) if out.returncode == 0 else 0


class TestAutoCommit:
    def test_creates_commit_with_action_topic_sid(self, tmp_path):
        lib = tmp_path / "lib"
        lib.mkdir()
        (lib / "a.md").write_text("aaa", encoding="utf-8")
        git_init(lib)

        r = auto_commit(library_dir=lib, action="write", topic="测试主题", sid="sid-1")

        assert r["committed"] is True
        assert r["skipped"] is False
        assert r["error"] is None
        log = subprocess.run(["git", "-C", str(lib), "log", "--oneline", "-1"],
                             capture_output=True, text=True)
        assert "auto: write 测试主题 (sid=sid-1)" in log.stdout
        assert (lib / "a.md") in {p for p in lib.rglob("*") if p.is_file()}

    def test_no_changes_no_empty_commit(self, tmp_path):
        lib = tmp_path / "lib"
        lib.mkdir()
        (lib / "a.md").write_text("aaa", encoding="utf-8")
        git_init(lib)

        r1 = auto_commit(library_dir=lib, action="write", topic="t", sid="s1")
        assert r1["committed"] is True
        count_after_first = git_log_count(lib)

        r2 = auto_commit(library_dir=lib, action="write", topic="t", sid="s1")

        assert r2["committed"] is False
        assert r2["skipped"] is True
        assert r2["error"] is None
        assert git_log_count(lib) == count_after_first  # 无空提交

    def test_no_git_dir_skips(self, tmp_path):
        lib = tmp_path / "lib"
        lib.mkdir()
        (lib / "a.md").write_text("aaa", encoding="utf-8")

        r = auto_commit(library_dir=lib, action="write", topic="t", sid="s1")

        assert r["committed"] is False
        assert r["skipped"] is True
        assert r["error"] is None

    def test_git_failure_degrades_silently(self, tmp_path, monkeypatch):
        """git 仓库损坏（add 失败）→ 返回 error，不抛异常（living_notes 降级记 notes.error）。"""
        lib = tmp_path / "lib"
        lib.mkdir()
        git_init(lib)
        monkeypatch.setattr("tools.library_git._run_git",
                            lambda lib_dir, args: (128, "fatal: not a git repository"))

        r = auto_commit(library_dir=lib, action="write", topic="t", sid="s1")

        assert r["committed"] is False
        assert r["error"] is not None

    def test_whitelist_blocks_non_add_commit(self, tmp_path):
        """安全红线：push/reset/checkout/clean/rm 一律拒绝执行。"""
        lib = tmp_path / "lib"
        lib.mkdir()
        git_init(lib)

        for op in (["push"], ["reset", "--hard"], ["checkout", "."],
                   ["clean", "-fd"], ["rm", "-rf", "."]):
            rc, out = _run_git(lib, op)
            assert rc == 2
            assert "blocked" in out

        assert _ALLOWED_GIT == {"add", "commit"}


class TestIntegrationWithLivingNotes:
    """write_living_notes 真实走钩子：tmp 库产生自动提交；无变更不重复提交。"""

    def _write_note(self, tmp_path, monkeypatch, sid="sid-g1"):
        from tools import living_notes as ln
        import tools.library_mirror as lm

        # 隔离 library 路径（闸 3 铁律：绝不碰真实主库）
        library = tmp_path / "library"
        library.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(ln, "LIBRARY_DIR", library)
        monkeypatch.setattr(ln, "INDEX_PATH", library / "index.md")
        git_init(library)  # tmp 库带独立 .git

        # 镜像 stub（真实 vault 零触碰）
        monkeypatch.setattr(lm, "sync_library_to_obsidian",
                            lambda **kw: {"ok": True, "synced": [], "removed": [],
                                          "skipped": True, "blocked": None})

        # 第一次调用：judge；第二次：成文（沿用 R2b 测试的假 LLM 协议）
        calls = {"n": 0}
        def fake_llm(messages, use_tools=False, **kw):
            calls["n"] += 1
            if calls["n"] == 1:
                judge = {"topic": "G1集成", "domain": "agent开发",
                         "section": "- x", "match": None}
                return {"choices": [{"message": {"content": json.dumps(judge, ensure_ascii=False)}}]}
            return {"choices": [{"message": {"content": (
                "---\ntopic: G1集成\ndomain: agent开发\ncreated: 2026-08-09\n---\n\n"
                "# G1集成\n\n## 概述\nx\n\n## 关键结论\nx\n\n## 决策与原因\nx\n\n"
                "## 待办与未决\nx\n\n## 时间线\n- 09:00 x\n")}}]}

        return ln, library, fake_llm

    def test_write_creates_auto_commit(self, tmp_path, monkeypatch):
        ln, library, fake_llm = self._write_note(tmp_path, monkeypatch)

        result = ln.write_living_notes(["要点"], "消息", "sid-g1", fake_llm,
                                       full_reply="# G1集成\nx")

        assert result["written"] is True
        log = subprocess.run(["git", "-C", str(library), "log", "--oneline", "-5"],
                             capture_output=True, text=True)
        assert "auto: write G1集成 (sid=sid-g1)" in log.stdout

    def test_no_changes_no_second_commit(self, tmp_path, monkeypatch):
        ln, library, fake_llm = self._write_note(tmp_path, monkeypatch)

        ln.write_living_notes(["要点"], "消息", "sid-g1", fake_llm,
                              full_reply="# G1集成\nx")
        count_after_first = git_log_count(library)

        # 无变更再次触发 → 不产生新提交
        ln.write_living_notes(["要点"], "消息", "sid-g1", fake_llm,
                              full_reply="# G1集成\nx")

        assert git_log_count(library) == count_after_first

    def test_git_failure_emits_notes_error_and_does_not_block(self, tmp_path, monkeypatch):
        """验收 3：git 仓库损坏 → 笔记写入照常（written=True），notes.error 事件落盘。"""
        import tools.library_git as lg
        from tools import living_notes as ln
        import tools.library_mirror as lm
        import core.event_bus as eb

        library = tmp_path / "library"
        library.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(ln, "LIBRARY_DIR", library)
        monkeypatch.setattr(ln, "INDEX_PATH", library / "index.md")
        git_init(library)
        monkeypatch.setattr(lm, "sync_library_to_obsidian",
                            lambda **kw: {"ok": True, "synced": [], "removed": [],
                                          "skipped": True, "blocked": None})
        # git 仓库损坏：add 必败
        monkeypatch.setattr(lg, "_run_git",
                            lambda lib_dir, args: (128, "fatal: not a git repository"))

        fired = []
        class _Bus:
            def write(self, t, d):
                fired.append((t, d))
        monkeypatch.setattr(eb, "event_bus", _Bus())

        calls = {"n": 0}
        def fake_llm(messages, use_tools=False, **kw):
            calls["n"] += 1
            if calls["n"] == 1:
                judge = {"topic": "G1降级", "domain": "agent开发",
                         "section": "- x", "match": None}
                return {"choices": [{"message": {"content": json.dumps(judge, ensure_ascii=False)}}]}
            return {"choices": [{"message": {"content": (
                "---\ntopic: G1降级\ndomain: agent开发\ncreated: 2026-08-09\n---\n\n"
                "# G1降级\n\n## 概述\nx\n\n## 关键结论\nx\n\n## 决策与原因\nx\n\n"
                "## 待办与未决\nx\n\n## 时间线\n- 09:00 x\n")}}]}

        result = ln.write_living_notes(["要点"], "消息", "sid-g1-fail", fake_llm,
                                       full_reply="# G1降级\nx")

        assert result["written"] is True  # 主流程不阻塞
        assert (library / "agent开发" / "G1降级.md").exists()  # 笔记照常落盘
        assert any(t == "notes.error" and "library_git" in d.get("error", "")
                   for t, d in fired)
