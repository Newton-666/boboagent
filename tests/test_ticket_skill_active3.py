"""TICKET-SKILL-ACTIVE-3 专项测试 — skill 自动沉淀（B 票）。

覆盖（票验收）：
- L1 一级门卫：同模式（工具名+参数指纹）≥3 次 → 触发；2 次 → 不触发（边界）；
  不同命令不算同模式；无参数历史退化为工具名聚类
- L2 二级精判：值得（固定流程）→ 草案（name/triggers/steps）；
  不值得（一次性）→ None 静默；LLM 异常/垃圾输出 → None（零打扰）
- L3 三级沉淀：save_custom_skill 落 data/skills/custom/<name>/standard.md
  （格式含 keywords/步骤）+ skill.activate emit 一次（前端卡）+ 冷却记录
- L4 防刷屏：同 session 二次不触发；已沉淀模式不重复；每日限一次
- L5 治理联动：沉淀后可被 skills.list 扫到（custom 组）+ enabled 默认 true

所有路径 monkeypatch 到 tmp_path（不碰真实 events.jsonl / skills/）。
"""

import json
import re
from pathlib import Path

import pytest

import core.skill_sedimenter as sed


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """隔离：数据文件全指 tmp_path；session 冷却清空。"""
    monkeypatch.setattr(sed, "_EVENTS_FILE", tmp_path / "events.jsonl")
    monkeypatch.setattr(sed, "_CUSTOM_DIR", tmp_path / "custom")
    monkeypatch.setattr(sed, "_SEDIMENTED_FILE", tmp_path / "sedimented.json")
    monkeypatch.setattr(sed, "_session_done", set())
    return tmp_path


