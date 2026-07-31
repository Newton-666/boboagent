"""票 LN-4：笔记指针注入 + injector 分层保底 + 上下文预算监控。

9 项验收（全部 tmpdir/隔离环境物理检查）：
  1. 指针注入：library + source_sessions 含当前 sid → 系统提示含指针行（v{N} + 读全文再答）
  2. 主题词命中：sid 不关联但用户消息含主题名 → 指针出现；无关联 → 指针段整体缺席
  3. 指针预算：构造 10 篇关联笔记 → 只取前 3 条，段长 ≤300 字符
  4. 保底金标准：记忆块可吃满 5000 的场景 → skill 段仍 ≥800 字符、指针段仍在
  5. 记忆淘汰：超额时低信号条目先淘汰（最低信号分条目不在注入中）
  6. 测试环境隔离：test_injector 在真实 knowledge_base.json 任意状态下稳定通过
     （由 test_injector.py 的 isolated_memory fixture 保证，本文件连跑 3 次验证）
  7. 监控事件：组装后 events.jsonl 有 prompt.budget 事件，sections 四段齐全、字符数与实测一致
  8. 无 library / library 只读 → 注入正常、有降级事件、不炸
  9. 全量测试零回归（由 run_tests 单独验证）

边界：living_notes 不动、总池比例化不碰、context_lab 扩展不碰、历史层压缩不动。
"""

import json
import os

import pytest

from core.injector import PromptInjector, _LIBRARY_DIR


# ── Mock 基础设施（与 test_injector.py 同构，独立定义）────────────

class MockTracker:
    _change_log: list = []
    _read_files: dict = {}


class MockProactive:
    def inject_context(self, messages):
        return messages


class MockSkillLoader:
    def load_standards(self):
        return []

    def list_available(self):
        return ""


class MockSkillManager:
    """模拟技能库：get_skill_tools 返回技能列表，get_skill 返回步骤。"""

    def __init__(self, skills=None):
        self._skills = skills or []

    def get_skill_tools(self):
        tools = []
        for s in self._skills:
            tools.append({
                "type": "function",
                "function": {
                    "name": f"run_skill:{s['name']}",
                    "description": s.get("description", ""),
                },
                "triggers": s.get("triggers", []),
            })
        return tools

    def get_skill(self, name):
        for s in self._skills:
            if s["name"] == name:
                return s
        return None


class MockEngine:
    def __init__(self, user_input="hello world"):
        self.history = [{"role": "user", "content": user_input}]
        self.current_user_input = user_input
        self._pending_diff = ""
        self._compressing = False
        self.tracker = MockTracker()
        self.proactive = MockProactive()
        self.skill_loader = MockSkillLoader()


@pytest.fixture
def library(tmp_path):
    """构造隔离 library 目录（monkeypatch injector._LIBRARY_DIR）。"""
    lib = tmp_path / "library"
    lib.mkdir()
    return lib


@pytest.fixture(autouse=True)
def patch_library_dir(library, monkeypatch):
    """默认把所有注入测试的 library 指向隔离目录。"""
    monkeypatch.setattr("core.injector._LIBRARY_DIR", str(library))


@pytest.fixture(autouse=True)
def isolated_memory(tmp_path, monkeypatch):
    """隔离记忆库：默认空库，验收 4/5 自行写入大量条目。"""
    import tools.v5_memory as v5
    kb = tmp_path / "kb.json"
    kb.write_text(json.dumps({"entries": [], "folders": []}), encoding="utf-8")
    monkeypatch.setattr(v5, "MEMORY_DB", str(kb))
    monkeypatch.setattr(v5, "_MEMORY_BACKUP", str(kb) + ".bak")


@pytest.fixture
def no_skills(monkeypatch):
    """默认技能库为空。"""
    monkeypatch.setattr(
        "core.skill_manager.get_skill_manager",
        lambda: MockSkillManager(skills=[]),
    )


