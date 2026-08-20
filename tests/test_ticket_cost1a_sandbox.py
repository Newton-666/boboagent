"""票 TICKET-COST-1A-SANDBOX：工具配置效率实验沙盒专项测试。

验收（票原文）：
- 四档配置 31/14/8/82
- 判分器自身测试（确定性）
- 合并 schema 合法性断言
- core/ 零改动（git diff core/ 为空）
- API key 只从 data/.env 读；results/ 进 .gitignore
"""

import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys_path = str(ROOT)

from experiments.cost1a import configs, tasks, tools_impl  # noqa: E402


class TestConfigCounts:
    """验收：四档工具数 31/14/8/82"""

    def test_four_tiers(self):
        assert configs.validate() == {"A": 31, "B": 14, "C": 8, "D": 82}

    def test_a_is_park1_online(self):
        from tools import TOOLS_SCHEMA
        a = configs.config_a()
        assert len(a) == len(TOOLS_SCHEMA) == 31

    def test_d_is_full_82(self):
        from tools import ALL_TOOLS_SCHEMA
        assert len(configs.config_d()) == len(ALL_TOOLS_SCHEMA) == 82

    def test_c_is_core_8(self):
        names = {t["function"]["name"] for t in configs.config_c()}
        assert names == set(configs.CORE_8)


class TestMergedSchema:
    """验收：合并 schema 合法性（name/action 枚举/描述/required）"""

    def test_b_has_family_tools(self):
        names = configs.config_names("B")
        for merged in configs.FAMILIES:
            assert merged in names

    def test_action_enum_matches_members(self):
        b = {t["function"]["name"]: t for t in configs.config_b()}
        for merged, members in configs.FAMILIES.items():
            fn = b[merged]["function"]
            assert "action" in fn["parameters"]["properties"]
            assert fn["parameters"]["required"] == ["action"]
            enum = fn["parameters"]["properties"]["action"]["enum"]
            assert set(enum) == set(members), f"{merged} 枚举与成员不一致"
            assert fn["description"], f"{merged} 描述为空（合并原文要求）"
            assert len(fn["description"]) > 100, f"{merged} 描述过短，未合并原文"


class TestDispatcher:
    """tools_impl 分发正确性"""

    def test_core_read(self, tmp_path):
        (tmp_path / "x.txt").write_text("hello", encoding="utf-8")
        tools_impl.set_sandbox(tmp_path)
        r, a = tools_impl.dispatch("read_local_file", {"path": "x.txt"})
        assert r == "hello"

    def test_core_read_real_schema_argname(self, tmp_path):
        # 真实 schema 参数名是 filepath，不是 path——别名必须归一化
        (tmp_path / "x.txt").write_text("hello", encoding="utf-8")
        tools_impl.set_sandbox(tmp_path)
        r, a = tools_impl.dispatch("read_local_file", {"filepath": "x.txt"})
        assert r == "hello", r

    def test_core_edit(self, tmp_path):
        (tmp_path / "x.txt").write_text("a b", encoding="utf-8")
        tools_impl.set_sandbox(tmp_path)
        tools_impl.dispatch("edit_file", {"path": "x.txt", "old_string": "a", "new_string": "c"})
        assert (tmp_path / "x.txt").read_text(encoding="utf-8") == "c b"

    def test_obsidian_merged_action_write(self, tmp_path):
        tools_impl.set_sandbox(tmp_path)
        r, action = tools_impl.dispatch(
            "obsidian_tool",
            {"action": "write_obsidian", "path": "notes/meeting-2026.md",
             "content": "COST1A 沙盒实验启动"})
        assert action == "write_obsidian"
        assert (tmp_path / "notes" / "meeting-2026.md").exists()
        assert "COST1A 沙盒实验启动" in (tmp_path / "notes" / "meeting-2026.md").read_text(encoding="utf-8")

    def test_unknown_tool_stub(self, tmp_path):
        tools_impl.set_sandbox(tmp_path)
        r, a = tools_impl.dispatch("github_create_repo", {"name": "x"})
        assert "stub" in r

    def test_path_escape_blocked(self, tmp_path):
        tools_impl.set_sandbox(tmp_path)
        r, _ = tools_impl.dispatch("read_local_file", {"path": "/etc/passwd"})
        assert "越界" in r or "错误" in r


