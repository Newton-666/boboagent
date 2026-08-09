'''TICKET-G2：grep_code 静默漏检修复 — 回归测试

覆盖（验收口径）：
1. gitignore 区（.gitignore 排除的目录/文件）埋词可搜到（--no-ignore-vcs）
2. 点开头的正常目录（.config/）与点文件埋词可搜到（--hidden）
3. 输出头部包含口径标注行；截断时明示
4. rg 可用与不可用（模拟回退）两条路径结果集一致
5. .git/ VCS 元目录两条路径一致跳过
'''

from pathlib import Path

import pytest

import tools.grep_code as gc
from tools.grep_code import execute, MAX_MATCHES


@pytest.fixture
def ignored_tree(tmp_path):
    '''gitignore 区 + 点目录 + .git 元目录埋词的文件树'''
    (tmp_path / ".gitignore").write_text("data/\n*.log\n# G2_IGNORERULE\n")
    (tmp_path / "data").mkdir()
    (tmp_path / "data/events.jsonl").write_text('{"tag": "G2_IGNORED_TOKEN"}\n')
    (tmp_path / "data/debug.log").write_text("G2_IGNORED_TOKEN log line\n")
    (tmp_path / ".config").mkdir()
    (tmp_path / ".config/app.conf").write_text("G2_DOTDIR_TOKEN=1\n")
    (tmp_path / ".dotfile.py").write_text("G2_DOTFILE_TOKEN = True\n")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git/config").write_text("G2_GIT_TOKEN = 1\n")
    (tmp_path / "normal.py").write_text("G2_NORMAL_TOKEN = 1\n")
    return tmp_path


class TestGitignoreZone:
    '''罪证 1：gitignore 区内容曾被静默跳过'''

    def test_gitignored_jsonl_found(self, ignored_tree):
        result = execute("G2_IGNORED_TOKEN", path=str(ignored_tree))
        assert "G2_IGNORED_TOKEN" in result
        assert "events.jsonl" in result
        assert "未找到" not in result

    def test_gitignored_log_found(self, ignored_tree):
        result = execute("G2_IGNORED_TOKEN", path=str(ignored_tree))
        assert "debug.log" in result


class TestHiddenZone:
    '''罪证 1：点开头目录/文件曾被静默跳过'''

    def test_dot_directory_found(self, ignored_tree):
        result = execute("G2_DOTDIR_TOKEN", path=str(ignored_tree))
        assert ".config" in result

    def test_dot_file_found(self, ignored_tree):
        result = execute("G2_DOTFILE_TOKEN", path=str(ignored_tree))
        assert ".dotfile.py" in result

    def test_gitignore_file_itself_searchable(self, ignored_tree):
        '''.gitignore 作为隐藏文件本身也应可搜（两条路径口径一致）'''
        result = execute("G2_IGNORERULE", path=str(ignored_tree))
        assert ".gitignore" in result


class TestGitDirSkipped:
    '''VCS 元目录 .git/ 两条路径一致跳过'''

    def test_git_dir_skipped(self, ignored_tree):
        '''.git/ 内唯一埋词 → 两条路径均未搜到（头部含搜索词属正常标注）'''
        result = execute("G2_GIT_TOKEN", path=str(ignored_tree))
        assert "未找到" in result
        assert ".git/config" not in result


class TestHeaderAnnotation:
    '''验收 3：输出头部含口径标注；截断时明示'''

    def test_output_has_scope_line(self, ignored_tree):
        result = execute("G2_NORMAL_TOKEN", path=str(ignored_tree))
        assert "口径" in result
        assert "跳过" in result

    def test_no_match_has_scope_line(self, ignored_tree):
        result = execute("G2_NOT_FOUND_XYZ", path=str(ignored_tree))
        assert "未找到" in result
        assert "口径" in result

    def test_truncation_annotated(self, tmp_path):
        '''超过 MAX_MATCHES 时头部明示截断'''
        for i in range(MAX_MATCHES + 10):
            (tmp_path / f"f{i:03d}.py").write_text(f"G2_TRUNC_TOKEN_{i} = 1\n")
        result = execute("G2_TRUNC_TOKEN", path=str(tmp_path), context=0)
        assert "截断" in result
        assert f"≥ {MAX_MATCHES}" in result


class TestPathConsistency:
    '''验收 2：rg 可用与不可用（模拟回退）两条路径结果集一致'''

    def test_rg_and_python_consistent(self, ignored_tree, monkeypatch):
        result_rg = execute("G2_", path=str(ignored_tree), context=0)
        # 模拟 rg 不可用：强制回退 Python
        monkeypatch.setattr(gc, "_search_ripgrep", lambda *a, **k: None)
        result_py = execute("G2_", path=str(ignored_tree), context=0)
        files_rg = _extract_files(result_rg)
        files_py = _extract_files(result_py)
        assert files_rg == files_py
        assert files_rg  # 非空


def _extract_files(output: str) -> set:
    '''从输出中提取 "── 文件 ──" 分组行（取 basename 消除绝对/相对路径差异）'''
    return {Path(line.strip(" ─").strip()).name for line in output.split("\n")
            if line.startswith("──")}