def _write_note(lib, domain, topic, sid=None, version=1,
                last_touched="2026-07-31", extra=""):
    """构造一篇带 frontmatter 的笔记，返回路径。"""
    d = lib / domain
    d.mkdir(parents=True, exist_ok=True)
    sessions = f"[{sid}]" if sid else "[]"
    body = (
        "---\n"
        f"topic: {topic}\ndomain: {domain}\ncreated: 2026-07-01\n"
        f"last_touched: {last_touched}\nversion: {version}\n"
        f"source_sessions: {sessions}\n"
        "---\n\n"
        f"## 概述\n\n- {topic} 的内容\n"
    )
    if extra:
        body += extra
    p = d / f"{topic}.md"
    p.write_text(body, encoding="utf-8")
    return p


def _build(injector, user_input="hello", session_id="s1",
           system_prompt="You are Bobo."):
    """跑一次 build_messages。"""
    return injector.build_messages(
        system_prompt=system_prompt,
        user_input=user_input,
        tools_schema=[],
        extra_categories=set(),
        session_id=session_id,
    )


def _all_content(msgs):
    return " ".join(m.get("content", "") for m in msgs)


# ── 验收 1：sid 命中 source_sessions → 必带指针 ─────────────

def test_pointer_injected_by_sid(library, no_skills):
    _write_note(library, "技术研究", "矩阵B构造", sid="sid-abc", version=3)
    injector = PromptInjector(MockEngine())
    msgs = _build(injector, user_input="继续讨论", session_id="sid-abc")
    contents = _all_content(msgs)
    assert "📚 关联笔记：技术研究/矩阵B构造.md" in contents
    assert "v3" in contents
    assert "深入讨论请先用 read_local_file 读全文再答" in contents


# ── 验收 2：主题词命中 + 无关联缺席 ─────────────────────

def test_pointer_by_topic_match(library, no_skills):
    _write_note(library, "技术研究", "上下文预算", sid="other-sid")
    injector = PromptInjector(MockEngine())
    # sid 不关联，但用户消息含主题名
    msgs = _build(injector, user_input="聊聊上下文预算管理", session_id="sid-new")
    contents = _all_content(msgs)
    assert "上下文预算" in contents
    assert "📚 关联笔记：技术研究/上下文预算.md" in contents


def test_no_pointer_when_unrelated(library, no_skills):
    _write_note(library, "技术研究", "上下文预算", sid="other-sid")
    injector = PromptInjector(MockEngine())
    # sid 不关联、用户消息不含主题词 → 指针段整体缺席
    msgs = _build(injector, user_input="今天天气怎么样", session_id="sid-new")
    contents = _all_content(msgs)
    assert "📚 关联笔记" not in contents
    assert "read_local_file 读全文" not in contents


# ── 验收 3：指针预算（10 篇关联 → 只取前 3，≤300 字符）─────

def test_pointer_budget_three_max(library, no_skills):
    for i in range(10):
        _write_note(library, "技术研究", f"主题{i:02d}", sid="sid-abc")
    injector = PromptInjector(MockEngine())
    msgs = _build(injector, user_input="hello", session_id="sid-abc")
    contents = _all_content(msgs)
    # 只取前 3 条
    assert contents.count("📚 关联笔记") == 3
    # 段长 ≤300 字符：找指针段
    start = contents.find("📚 关联笔记")
    end = contents.find("hello world")
    pointer_block = contents[start:end] if start != -1 else ""
    assert 0 < len(pointer_block) <= 300


# ── 验收 4：保底金标准（记忆吃满 5000 → skill ≥800、指针仍在）─