def _write_events(path, events: list):
    """写 events.jsonl（每条一行 JSON）。"""
    with open(path, "w", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")


def _tool_exec(name, args=None):
    evt = {"type": "tool.exec", "name": name}
    if args is not None:
        evt["args_summary"] = json.dumps(args)
    return evt


def _judge_resp(content: str) -> dict:
    return {"choices": [{"message": {"content": content}}]}


# ── L1：一级数量门卫 ─────────────────────────────────────────────────

def test_l1_three_same_pattern_triggers(tmp_path):
    """同模式（execute_terminal + pytest tests/）≥3 次 → count_patterns 命中。"""
    _write_events(tmp_path / "events.jsonl", [
        _tool_exec("execute_terminal", {"command": "cd /x && pytest tests/test_a.py"}),
        _tool_exec("execute_terminal", {"command": "cd /x && pytest tests/test_b.py"}),
        _tool_exec("execute_terminal", {"command": "cd /x && pytest tests/test_c.py"}),
    ])
    counts = sed.count_patterns()
    assert "execute_terminal|pytest tests/" in counts, f"应聚类为 pytest tests/: {counts}"
    assert counts["execute_terminal|pytest tests/"] == 3


def test_l1_two_times_not_trigger(tmp_path):
    """边界：仅 2 次 → 不触发（count_patterns 空）。"""
    _write_events(tmp_path / "events.jsonl", [
        _tool_exec("execute_terminal", {"command": "pytest tests/test_a.py"}),
        _tool_exec("execute_terminal", {"command": "pytest tests/test_b.py"}),
    ])
    assert sed.count_patterns() == {}


def test_l1_different_commands_not_same_pattern(tmp_path):
    """不同命令（pytest vs git commit）不聚类。"""
    _write_events(tmp_path / "events.jsonl", [
        _tool_exec("execute_terminal", {"command": "pytest tests/"}),
        _tool_exec("execute_terminal", {"command": "pytest tests/"}),
        _tool_exec("execute_terminal", {"command": "pytest tests/"}),
        _tool_exec("execute_terminal", {"command": "git commit -m x"}),
        _tool_exec("execute_terminal", {"command": "git commit -m y"}),
    ])
    counts = sed.count_patterns()
    assert "execute_terminal|pytest tests/" in counts, f"pytest 3 次应命中: {counts}"
    assert "execute_terminal|git commit" not in counts, "git commit 仅 2 次不得命中"


def test_l1_no_args_fallback_to_tool_name(tmp_path):
    """历史记录无 args_summary（旧版本）→ 退化为纯工具名聚类。"""
    _write_events(tmp_path / "events.jsonl", [
        _tool_exec("read_local_file"),
        _tool_exec("read_local_file"),
        _tool_exec("read_local_file"),
    ])
    counts = sed.count_patterns()
    assert counts.get("read_local_file") == 3, f"应退化为工具名: {counts}"


def test_l1_empty_or_broken_file(tmp_path):
    """文件缺失/损坏 → 空（一级静默，零打扰）。"""
    assert sed.count_patterns() == {}
    (tmp_path / "events.jsonl").write_text("{bad json\n", encoding="utf-8")
    assert sed.count_patterns() == {}


# ── L2：二级 LLM 精判 ────────────────────────────────────────────────

def test_l2_worth_generates_draft():
    """值得（固定流程）→ 草案 dict（name/triggers/steps）。"""
    draft = sed._judge(
        "execute_terminal|pytest tests/",
        lambda msgs, **kw: _judge_resp(
            '{"worth": true, "name": "pytest-runner", "triggers": ["跑测试", "pytest"],'
            ' "steps": ["cd 项目根", "跑 pytest tests/"]}'
        ),
    )
    assert draft == {
        "name": "pytest-runner",
        "triggers": ["跑测试", "pytest"],
        "steps": ["cd 项目根", "跑 pytest tests/"],
    }


def test_l2_not_worth_silent():
    """不值得（一次性/用户偏好手动）→ None（静默）。"""
    assert sed._judge("execute_terminal|pytest tests/",
                      lambda msgs, **kw: _judge_resp('{"worth": false}')) is None


def test_l2_llm_failure_silent():
    """LLM 异常 / 错误返回 / 垃圾输出 → None（零打扰）。"""
    assert sed._judge("x|y", lambda msgs, **kw: (_ for _ in ()).throw(RuntimeError("boom"))) is None
    assert sed._judge("x|y", lambda msgs, **kw: {"error": "rate limit"}) is None
    assert sed._judge("x|y", lambda msgs, **kw: _judge_resp("完全不是 JSON 的废话")) is None
    assert sed._judge("x|y", lambda msgs, **kw: _judge_resp('{"worth": true, "name": "Bad Name!"}')) is None


def test_l2_cold_call_disables_thinking():
    """精判必须带 thinking_disabled=True（P5-400 同款防 400）。"""
    seen = {}

    def fake_llm(msgs, **kw):
        seen.update(kw)
        return _judge_resp('{"worth": false}')

    sed._judge("x|y", fake_llm)
    assert seen.get("thinking_disabled") is True, "冷调用必须关 thinking"
    assert seen.get("use_tools") is False


# ── L3：三级自动沉淀 ─────────────────────────────────────────────────

def test_l3_save_custom_skill(tmp_path):
    """save_custom_skill → custom/<name>/standard.md 格式对齐（keywords/步骤）。"""
    name = sed.save_custom_skill(
        {"name": "pytest-runner", "triggers": ["跑测试"], "steps": ["步骤一", "步骤二"]},
        "execute_terminal|pytest tests/",
    )
    assert name == "pytest-runner"
    fp = tmp_path / "custom" / "pytest-runner" / "standard.md"
    assert fp.exists(), "standard.md 应落地"
    text = fp.read_text(encoding="utf-8")
    assert "# pytest-runner v1" in text
    assert "> keywords: 跑测试" in text
    assert "1. 步骤一" in text and "2. 步骤二" in text
    assert "> source: auto-sedimented" in text


def test_l3_full_pipeline_sediments(tmp_path, monkeypatch):
    """全链：3 次模式 + 值得 → 沉淀 + Skill 卡 emit 一次 + 冷却记录。"""
    _write_events(tmp_path / "events.jsonl", [
        _tool_exec("execute_terminal", {"command": "pytest tests/a"}),
        _tool_exec("execute_terminal", {"command": "pytest tests/b"}),
        _tool_exec("execute_terminal", {"command": "pytest tests/c"}),
    ])
    # event_bus 桩（收集 write）
    import core.event_bus as eb
    fired = []

    class _Bus:
        def write(self, t, d):
            fired.append((t, d))

    monkeypatch.setattr(eb, "event_bus", _Bus())

    sed._sediment_skill(
        "sess-1",
        lambda msgs, **kw: _judge_resp(
            '{"worth": true, "name": "pytest-runner", "triggers": ["跑测试"],'
            ' "steps": ["跑 pytest tests/"]}'
        ),
    )
    # 沉淀落地
    fp = tmp_path / "custom" / "pytest-runner" / "standard.md"
    assert fp.exists(), "全链应沉淀 standard.md"
    # Skill 卡 emit 恰一次
    act = [e for e in fired if e[0] == "skill.activate"]
    assert len(act) == 1, f"应 emit 一次 skill.activate: {fired}"
    assert act[0][1] == {"skill_name": "pytest-runner"}
    # 冷却记录
    data = json.loads((tmp_path / "sedimented.json").read_text(encoding="utf-8"))
    assert "execute_terminal|pytest tests/" in data["patterns"], "已沉淀模式应入冷却"
    assert data.get("last_date"), "应记录当日冷却"


def test_l3_not_worth_silent_no_files(tmp_path, monkeypatch):
    """静默路径：不值得 → 无文件 + 无 emit（零打扰）。"""
    _write_events(tmp_path / "events.jsonl", [
        _tool_exec("execute_terminal", {"command": "ls"}),
        _tool_exec("execute_terminal", {"command": "ls"}),
        _tool_exec("execute_terminal", {"command": "ls"}),
    ])
    import core.event_bus as eb
    fired = []
    monkeypatch.setattr(eb, "event_bus", type("B", (), {"write": lambda self, t, d: fired.append((t, d))})())
    sed._sediment_skill("sess-2", lambda msgs, **kw: _judge_resp('{"worth": false}'))
    assert not (tmp_path / "custom").exists() or not list((tmp_path / "custom").iterdir()), \
        "不值得 → 不得沉淀文件"
    assert not [e for e in fired if e[0] == "skill.activate"], "不值得 → 不得 emit"


# ── L4：防刷屏（冷却）────────────────────────────────────────────────

def test_l4_same_session_no_repeat(tmp_path, monkeypatch):
    """同 session 二次调用不重复触发（judge 不再被调）。"""
    _write_events(tmp_path / "events.jsonl", [
        _tool_exec("execute_terminal", {"command": "pytest a"}) for _ in range(3)
    ])
    calls = {"n": 0}

    def fake_llm(msgs, **kw):
        calls["n"] += 1
        return _judge_resp('{"worth": false}')

    sed._sediment_skill("sess-x", fake_llm)
    sed._sediment_skill("sess-x", fake_llm)  # 同 session 第二次
    assert calls["n"] == 1, f"同 session 应只精判一次: {calls}"


def test_l4_sedimented_pattern_not_repeat(tmp_path):
    """已沉淀模式不重复（sedimented.json patterns 含该模式 → 不触发）。"""
    _write_events(tmp_path / "events.jsonl", [
        _tool_exec("execute_terminal", {"command": "pytest a"}) for _ in range(3)
    ])
    (tmp_path / "sedimented.json").write_text(
        json.dumps({"patterns": ["execute_terminal|pytest a"], "last_date": ""}),
        encoding="utf-8",
    )
    assert not sed._can_trigger("sess-y", "execute_terminal|pytest a")


def test_l4_daily_once(tmp_path):
    """每日限一次：last_date=今天 → 不触发。"""
    from datetime import date
    (tmp_path / "sedimented.json").write_text(
        json.dumps({"patterns": [], "last_date": date.today().isoformat()}),
        encoding="utf-8",
    )
    assert not sed._can_trigger("sess-z", "any|pattern")


# ── L5：治理联动（SKILL-PANEL Custom 组可见 + enabled 默认 true）─────

def test_l5_custom_visible_in_skills_list(tmp_path, monkeypatch):
    """沉淀后 skills.list 可扫到 custom 组，enabled 默认 true。"""
    sed.save_custom_skill(
        {"name": "pytest-runner", "triggers": ["跑测试"], "steps": ["跑 pytest tests/"]},
        "execute_terminal|pytest tests/",
    )
    # 复用 SKILL-PANEL handler 扫描（monkeypatch 其 custom 目录到 tmp）
    import importlib
    h = importlib.import_module("bobo_tui_gateway.handlers.skills")
    real = h._CUSTOM_DIR
    try:
        h._CUSTOM_DIR = tmp_path / "custom"
        r = h.handle_skills_list({}, "r1", None)
        custom = r["result"]["custom"]
        assert any(x["name"] == "pytest-runner" for x in custom), f"custom 组应可扫到: {custom}"
        item = [x for x in custom if x["name"] == "pytest-runner"][0]
        assert item["enabled"] is True, "沉淀 skill 默认 enabled=true"
    finally:
        h._CUSTOM_DIR = real


# ── L6：异步入口形态（不阻塞、daemon 线程）──────────────────────────

def test_l6_async_entry_nonblocking(tmp_path):
    """maybe_sediment_skill 返回后主线程不等待（daemon 异步）。"""
    _write_events(tmp_path / "events.jsonl", [
        _tool_exec("execute_terminal", {"command": "pytest a"}) for _ in range(3)
    ])
    t0 = __import__("time").time()
    sed.maybe_sediment_skill("sess-a", lambda msgs, **kw: _judge_resp('{"worth": false}'), delay=0.05)
    elapsed = __import__("time").time() - t0
    assert elapsed < 0.5, f"异步入口应立刻返回: {elapsed:.2f}s"
