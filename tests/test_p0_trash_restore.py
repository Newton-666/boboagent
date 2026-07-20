"""P0 trash 恢复路径穿越的回归测试（fix/p0-trash-restore）。

审计发现 #7：restore_checkpoint 的 trash 恢复此前双向穿越——
源端可逃出 ~/.bobo/trash 引用任意文件，目的端可写出 vault。
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def env(tmp_path, monkeypatch):
    """隔离的 HOME + vault + trash 目录。"""
    home = tmp_path / "home"
    trash = home / ".bobo" / "trash"
    trash.mkdir(parents=True)
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("OBSIDIAN_VAULT", str(vault))
    return {"home": home, "trash": trash, "vault": vault}


def _engine():
    from core.engine import Engine
    from tests.mock_llm import MockLLMCaller, text_response
    caller = MockLLMCaller([text_response("ok")])
    return Engine(caller, None, test_mode=True)


def _restore(engine, path_arg):
    tc = {"id": "t1", "function": {"name": "restore_checkpoint", "arguments": '{"path": "%s"}' % path_arg}}
    results = []
    engine._handle_restore_checkpoint(tc, results)
    return results[0]["content"]


class TestTrashRestoreTraversal:
    def test_source_dotdot_blocked(self, env):
        # 在 trash 外放一个"受害文件"
        victim = env["home"] / ".bobo" / "important_20260101"
        victim.write_text("重要数据", encoding="utf-8")
        result = _restore(_engine(), "trash:../important_20260101")
        assert "非法的回收站路径" in result
        assert victim.exists()  # 没被移动

    def test_source_absolute_blocked(self, env):
        result = _restore(_engine(), "trash:/etc/passwd")
        assert "非法的回收站路径" in result

    def test_destination_dotdot_neutralized(self, env):
        # trash_name 里的目录成分会被 basename 剥掉；
        # 即使构造出带 ../ 的名字，源端检查也会先拦下
        result = _restore(_engine(), "trash:../../tmp/evil_20260101")
        assert "非法的回收站路径" in result
        assert not (env["vault"].parent / "evil").exists()


class TestTrashRestoreLegit:
    def test_legit_restore_works(self, env):
        backup = env["trash"] / "笔记_20260101"
        backup.write_text("笔记内容", encoding="utf-8")
        result = _restore(_engine(), "trash:笔记_20260101")
        assert "已从回收站恢复" in result
        assert (env["vault"] / "笔记").read_text(encoding="utf-8") == "笔记内容"
        assert not backup.exists()  # 已从 trash 移走

    def test_restore_refuses_overwrite(self, env):
        (env["trash"] / "笔记_20260101").write_text("旧", encoding="utf-8")
        (env["vault"] / "笔记").write_text("新", encoding="utf-8")
        result = _restore(_engine(), "trash:笔记_20260101")
        assert "文件已存在" in result
        assert (env["vault"] / "笔记").read_text(encoding="utf-8") == "新"

    def test_missing_trash_item(self, env):
        result = _restore(_engine(), "trash:不存在_20260101")
        assert "未找到" in result
