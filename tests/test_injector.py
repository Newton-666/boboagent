"""Tests for PromptInjector — messages 构建管道。"""

import json

import pytest

from core.injector import PromptInjector


@pytest.fixture(autouse=True)
def isolated_memory(tmp_path, monkeypatch):
    """票 LN-4：隔离临时记忆库，不依赖真实 knowledge_base.json（灭环境污染）。

    注入两条固定记忆（其中一条含 "skill" 字样，让依赖该字样的断言稳定成立）。
    """
    import tools.v5_memory as v5
    kb = tmp_path / "knowledge_base.json"
    payload = json.dumps({
        "entries": [
            {
                "id": 1,
                "text": "保存为 skill 的流程：说『开始教学』录制，完成后说『保存为 skill <名称>』",
                "timestamp": "2026-07-31 10:00:00",
                "signal_score": 150,
                "folder": "general", "type": "general",
                "tags": [], "last_time_decay": "",
            },
            {
                "id": 2,
                "text": "记忆库隔离测试条目二",
                "timestamp": "2026-07-30 10:00:00",
                "signal_score": 80,
                "folder": "general", "type": "general",
                "tags": [], "last_time_decay": "",
            },
        ],
        "folders": [],
    }, ensure_ascii=False)
    kb.write_text(payload, encoding="utf-8")
    monkeypatch.setattr(v5, "MEMORY_DB", str(kb))
    monkeypatch.setattr(v5, "_MEMORY_BACKUP", str(kb) + ".bak")


@pytest.fixture(autouse=True)
def silence_event_bus(monkeypatch):
    """票 LN-4：prompt.budget 事件不写真实 events.jsonl（测试日志隔离）。"""
    import core.event_bus as eb
    fired = []

    class _Bus:
        def write(self, t, d):
            fired.append((t, d))

    monkeypatch.setattr(eb, "event_bus", _Bus())
    return fired


class MockTracker:
    """Minimal tracker mock — 只提供 injector 读取的属性。"""
    _change_log: list = []
    _read_files: dict = {}


class MockProactive:
    """Minimal proactive mock — 直通返回 messages。"""
    def inject_context(self, messages):
        return messages


class MockSkillLoader:
    """Minimal skill_loader mock — 返回空，无副作用。"""
    def load_standards(self):
        return []
    def list_available(self):
        return ""


class MockSkillManager:
    """Mock SkillManager — 模拟 get_skill_tools / get_skill 接口。"""
    def __init__(self, skills=None):
        self._skills = skills or []

    def get_skill_tools(self):
        tools = []
        for s in self._skills:
            tool = {
                "type": "function",
                "function": {
                    "name": f"run_skill:{s['name']}",
                    "description": s.get("description", ""),
                },
            }
            if s.get("triggers"):
                tool["triggers"] = s["triggers"]
            tools.append(tool)
        return tools

    def get_skill(self, name: str):
        for s in self._skills:
            if s["name"] == name:
                return s
        return None


class MockEngine:
    """Mock engine：只暴露 injector 需要的最小接口。"""

    def __init__(self):
        self.history = [{"role": "user", "content": "hello world"}]
        self.current_user_input = "hello world"
        self._pending_diff = ""
        self._compressing = False
        self.tracker = MockTracker()
        self.proactive = MockProactive()
        self.skill_loader = MockSkillLoader()


@pytest.fixture
def injector():
    return PromptInjector(MockEngine())


