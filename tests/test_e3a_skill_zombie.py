"""TICKET-E3a 验收测试 — 安葬旧 YAML 技能系统。

覆盖：
1. save_skill 不再 AttributeError（旧实现调不存在的 extract_steps_from_history）
2. save_skill 落盘到 data/skill-standards/（活系统）
3. list_skills 扫描 data/skill-standards/（供前端 /skills 展示）
4. injector 不再注入"推荐技能"段
5. engine 死方法 _check_skill_match 已移除
"""

import pytest


# ── 验收 1+2：save_skill 重写为活系统，必崩 bug 修复 ──────────

class FakeEngine:
    history = [
        {"role": "user", "content": "开始教学"},
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "function": {
                        "name": "file_operation",
                        "arguments": '{"action": "write"}',
                    }
                }
            ],
            "content": "我先写入文件",
        },
        {"role": "user", "content": "保存为 skill 测试"},
    ]


def test_save_skill_no_attribute_error(tmp_path, monkeypatch):
    """旧实现调 extract_steps_from_history → AttributeError 必崩；重写后不再崩。"""
    from core.skill_manager import SkillManager
    import tools.save_skill as ss

    monkeypatch.setattr(
        SkillManager, "_standards_dir", staticmethod(lambda: tmp_path)
    )
    ss.set_engine(FakeEngine())

    result = ss.execute("test-skill", "测试描述")
    assert "已保存技能" in result
    assert "test-skill" in result


def test_save_skill_writes_standard_md(tmp_path, monkeypatch):
    """save_skill 落盘到 data/skill-standards/<name>/standard.md（活系统格式）。"""
    from core.skill_manager import SkillManager
    import tools.save_skill as ss

    monkeypatch.setattr(
        SkillManager, "_standards_dir", staticmethod(lambda: tmp_path)
    )
    ss.set_engine(FakeEngine())

    ss.execute("search-test", "搜索测试")
    md = tmp_path / "search-test" / "standard.md"
    assert md.is_file()
    content = md.read_text(encoding="utf-8")
    assert "# search-test" in content
    assert "file_operation" in content  # 工具序列被提取


# ── 验收 3：list_skills 扫描活系统目录 ──────────

def test_list_skills_scans_standards_dir(tmp_path, monkeypatch):
    """list_skills 应返回 data/skill-standards/ 下的技能名（活系统）。"""
    from core.skill_manager import SkillManager

    (tmp_path / "alpha-skill" / "standard.md").parent.mkdir(parents=True)
    (tmp_path / "alpha-skill" / "standard.md").write_text("# alpha", encoding="utf-8")
    (tmp_path / "beta-skill" / "standard.md").parent.mkdir(parents=True)
    (tmp_path / "beta-skill" / "standard.md").write_text("# beta", encoding="utf-8")
    # 没有 standard.md 的目录不算技能
    (tmp_path / "not-a-skill").mkdir()

    monkeypatch.setattr(
        SkillManager, "_standards_dir", staticmethod(lambda: tmp_path)
    )
    sm = SkillManager()
    assert sm.list_skills() == ["alpha-skill", "beta-skill"]


# ── 验收 4：injector 不再注入推荐技能段 ──────────

def test_injector_no_skill_section(isolated_memory_db, monkeypatch):
    """段 2（推荐技能）已安葬：build_messages 输出不应再含'推荐技能'。

    显式请求 conftest.isolated_memory_db：在干净临时记忆库下跑，
    不依赖真实记忆内容——真实记忆库随时可能出现"推荐技能"字样，
    泛匹配断言会被环境污染误伤。
    """
    import sys
    from core.injector import PromptInjector

    class MockEngine:
        def __init__(self):
            self.history = [{"role": "user", "content": "hello world"}]
            self.current_user_input = "帮我搜索"
            self._pending_diff = ""
            self._compressing = False
            self.tracker = type("T", (), {"_change_log": [], "_read_files": {}})()
            self.proactive = type(
                "P", (), {"inject_context": lambda self, msgs: msgs}
            )()
            self.skill_loader = type(
                "S",
                (),
                {"load_standards": lambda self: [], "list_available": lambda self: ""},
            )()

        @property
        def system_prompt(self):
            return "You are Bobo."

        def build_system_prompt(self, **kw):
            return "You are Bobo."

        def get_pool(self):
            return None

        def recent_changes(self):
            return []

        def recent_reads(self):
            return {}

    sys.modules.setdefault("core.injector", sys.modules["core.injector"])
    engine = MockEngine()
    injector = PromptInjector(engine)

    msgs = injector.build_messages(
        system_prompt="You are Bobo.",
        user_input="帮我搜索",
        tools_schema=[],
        extra_categories=set(),
        session_id="s1",
    )
    contents = " ".join(m.get("content", "") for m in msgs)
    assert "推荐技能" not in contents


# ── 验收 5：engine 死方法已移除 ──────────

def test_engine_skill_dead_code_removed():
    """engine 不应再有 skills_dir / skill_manager / _check_skill_match。"""
    import inspect
    from core import engine as engine_mod

    src = inspect.getsource(engine_mod)
    assert "skills_dir" not in src
    assert "self.skill_manager" not in src
    assert "_check_skill_match" not in src
    # 活代码保留：教学模式录制保存
    assert "save_from_recording" in src
    assert "self.skill_executor" in src
