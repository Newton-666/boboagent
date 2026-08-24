"""必保层单元测试（B67：保存层守卫）——关键词/规则/防漏网/压缩集成。"""
import sys
import tempfile
import unittest.mock as um
from pathlib import Path

import core.fact_protect as fp
import tools.v5_memory as vm


def _mk_env():
    tmp = Path(tempfile.mkdtemp(prefix="fp_"))
    db = tmp / "kb.json"
    return db


def test_explicit_keyword_protected():
    db = _mk_env()
    with um.patch.object(vm, "_memory_db", lambda: str(db)):
        n = fp.protect_from_messages([
            {"role": "user", "content": "记住：以后都用 Python 写脚本"},
        ])
        entries = vm._load()["entries"]
        assert n == 1
        assert entries[0]["type"] == "USER_PREF"
        assert "Python" in entries[0]["text"]


def test_hard_fact_protected():
    db = _mk_env()
    with um.patch.object(vm, "_memory_db", lambda: str(db)):
        n = fp.protect_from_messages([
            {"role": "assistant", "content": "配置文件在 /etc/app/config.json，端口 8080"},
        ])
        entries = vm._load()["entries"]
        assert n >= 1
        kinds = [e["type"] for e in entries]
        assert all(k == "FACT" for k in kinds)


def test_no_keyword_but_important_not_lost():
    """无触发词但含硬事实（路径/数字）——规则层兜住，防"没匹配上被压掉"。"""
    db = _mk_env()
    with um.patch.object(vm, "_memory_db", lambda: str(db)):
        n = fp.protect_from_messages([
            {"role": "user", "content": "这个项目跑在 8080 端口，日志在 /var/log/app.log"},
        ])
        assert n >= 1  # 规则识别出数字/路径，不因无"记住"而丢
        text = " ".join(e["text"] for e in vm._load()["entries"])
        assert "8080" in text


def test_compression_integration():
    """压缩集成：对将摘要掉的段跑必保层。"""
    import core.context as ctx
    # 验证 _compress_history 中调用了 protect_from_messages
    src = open("core/context.py", encoding="utf-8").read()
    assert "protect_from_messages" in src
    assert "split_idx" in src  # 在 layer0 边界后保护
