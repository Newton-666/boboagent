"""TICKET-PROFILE-1 验收测试 — USER.md 用户模型画像注入。

覆盖（票文验收）：
1. USER.md 注入：build_messages 产物含 USER.md 内容，且在前缀稳定段
   （自查协议之前、SELF L0 之后）
2. USER.md 文件缺失：静默跳过，不注入也不炸
注：USER.md 不计入 prompt.budget sections（LN-4 验收口径 sections 精确九段）。
"""

import pytest

import core.injector as injector_mod
from core.injector import PromptInjector


class MockEngine:
    def __init__(self, load_standards_result=None):
        self.history = [{"role": "user", "content": "hello world"}]
        self.current_user_input = "测试"
        self._pending_diff = ""
        self._compressing = False
        self._just_compressed = False
        self.tracker = type("T", (), {"_change_log": [], "_read_files": {}})()
        self.proactive = type(
            "P", (), {"inject_context": lambda self, msgs: msgs}
        )()
        self.skill_loader = type(
            "S",
            (),
            {"load_standards": lambda self, _r=load_standards_result: _r or []},
        )()


def _build(engine):
    return PromptInjector(engine).build_messages(
        system_prompt="You are Bobo.",
        user_input="测试",
        tools_schema=[],
        extra_categories=set(),
        session_id="s1",
    )


def test_user_profile_injected_before_self_check():
    """USER.md 注入，且位于自查协议之前（system_prompt → L0 → USER → 自查）。"""
    msgs = _build(MockEngine())
    contents = [m.get("content", "") for m in msgs]

    user_idx = next(
        i for i, c in enumerate(contents) if "代码评审意见" in c
    )
    self_check_idx = next(
        i for i, c in enumerate(contents) if "【上下文自查协议】" in c
    )
    assert user_idx < self_check_idx
    # 且紧跟 SELF L0 之后（L0 在 USER 之前）
    l0_idx = next(
        i for i, c in enumerate(contents) if "[SELF]" in c and "I am bobo" in c
    )
    assert l0_idx < user_idx


def test_user_profile_missing_file_silent(monkeypatch):
    """docs/USER.md 缺失时静默跳过，不注入也不炸。"""
    monkeypatch.setattr(
        injector_mod, "_USER_PROFILE_PATH",
        "/nonexistent/docs/USER.md",
    )
    msgs = _build(MockEngine())
    contents = " ".join(m.get("content", "") for m in msgs)
    assert "代码评审意见" not in contents