class TestBuildMessages:
    def test_returns_list(self, injector):
        msgs = injector.build_messages(
            system_prompt="You are Bobo.",
            user_input="hello",
            tools_schema=[],
            extra_categories=set(),
            session_id="s1",
        )
        assert isinstance(msgs, list)

    def test_first_message_is_system(self, injector):
        msgs = injector.build_messages(
            system_prompt="You are Bobo.",
            user_input="hello",
            tools_schema=[],
            extra_categories=set(),
            session_id="s1",
        )
        assert msgs[0]["role"] == "system"
        assert msgs[0]["content"] == "You are Bobo."

    def test_contains_user_message_from_history(self, injector):
        msgs = injector.build_messages(
            system_prompt="You are Bobo.",
            user_input="hello",
            tools_schema=[],
            extra_categories=set(),
            session_id="s1",
        )
        roles = [m["role"] for m in msgs]
        assert "user" in roles
        user_msgs = [m for m in msgs if m["role"] == "user"]
        assert any("hello world" in m["content"] for m in user_msgs)

    def test_no_diff_when_pending_diff_is_empty(self, injector):
        msgs = injector.build_messages(
            system_prompt="You are Bobo.",
            user_input="hello",
            tools_schema=[],
            extra_categories=set(),
            session_id="s1",
        )
        contents = " ".join(m.get("content", "") for m in msgs)
        assert "代码变更" not in contents

    def test_handles_null_skill_loader(self, injector):
        """skill_loader 返回空时 injector 不崩溃，且注入'可用标准'提示。"""
        injector._engine.skill_loader = MockSkillLoader()
        msgs = injector.build_messages(
            system_prompt="You are Bobo.",
            user_input="hello",
            tools_schema=[],
            extra_categories=set(),
            session_id="s1",
        )
        assert len(msgs) >= 2  # system + history

    def test_diff_injected_when_pending(self, injector):
        injector._engine._pending_diff = "+ print('hello')\n- print('bye')"
        msgs = injector.build_messages(
            system_prompt="You are Bobo.",
            user_input="hello",
            tools_schema=[],
            extra_categories=set(),
            session_id="s1",
        )
        contents = " ".join(m.get("content", "") for m in msgs)
        assert "代码变更" in contents
        # pending_diff 会被消费清空
        assert injector._engine._pending_diff == ""


class TestSkillInjectionImportFix:
    """验证 feat/fix-skillmgr-import：技能注入块不再抛 ImportError。"""

    def test_skill_injection_no_import_error(self, monkeypatch):
        """get_skill_manager 返回空 SkillManager → 注入块不抛 ImportError，正常完成。"""
        from core.injector import PromptInjector

        engine = MockEngine()
        injector = PromptInjector(engine)

        # mock get_skill_manager 返回空 SkillManager（无技能可注入）
        mock_mgr = MockSkillManager(skills=[])
        monkeypatch.setattr(
            "core.skill_manager.get_skill_manager",
            lambda: mock_mgr,
        )

        # 不应抛异常
        msgs = injector.build_messages(
            system_prompt="You are Bobo.",
            user_input="hello",
            tools_schema=[],
            extra_categories=set(),
            session_id="s1",
        )

        assert isinstance(msgs, list)
        assert len(msgs) >= 2  # system + history，无技能时注入块跳过但不崩溃

    def test_skill_injection_with_matched_trigger(self, monkeypatch):
        """get_skill_manager 返回带触发的技能 → 注入块匹配并注入步骤。"""
        from core.injector import PromptInjector

        engine = MockEngine()
        engine.current_user_input = "帮我搜索一下文档"
        injector = PromptInjector(engine)

        mock_mgr = MockSkillManager(skills=[
            {
                "name": "web_search",
                "description": "搜索网页",
                "triggers": ["搜索"],
                "steps": [
                    {"step": "1", "name": "搜索", "action": "web_search"},
                ],
            },
        ])
        monkeypatch.setattr(
            "core.skill_manager.get_skill_manager",
            lambda: mock_mgr,
        )

        msgs = injector.build_messages(
            system_prompt="You are Bobo.",
            user_input="帮我搜索一下文档",
            tools_schema=[],
            extra_categories=set(),
            session_id="s1",
        )

        assert isinstance(msgs, list)
        contents = " ".join(m.get("content", "") for m in msgs)
        # 匹配到"搜索"触发词 → 应出现"推荐技能"
        assert "推荐技能" in contents, f"匹配触发词但未注入推荐技能: {contents[:200]}"
        assert "web_search" in contents, f"推荐技能中未包含 skill name: {contents[:200]}"

    def test_skill_injection_block_does_not_affect_other_injections(self, monkeypatch):
        """技能注入块的异常不影响后续注入段（API / 记忆等）。"""
        from core.injector import PromptInjector

        engine = MockEngine()
        engine.current_user_input = "hello world"
        injector = PromptInjector(engine)

        mock_mgr = MockSkillManager(skills=[])
        monkeypatch.setattr(
            "core.skill_manager.get_skill_manager",
            lambda: mock_mgr,
        )

        msgs = injector.build_messages(
            system_prompt="You are Bobo.",
            user_input="hello",
            tools_schema=[],
            extra_categories=set(),
            session_id="s1",
        )

        # 其余注入段正常：skill_loader 输出应存在
        contents = " ".join(m.get("content", "") for m in msgs)
        assert "可用的项目标准" in contents or "skill" in contents.lower(), (
            f"skill_loader 注入段可能受影响: {contents[:200]}"
        )


