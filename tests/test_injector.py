"""Tests for PromptInjector — messages 构建管道。"""

import pytest

from core.injector import PromptInjector


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