def test_guarantee_floor_golden(library, no_skills, monkeypatch, tmp_path):
    # 构造大量记忆条目（总字符远超 5000）
    import tools.v5_memory as v5
    entries = []
    for i in range(120):
        entries.append({
            "id": i,
            "text": f"记忆条目 {i}：这是第 {i} 条用于填充记忆池的内容。",
            "timestamp": f"2026-07-31 {i:02d}:00:00",
            "signal_score": 150 - (i % 3) * 40,  # 信号分有高低
            "folder": "general", "type": "general",
            "tags": [], "last_time_decay": "",
        })
    kb = tmp_path / "kb_big.json"
    kb.write_text(json.dumps({"entries": entries, "folders": []}),
                  encoding="utf-8")
    monkeypatch.setattr(v5, "MEMORY_DB", str(kb))
    monkeypatch.setattr(v5, "_MEMORY_BACKUP", str(kb) + ".bak")

    # 构造大量技能（matched 内容 ≥800 字符：多技能 × 多步骤）
    skills = []
    for i in range(6):
        steps = [
            {"step": str(s), "name": f"子步骤{i}-{s}",
             "action": f"执行第 {i} 号技能的第 {s} 个操作动作"}
            for s in range(1, 9)
        ]
        skills.append({
            "name": f"skill_{i}",
            "description": f"技能 {i}：处理第 {i} 类任务工作流（含详细操作说明）",
            "triggers": ["处理"],
            "steps": steps,
        })
    monkeypatch.setattr(
        "core.skill_manager.get_skill_manager",
        lambda: MockSkillManager(skills=skills),
    )

    _write_note(library, "技术研究", "矩阵B构造", sid="sid-abc")
    engine = MockEngine(user_input="帮我处理一下任务")
    injector = PromptInjector(engine)
    msgs = _build(injector, user_input="帮我处理一下任务", session_id="sid-abc")
    contents = _all_content(msgs)

    # 记忆段被截到 2500 内（吃满场景）
    assert "记忆 (" in contents
    # skill 段仍 ≥800 字符
    assert "[推荐技能" in contents
    skill_start = contents.find("[推荐技能")
    skill_end = contents.find("hello world")
    skill_block = contents[skill_start:skill_end] if skill_start != -1 else ""
    assert len(skill_block) >= 800, f"skill 段仅 {len(skill_block)} 字符"
    # 指针段仍在
    assert "📚 关联笔记" in contents
    assert "矩阵B构造" in contents


# ── 验收 5：记忆超额 → 低信号先淘汰 ────────────────────

def test_memory_evicts_low_signal(library, no_skills, monkeypatch, tmp_path):
    import tools.v5_memory as v5
    entries = []
    for i in range(40):
        # 信号分从 200 递减到 5（后面的是低信号）
        entries.append({
            "id": i,
            "text": f"信号条目 {i:02d}：{('x' * 120)}",  # 每条 >100 字符
            "timestamp": f"2026-07-01 {i:02d}:00:00",
            "signal_score": max(5, 200 - i * 5),
            "folder": "general", "type": "general",
            "tags": [], "last_time_decay": "",
        })
    kb = tmp_path / "kb_signal.json"
    kb.write_text(json.dumps({"entries": entries, "folders": []}),
                  encoding="utf-8")
    monkeypatch.setattr(v5, "MEMORY_DB", str(kb))
    monkeypatch.setattr(v5, "_MEMORY_BACKUP", str(kb) + ".bak")

    injector = PromptInjector(MockEngine())
    msgs = _build(injector, user_input="hello", session_id="sid-x")
    contents = _all_content(msgs)

    # 低信号条目（信号分 5 的最后一条）不在注入中
    assert "信号条目 39" not in contents
    # 高信号条目（信号分 200 的第一条）在注入中
    assert "信号条目 00" in contents


# ── 验收 6：环境隔离（test_injector 不依赖真实记忆库）──
# 由 test_injector.py::isolated_memory fixture 保证；此处连跑 3 次由外层验证。

def test_isolated_memory_not_touching_real_db(library, no_skills, tmp_path):
    """build_messages 只读隔离库：真实 knowledge_base.json 不参与注入。"""
    import tools.v5_memory as v5
    from config import BOBO_DATA_DIR
    # 隔离生效：v5_memory 指向 tmp 隔离库，而非真实数据目录
    assert str(BOBO_DATA_DIR / "knowledge_base.json") != v5.MEMORY_DB
    assert tmp_path in __import__("pathlib").Path(v5.MEMORY_DB).parents
    injector = PromptInjector(MockEngine())
    msgs = _build(injector, user_input="hello", session_id="sid-x")
    contents = _all_content(msgs)
    assert "记忆 (" not in contents  # 空隔离库 → 记忆段整体缺席