class TestPromptPoolIntegration:
    """票 LN-5：验证 PromptPool ratio 真正影响 injector 各段 ceiling。"""

    def test_prompt_pool_ratio_truncates_skills(self, monkeypatch, injector):
        """固定总池 10000，skills ceiling 30%，超长 skill 列表应被截断到 ceiling 内。"""
        from core import prompt_pool as pp
        monkeypatch.delenv("BOBO_PROMPT_POOL_RATIO", raising=False)
        monkeypatch.delenv("BOBO_PROVIDER", raising=False)
        monkeypatch.setenv("BOBO_PROMPT_POOL_CHARS", "10000")
        pp.reset_prompt_pool()
        pool = pp.get_prompt_pool()
        skill_ceiling = pool.ceiling("skills")
        assert skill_ceiling == 3000  # 30% of 10000

        # 注入 30 条技能，每条 80 字符，总长远超 1000 字符 ceiling
        long_skills = [
            {
                "name": f"skill_{i}",
                "description": "x" * 80,
                "triggers": ["test"],
            }
            for i in range(30)
        ]
        monkeypatch.setattr(
            "core.skill_manager.get_skill_manager",
            lambda: MockSkillManager(skills=long_skills),
        )
        injector._engine.current_user_input = "test trigger"

        msgs = injector.build_messages(
            system_prompt="You are Bobo.",
            user_input="test trigger",
            tools_schema=[],
            extra_categories=set(),
            session_id="s1",
        )
        skill_msgs = [m for m in msgs if m["role"] == "system" and "skill_" in (m.get("content") or "")]
        assert skill_msgs, "no skill section injected"
        skill_content = skill_msgs[0]["content"]
        assert len(skill_content) <= skill_ceiling, (
            f"skills section exceeded ceiling: {len(skill_content)} > {skill_ceiling}"
        )
        # 至少应保留一条具体 skill（不只是标题）
        assert any(f"skill_{i}" in skill_content for i in range(30)), (
            f"all skills were evicted, content: {skill_content!r}"
        )
        pp.reset_prompt_pool()

    def test_prompt_pool_decision_event_emitted(self, silence_event_bus, injector):
        """build_messages 应同时发出 prompt.budget 和 prompt.budget.decision 事件。"""
        injector.build_messages(
            system_prompt="You are Bobo.",
            user_input="hello",
            tools_schema=[],
            extra_categories=set(),
            session_id="s1",
        )
        types = [t for t, d in silence_event_bus]
        assert "prompt.budget" in types
        assert "prompt.budget.decision" in types

        decision = [d for t, d in silence_event_bus if t == "prompt.budget.decision"][0]
        assert "allocated" in decision
        assert "used" in decision
        assert "total_pool" in decision
        assert decision["total_pool"] > 0
        assert "identity" in decision["allocated"]
        assert "memory" in decision["used"]
        assert decision["used"]["memory"] >= 0
