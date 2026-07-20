"""P0 路径穿越防护的回归测试。

覆盖分支 fix/p0-path-traversal 的全部改动：
- obsidian_tools._normalize_path 的 vault 范围校验（#1）
- delete_folder/create_folder 严格护栏（#2）
- file_operation batch_write/read 的安全水位对齐（#5）
- api_register / batch_copy_notes / review_to_obsidian / copy_to_notion 参数净化（#7）
- _is_blocked_path 大小写与空格（BLOCKED_FOLDERS 配置健壮性）
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def vault(tmp_path, monkeypatch):
    """临时 vault，并把各模块的 OBSIDIAN_VAULT 常量指过去。"""
    v = tmp_path / "vault"
    v.mkdir()
    (v / "note1.md").write_text("# 笔记一\n内容", encoding="utf-8")
    (v / "Bobo数据库").mkdir()
    (v / "Bobo数据库" / "工作").mkdir()
    (v / "Bobo数据库" / "工作" / "a.md").write_text("A", encoding="utf-8")
    monkeypatch.setattr("tools.obsidian_tools.OBSIDIAN_VAULT", str(v))
    monkeypatch.setattr("tools.file_writer.OBSIDIAN_VAULT", str(v))
    return v


@pytest.fixture
def outside_file(tmp_path):
    """vault 外的敏感文件，用于验证穿越被拦截且文件不受影响。"""
    f = tmp_path / "secret.txt"
    f.write_text("TOP SECRET", encoding="utf-8")
    return f


# ── #1: _normalize_path 范围校验 ──────────────────────────────────────

class TestNormalizePathContainment:
    def test_dotdot_escape_denied(self, vault):
        from tools.obsidian_tools import _normalize_path
        result = _normalize_path("../../outside.md")
        assert result.startswith("__PATH_DENIED__:")

    def test_absolute_path_denied(self, vault):
        from tools.obsidian_tools import _normalize_path
        # 剥掉一个前导 / 后仍是绝对路径
        result = _normalize_path("//etc/passwd")
        assert result.startswith("__PATH_DENIED__:")

    def test_destination_dotdot_denied(self, vault):
        from tools.obsidian_tools import _normalize_path
        result = _normalize_path("../../x.md", is_destination=True)
        assert result.startswith("__PATH_DENIED__:")

    def test_legit_filename_still_works(self, vault):
        from tools.obsidian_tools import _normalize_path
        result = _normalize_path("note1.md")
        assert result == str(vault / "note1.md")

    def test_legit_subdir_still_works(self, vault):
        from tools.obsidian_tools import _normalize_path
        result = _normalize_path("Bobo数据库/工作/a.md")
        assert result == str(vault / "Bobo数据库" / "工作" / "a.md")

    def test_multiple_matches_sentinel_passthrough(self, vault):
        from tools.obsidian_tools import _normalize_path
        # 根目录和 Bobo数据库 都不放，只在两个子目录放同名文件
        (vault / "subA").mkdir()
        (vault / "subB").mkdir()
        (vault / "subA" / "dup_note.md").write_text("A", encoding="utf-8")
        (vault / "subB" / "dup_note.md").write_text("B", encoding="utf-8")
        result = _normalize_path("dup_note.md")
        assert result.startswith("__MULTIPLE_MATCHES__:")


class TestObsidianToolsEndToEnd:
    def test_read_outside_denied(self, vault, outside_file):
        from tools.obsidian_tools import read_obsidian_note
        result = read_obsidian_note("../secret.txt")
        assert "拒绝访问" in result
        assert "TOP SECRET" not in result

    def test_delete_outside_denied(self, vault, outside_file):
        from tools.obsidian_tools import delete_note
        result = delete_note("../secret.txt")
        assert "拒绝访问" in result
        assert outside_file.exists()  # 文件必须还在

    def test_move_outside_denied(self, vault, outside_file):
        from tools.obsidian_tools import move_note
        result = move_note("../secret.txt", "Bobo数据库/偷来.md")
        assert "拒绝访问" in result
        assert outside_file.exists()
        assert not (vault / "Bobo数据库" / "偷来.md").exists()

    def test_rename_to_outside_denied(self, vault):
        from tools.obsidian_tools import rename_note
        result = rename_note("note1.md", "../../renamed.md")
        assert "拒绝访问" in result

    def test_list_folder_outside_denied(self, vault):
        from tools.obsidian_tools import list_folder
        result = list_folder("../../")
        assert "拒绝访问" in result

    def test_write_obsidian_outside_denied(self, vault, tmp_path):
        from tools.file_writer import write_obsidian
        result = write_obsidian("../evil.md", "恶意内容")
        assert "拒绝访问" in result
        assert not (tmp_path / "evil.md").exists()

    def test_append_obsidian_outside_denied(self, vault, outside_file):
        from tools.file_writer import append_obsidian
        result = append_obsidian("../secret.txt", "追加恶意")
        assert "拒绝访问" in result
        assert outside_file.read_text(encoding="utf-8") == "TOP SECRET"

    def test_write_obsidian_legit_still_works(self, vault):
        from tools.file_writer import write_obsidian
        result = write_obsidian("新笔记.md", "内容")
        assert "已写入" in result


# ── #2: delete_folder / create_folder 护栏 ────────────────────────────

class TestFolderGuards:
    def test_delete_folder_dotdot_refused(self, vault):
        from tools.obsidian_tools import delete_folder
        result = delete_folder("..", force=True)
        assert "非法文件夹名" in result
        assert vault.exists()  # vault 还在

    def test_delete_folder_absolute_refused(self, vault, tmp_path):
        from tools.obsidian_tools import delete_folder
        victim = tmp_path / "victim"
        victim.mkdir()
        result = delete_folder(str(victim), force=True)
        assert "非法文件夹名" in result
        assert victim.exists()

    def test_delete_folder_legit_still_works(self, vault, monkeypatch):
        # 避免 tmp 路径（/private/...）撞上默认屏蔽词
        monkeypatch.setattr("tools.obsidian_tools.BLOCKED_FOLDERS", ["私密"])
        from tools.obsidian_tools import delete_folder
        result = delete_folder("工作", force=True)
        assert "已删除" in result
        assert not (vault / "Bobo数据库" / "工作").exists()

    def test_create_folder_traversal_refused(self, vault, tmp_path):
        from tools.obsidian_tools import create_folder
        result = create_folder("../../sneaky")
        assert "非法文件夹名" in result
        assert not (tmp_path.parent / "sneaky").exists()


# ── #5: file_operation 安全水位对齐 ───────────────────────────────────

class TestFileOperation:
    def test_batch_write_denied_path(self):
        from tools.file_operation import execute
        result = execute(
            action="batch_write",
            files=[{"path": "~/.zshrc", "content": "evil"}],
        )
        assert "❌" in result
        assert "0 个成功" in result

    def test_batch_write_legit_file(self, tmp_path):
        from tools.file_operation import execute
        target = tmp_path / "ok.txt"
        result = execute(
            action="batch_write",
            files=[{"path": str(target), "content": "hello"}],
        )
        assert "1 个成功" in result
        assert target.read_text() == "hello"

    def test_batch_write_non_dict_entry_no_crash(self, tmp_path):
        from tools.file_operation import execute
        result = execute(action="batch_write", files=["a.txt", 42, None])
        assert "0 个成功" in result
        assert "3 个失败" in result

    def test_read_sensitive_warning(self, tmp_path):
        from tools.file_operation import execute
        # 二进制文件触发 safe_read_check 警告
        bin_file = tmp_path / "x.bin"
        bin_file.write_bytes(b"\x00\x01\x02")
        result = execute(action="read", path=str(bin_file))
        assert "警告" in result or "安全" in result


# ── #7: 其余参数净化 ──────────────────────────────────────────────────

class TestApiRegister:
    def test_traversal_name_refused(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        from tools.api_register import execute
        result = execute(name="../../tmp/evil", base_url="https://x.com")
        assert "❌" in result
        assert not (tmp_path / "tmp").exists()

    def test_legit_name_accepted(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        from tools.api_register import execute
        result = execute(name="my-api_v2", base_url="https://x.com")
        assert "已注册" in result


class TestBatchCopyNotes:
    def test_destination_traversal_refused(self, vault, monkeypatch):
        monkeypatch.setenv("OBSIDIAN_VAULT", str(vault))
        from tools.batch_copy_notes import execute
        result = execute(["note1.md"], "../../../tmp/x")
        assert "拒绝访问" in result

    def test_source_traversal_refused(self, vault, outside_file, monkeypatch):
        monkeypatch.setenv("OBSIDIAN_VAULT", str(vault))
        from tools.batch_copy_notes import execute
        result = execute(["../secret.txt"], "Bobo数据库")
        assert "路径越界" in result
        assert not (vault / "Bobo数据库" / "secret.txt").exists()

    def test_legit_copy_still_works(self, vault, monkeypatch):
        monkeypatch.setenv("OBSIDIAN_VAULT", str(vault))
        from tools.batch_copy_notes import execute
        result = execute(["note1.md"], "Bobo数据库")
        assert "1 成功" in result
        assert (vault / "Bobo数据库" / "note1.md").exists()


class TestReviewToObsidian:
    def test_project_traversal_refused(self, monkeypatch, tmp_path):
        monkeypatch.setenv("OBSIDIAN_VAULT", str(tmp_path))
        from tools.review_to_obsidian import execute
        result = execute(pr_number=1, project="../../evil", findings="x")
        assert "❌" in result


class TestCopyToNotion:
    def test_traversal_refused(self, vault, outside_file, monkeypatch):
        monkeypatch.setenv("OBSIDIAN_VAULT", str(vault))
        from tools.copy_to_notion import execute
        result = execute("../secret.txt")
        assert "拒绝访问" in result
        assert "TOP SECRET" not in result


# ── BLOCKED_FOLDERS 健壮性 ────────────────────────────────────────────

class TestBlockedFolders:
    def test_case_insensitive(self, vault, monkeypatch):
        # 屏蔽词用拉丁字母验证大小写；同时验证 vault 外的系统目录组件
        # （如 tmp 路径里的 "private"）不会误伤 vault 内文件
        monkeypatch.setattr(
            "tools.obsidian_tools.BLOCKED_FOLDERS", ["SecretFolder", "日记"]
        )
        from tools.obsidian_tools import _is_blocked_path
        assert _is_blocked_path(str(vault / "secretfolder" / "x.md"))
        assert _is_blocked_path(str(vault / "SECRETFOLDER" / "x.md"))
        assert not _is_blocked_path(str(vault / "公开" / "x.md"))

    def test_system_dir_not_false_positive(self, vault, monkeypatch):
        # macOS tmp 在 /private 下，"Private" 屏蔽词不应误伤 vault 内路径
        monkeypatch.setattr(
            "tools.obsidian_tools.BLOCKED_FOLDERS", ["Private", "Archive", "日记"]
        )
        from tools.obsidian_tools import _is_blocked_path
        assert not _is_blocked_path(str(vault / "普通笔记.md"))
        assert _is_blocked_path(str(vault / "Private" / "x.md"))

    def test_config_strips_whitespace(self, monkeypatch):
        monkeypatch.setenv("BLOCKED_FOLDERS", "Private, Archive ,日记")
        import importlib
        import config
        importlib.reload(config)
        assert config.BLOCKED_FOLDERS == ["Private", "Archive", "日记"]
        importlib.reload(config)  # 复原，避免影响其他测试
