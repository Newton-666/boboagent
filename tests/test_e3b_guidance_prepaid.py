"""TICKET-E3b 验收测试 — GUIDANCE 进预付层 + 段9未命中清单删除 + 段5死代码安葬。

覆盖（票文 E10）：
1. GUIDANCE 注入：build_messages 产物含 [CAPABILITY MAP]，且紧跟自查协议之后
2. GUIDANCE 文件缺失：静默跳过，不注入也不炸
3. 段 9 未命中清单：load_standards 无命中时产物不含"可用的项目标准"
4. 段 9 命中回归：load_standards 有命中时仍注入标准全文
5. 段 5 安葬：OBSIDIAN_VAULT 指向含 AGENTS.md 的目录也不注入 [项目规则 (AGENTS.md)]
6. prompt.budget 事件含 guidance 段统计
"""

import pytest

import core.injector as injector_mod
from core.injector import PromptInjector


@pytest.fixture(autouse=True)
def silence_event_bus(monkeypatch):
    """prompt.budget 事件不写真实 events.jsonl（测试日志隔离）。"""
    import core.event_bus as eb

    fired = []

    class _Bus:
        def write(self, t, d):
            fired.append((t, d))

    monkeypatch.setattr(eb, "event_bus", _Bus())
    return fired


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


def test_guidance_injected_after_self_check():
    """GUIDANCE 预付层注入，且位于自查协议段之后。"""
    msgs = _build(MockEngine())
    contents = [m.get("content", "") for m in msgs]

    self_check_idx = next(
        i for i, c in enumerate(contents) if "【上下文自查协议】" in c
    )
    guidance_idx = next(
        i for i, c in enumerate(contents) if "[CAPABILITY MAP]" in c
    )
    assert guidance_idx > self_check_idx


def test_guidance_missing_file_silent(monkeypatch):
    """docs/GUIDANCE.md 缺失时静默跳过，不注入也不炸。"""
    monkeypatch.setattr(
        injector_mod, "_GUIDANCE_PATH",
        "/nonexistent/docs/GUIDANCE.md",
    )
    msgs = _build(MockEngine())
    contents = " ".join(m.get("content", "") for m in msgs)
    assert "[CAPABILITY MAP]" not in contents


def test_section9_no_hit_no_available_list():
    """段 9 未命中时不注入"可用的项目标准"清单（E3b 已删 else 分支）。"""
    msgs = _build(MockEngine(load_standards_result=[]))
    contents = " ".join(m.get("content", "") for m in msgs)
    assert "可用的项目标准" not in contents


def test_section9_hit_still_injected():
    """段 9 命中时仍注入标准全文（回归）。"""
    msgs = _build(MockEngine(load_standards_result=["# bug 标准\n触发词: bug"]))
    contents = " ".join(m.get("content", "") for m in msgs)
    assert "## 项目标准" in contents
    assert "bug 标准" in contents


def test_section5_agents_removed(tmp_path, monkeypatch):
    """段 5 已安葬：OBSIDIAN_VAULT 指向含 AGENTS.md 的目录也不注入。"""
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "AGENTS.md").write_text(
        "# 项目规则\n永远先查文档再动手。", encoding="utf-8"
    )
    monkeypatch.setenv("OBSIDIAN_VAULT", str(vault))

    msgs = _build(MockEngine())
    contents = " ".join(m.get("content", "") for m in msgs)
    assert "[项目规则 (AGENTS.md)]" not in contents
    assert "永远先查文档再动手" not in contents


def test_prompt_budget_includes_guidance(silence_event_bus):
    """prompt.budget 事件 sections 含 guidance 段统计，且 chars > 0。"""
    _build(MockEngine())
    events = [d for t, d in silence_event_bus if t == "prompt.budget"]
    assert events, "应发出 prompt.budget 事件"
    sections = events[0]["sections"]
    assert "guidance" in sections
    assert sections["guidance"]["chars"] > 0
