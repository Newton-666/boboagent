"""TICKET-LEDGER-1B 回归测试 — 对账段去裸奔（内部上下文化，不进可见回复）。

覆盖：
- 1B-1 静态闸：engine.py 调用点只并入 history（_recon_internal 暂存 + 落 history 时
  合并），不再拼接进 _pending_content（可见终稿）；_workspace_recon 本体（只读
  git status/diff --stat）不动
- 1B-2 实弹：有工具轮收工 → 可见回复无 git 原文块（"工作区实况"/"git status"/
  "git diff" 全部不出现），但 history 内部上下文含对账段；模型自然语言对账
  （"改动 N 个文件"）照常出现在可见回复
- 1B-3 纯聊天回合（tool_round=0）→ 零注入（final 与 history 均无对账段）
- 1B-4 工作区干净（_workspace_recon 返回 ""）→ 零注入、零开销，行为不变

注：对账机制本身（只读 git、失败静默、收工闸触发时机）与汇报质量标准均不动，
仅改动"对账段去哪里"（可见终稿 → history 内部上下文）。
"""

import pytest

from tests.test_ticket_ledger_1 import (
    FakeLLMCaller,
    _make_engine,
    _make_tool_call,
    _run_with_capture,
)

RECON_SAMPLE = (
    "\n\n── 工作区实况（收工对账，只读）──\n"
    "git status --short: 3 项变更\n"
    " M core/engine.py\n"
    " M tests/test_ticket_ledger_1.py\n"
    "?? tests/test_ticket_ledger_1b.py\n"
    "git diff --stat:\n"
    " core/engine.py | 12 ++++++++----\n"
    "台账与汇报必须与以上工作区实况一致"
)


@pytest.fixture(autouse=True)
def _reset_ledger():
    from tools.task_ledger import _set_ledger
    _set_ledger([])
    yield
    _set_ledger([])


# ── 1B-1：静态闸 ───────────────────────────────────────────────────────

def test_1b_1_static_engine_callpoint():
    """调用点改为：对账段走局部变量 _recon，落 history 时并入；不拼 _pending_content。"""
    from pathlib import Path
    repo_root = Path(__file__).resolve().parent.parent  # tests/ -> 项目根（免疫 cwd 漂移）
    src = (repo_root / "core" / "engine.py").read_text(encoding="utf-8")

    # 调用点：不再拼接进 _pending_content
    assert "_recon = \"\"" in src, \
        "LEDGER-1B: 对账段应走局部变量 _recon（默认空串，零残留）"
    assert "_recon = self._workspace_recon()" in src, \
        "LEDGER-1B: 有工具轮时取工作区实况"
    assert "_pending_content = (self._pending_content or \"\") + _recon" not in src, \
        "LEDGER-1B: 旧路径（拼进可见终稿）必须移除"

    # 落 history：仅当 _recon 非空时并入 history 消息（不进可见终稿）
    assert "_hist_content = self._pending_content" in src, \
        "LEDGER-1B: 落 history 内容先取可见回复"
    assert "if _recon:" in src and "_hist_content = (_hist_content or \"\") + _recon" in src, \
        "LEDGER-1B: 对账段应并入 history 消息"
    assert 'self._append_to_history("assistant", _hist_content,' in src, \
        "LEDGER-1B: 落 history 使用合并后内容（F8 起带 thinking kwargs，前缀匹配）"

    # _workspace_recon 本体不动（只读 git status/diff --stat 机制保留）
    assert "def _workspace_recon(self)" in src, "对账机制不动: _workspace_recon 本体保留"
    assert '["git", "status", "--short"]' in src, "对账机制不动: 只读 git status"
    assert '["git", "diff", "--stat"]' in src, "对账机制不动: 只读 git diff --stat"


# ── 1B-2：实弹 —— 有工具轮收工 ─────────────────────────────────────────

def test_1b_2_visible_reply_no_git_raw_but_nl_recon(monkeypatch):
    """可见回复无 git 原文块；模型自然语言对账照常；history 含对账内部上下文。"""
    fake_llm = FakeLLMCaller([
        (None, [_make_tool_call("t1", "task_ledger", {
            "action": "create",
            "items": [{"id": "1", "title": "A", "status": "done",
                       "verify": "测试全绿", "evidence": "2302 passed"}],
        })]),
        (None, [_make_tool_call("t2", "edit_file",
                                {"file_path": "x.txt", "old_string": "a", "new_string": "b"})]),
        ("改好了。改动 1 个文件：x.txt", None),  # 模型自然语言对账
    ])
    engine = _make_engine(fake_llm, monkeypatch)
    monkeypatch.setattr(engine, "_workspace_recon", lambda: RECON_SAMPLE)
    final = _run_with_capture(engine, "改个文件")

    # 可见回复：无 git 原文块（"工作区实况"/"git status"/"git diff" 全部禁上屏）
    for banned in ("工作区实况", "git status", "git diff", "git diff --stat", "──"):
        assert banned not in final, f"git 原文不得上屏，含 {banned!r}: {final[:300]}"
    # 可见回复：模型自然语言对账照常
    assert "改动 1 个文件" in final, f"模型自然语言对账应保留: {final}"

    # history 内部上下文：含完整对账段（机制不破）
    hist_txt = "\n".join(m.get("content") or "" for m in engine.history)
    assert "工作区实况" in hist_txt, "对账段应并入 history"
    assert "git status --short: 3 项变更" in hist_txt, "history 应含 git 实况明细"
    assert "台账与汇报必须" in hist_txt, "history 应含对账约束说明"


# ── 1B-3：纯聊天回合零注入 ─────────────────────────────────────────────

def test_1b_3_chat_round_no_inject(monkeypatch):
    """纯聊天（tool_round=0）→ 对账不触发，final 与 history 均无对账段。"""
    fake_llm = FakeLLMCaller([("你好", None)])
    engine = _make_engine(fake_llm, monkeypatch)
    monkeypatch.setattr(engine, "_workspace_recon", lambda: RECON_SAMPLE)
    final = _run_with_capture(engine, "你好")
    assert "工作区实况" not in final
    hist_txt = "\n".join(m.get("content") or "" for m in engine.history)
    assert "工作区实况" not in hist_txt, "纯聊天不得注入对账"
    assert engine.state == engine.STATE_DONE


# ── 1B-4：工作区干净零开销 ─────────────────────────────────────────────

def test_1b_4_clean_workspace_no_inject(monkeypatch):
    """_workspace_recon 返回 ""（工作区干净）→ 零注入，行为不变。"""
    fake_llm = FakeLLMCaller([
        (None, [_make_tool_call("t1", "read_local_file", {"filepath": "x.txt"})]),
        ("读完了。改动 0 个文件。", None),
    ])
    engine = _make_engine(fake_llm, monkeypatch)
    monkeypatch.setattr(engine, "_workspace_recon", lambda: "")
    final = _run_with_capture(engine, "读个文件")
    assert "工作区实况" not in final
    hist_txt = "\n".join(m.get("content") or "" for m in engine.history)
    assert "工作区实况" not in hist_txt, "干净工作区不得注入对账段"
    assert engine.state == engine.STATE_DONE