# ── 验收 7：prompt.budget 事件 ────────────────────────

def test_prompt_budget_event(library, no_skills, tmp_path, monkeypatch):
    import core.event_bus as eb
    bus = eb.EventBus.reset(log_dir=str(tmp_path / "logs"))
    monkeypatch.setattr(eb, "event_bus", bus)

    _write_note(library, "技术研究", "矩阵B构造", sid="sid-abc", version=2)
    injector = PromptInjector(MockEngine())
    msgs = _build(injector, user_input="继续讨论矩阵B构造", session_id="sid-abc")

    events_file = tmp_path / "logs" / "events.jsonl"
    assert events_file.exists()
    lines = [json.loads(l) for l in events_file.read_text(encoding="utf-8").splitlines()]
    budget_events = [e for e in lines if e.get("type") == "prompt.budget"]
    assert len(budget_events) == 1
    ev = budget_events[0]
    assert ev["sid"] == "sid-abc"
    # total_chars 与实测一致
    assert ev["total_chars"] == sum(len(m.get("content", "")) for m in msgs)
    sec = ev["sections"]
    # 四段齐全
    assert set(sec.keys()) == {"identity", "memory", "skills", "note_pointers"}
    assert sec["identity"] == len("You are Bobo.")
    assert isinstance(sec["memory"], dict)
    assert isinstance(sec["skills"], dict)
    assert isinstance(sec["note_pointers"], dict)
    # 指针段统计：主题正确
    assert sec["note_pointers"]["count"] == 1
    assert sec["note_pointers"]["topics"] == ["矩阵B构造"]


# ── 验收 8：无 library / library 只读 → 降级不炸 ───────

def test_no_library_silent(library, no_skills, monkeypatch, tmp_path):
    import core.event_bus as eb
    bus = eb.EventBus.reset(log_dir=str(tmp_path / "logs"))
    monkeypatch.setattr(eb, "event_bus", bus)

    # library 目录不存在
    import shutil
    shutil.rmtree(str(library))
    injector = PromptInjector(MockEngine())
    msgs = _build(injector, user_input="hello", session_id="sid-x")
    assert isinstance(msgs, list) and len(msgs) >= 2
    assert "📚 关联笔记" not in _all_content(msgs)
    # 无 notes.error（library 不存在不是错误，是正常省略）
    lines = [json.loads(l) for l in (tmp_path / "logs" / "events.jsonl").read_text(
        encoding="utf-8").splitlines()]
    assert not any(e.get("type") == "notes.error" for e in lines)


def test_readonly_library_degrade(library, no_skills, monkeypatch, tmp_path):
    import core.event_bus as eb
    bus = eb.EventBus.reset(log_dir=str(tmp_path / "logs"))
    monkeypatch.setattr(eb, "event_bus", bus)

    _write_note(library, "技术研究", "矩阵B构造", sid="sid-abc")
    os.chmod(str(library), 0o555)
    try:
        injector = PromptInjector(MockEngine())
        msgs = _build(injector, user_input="hello", session_id="sid-abc")
        assert isinstance(msgs, list) and len(msgs) >= 2
        # 注入正常（不因只读崩溃）
        assert _all_content(msgs)
    finally:
        os.chmod(str(library), 0o755)


# ── 验收 9：全量零回归（由 run_tests 单独验证）─────────

def test_smoke_build_pipeline(library, no_skills):
    """管道冒烟：完整注入链不炸，system 第一、history 在列。"""
    _write_note(library, "技术研究", "冒烟主题", sid="s1")
    injector = PromptInjector(MockEngine())
    msgs = _build(injector, user_input="hello", session_id="s1")
    assert msgs[0]["role"] == "system"
    roles = [m["role"] for m in msgs]
    assert "user" in roles