class TestJudges:
    """验收：判分器确定性（正确产物 pass / 错误产物 fail，不看模型自评）"""

    def _run(self, task_id, sandbox, reply, calls=None):
        return tasks.judge(task_id, sandbox, reply, calls or [])

    def test_t1_pass_and_fail(self, tmp_path):
        tasks.setup_t1(tmp_path)
        # 修复 + 测试通过 → pass
        src = (tmp_path / "buggy.py").read_text(encoding="utf-8")
        (tmp_path / "buggy.py").write_text(src.replace("a - b", "a + b"), encoding="utf-8")
        ok, _ = self._run("t1_bugfix", tmp_path, "done")
        assert ok
        # 未修复 → fail
        tasks.setup_t1(tmp_path)
        ok2, _ = self._run("t1_bugfix", tmp_path, "done")
        assert not ok2

    def test_t2_requires_location_and_value(self, tmp_path):
        tasks.setup_t2(tmp_path)
        assert self._run("t2_search", tmp_path, "在 mod_a.py 第 2 行，值 314159")[0]
        assert not self._run("t2_search", tmp_path, "找到了，值 314159")[0]  # 缺文件/行号
        assert not self._run("t2_search", tmp_path, "在 mod_b.py 第 2 行，值 42")[0]  # 错文件错值

    def test_t3_rename_both_files(self, tmp_path):
        tasks.setup_t3(tmp_path)
        a = (tmp_path / "a.py").read_text(encoding="utf-8")
        b = (tmp_path / "b.py").read_text(encoding="utf-8")
        (tmp_path / "a.py").write_text(a.replace("legacy_name", "modern_name"), encoding="utf-8")
        (tmp_path / "b.py").write_text(b.replace("legacy_name", "modern_name"), encoding="utf-8")
        assert self._run("t3_refactor", tmp_path, "done")[0]
        # 只改一个文件 → fail
        tasks.setup_t3(tmp_path)
        a = (tmp_path / "a.py").read_text(encoding="utf-8")
        (tmp_path / "a.py").write_text(a.replace("legacy_name", "modern_name"), encoding="utf-8")
        assert not self._run("t3_refactor", tmp_path, "done")[0]

    def test_t4_memory(self, tmp_path):
        tasks.setup_t4(tmp_path)
        tools_impl.set_sandbox(tmp_path)
        tools_impl.dispatch("save_memory", {"content": "团队代号为 COST1A-BRAVO"})
        assert self._run("t4_memory", tmp_path, "我记住了：COST1A-BRAVO")[0]
        assert not self._run("t4_memory", tmp_path, "记住了")[0]

    def test_t5_note_content(self, tmp_path):
        tasks.setup_t5(tmp_path)
        tools_impl.set_sandbox(tmp_path)
        tools_impl.dispatch("obsidian_tool",
                            {"action": "write_obsidian", "path": "notes/meeting-2026.md",
                             "content": "COST1A 沙盒实验启动"})
        assert self._run("t5_note", tmp_path, "done")[0]
        # 空内容 → fail
        tasks.setup_t5(tmp_path)
        assert not self._run("t5_note", tmp_path, "done")[0]


class TestActionErrorRate:
    """B 档 action 选错率统计逻辑"""

    def test_expected_action(self):
        assert tasks.EXPECTED_ACTIONS["t5_note"] == {"write_obsidian", "append_obsidian"}

    def test_rate_computation_semantics(self):
        # runner 中：家族调用 action 不在期望集 → 计错
        expected = tasks.EXPECTED_ACTIONS["t5_note"]
        calls = [
            {"tool": "obsidian_tool", "action": "write_obsidian"},
            {"tool": "obsidian_tool", "action": "read_obsidian"},  # 选错
        ]
        errs = sum(1 for c in calls if c["action"] not in expected)
        assert errs == 1


class TestIronRules:
    """验收：core/ 零改动 + key 只读 .env + results/ 进 .gitignore"""

    def test_core_untouched(self):
        r = subprocess.run(["git", "diff", "--stat", "core/"],
                           capture_output=True, text=True, cwd=str(ROOT))
        # 票 COST-1c ① 特批白名单：core/llm_caller.py 仅加 usage 事件透传（零逻辑改动）；
        # 票 COST-2 特批白名单：core/injector.py 仅限两处（NOW 锚点后移 + 小时级精度）；
        # 票 SAFETY-1 特批白名单：core/command_safety.py 进程杀灭分级（kill/pkill/
        # killall 误杀自身后端与桌面端渲染进程的根治疗，diff 须含 SAFETY-1 标记）；
        # 票 COST-3 特批白名单：core/context.py + core/engine.py（工作锚点属性化 +
        # 工具集全量稳定，diff 须含 COST-3 标记）；
        # 票 DESK-P1 特批白名单：core/engine_adapter.py + core/tool_runner.py（会话
        # 项目根注入链路：gateway 落库 → engine 属性 → injector 尾部段 / execute_terminal cwd）；
        # 票 TICKET-PROFILE-5 特批白名单：core/signal_detector.py（行为信号两级检测
        # 流水线：关键词门卫 + LLM 精判，owner 授权，diff 须含 PROFILE-5 标记）；
        # 过滤掉特批文件行与 --stat 汇总行（"1 file changed"）
        lines = [l for l in r.stdout.strip().splitlines()
                 if l.strip() and "core/llm_caller.py" not in l
                 and "core/injector.py" not in l
                 and "core/command_safety.py" not in l
                 and "core/context.py" not in l
                 and "core/engine.py" not in l
                 and "core/engine_adapter.py" not in l
                 and "core/tool_runner.py" not in l
                 and "core/signal_detector.py" not in l
                 and "file changed" not in l and "files changed" not in l]
        assert lines == [], f"core/ 有改动: {r.stdout.strip()}"

    def test_results_in_gitignore(self):
        gi = (ROOT / ".gitignore").read_text(encoding="utf-8")
        assert "results/" in gi or "experiments/cost1a/results" in gi

    def test_no_hardcoded_key(self):
        # 只有 runner.py 碰 API key（经 config 从 data/.env 读）；禁止硬编码
        runner_src = (ROOT / "experiments" / "cost1a" / "runner.py").read_text(encoding="utf-8")
        assert "sk-" not in runner_src
        assert ("DEEPSEEK_" + "API_KEY=") not in runner_src
        assert "from config import" in runner_src  # key 只从 config（.env）读

    def test_all_new_files_under_experiments(self):
        # 沙盒全部新文件在 experiments/cost1a/ 下（除测试与报告）
        for f in Path(ROOT / "experiments" / "cost1a").glob("*.py"):
            assert f.name in ("__init__.py", "runner.py", "tools_impl.py",
                              "configs.py", "tasks.py", "report.py"), f
