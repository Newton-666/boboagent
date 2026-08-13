"""TICKET-OBS-1: load_result 自我嵌套修复回归测试。

背景：load_result 的返回（[FULL RESULT] 前缀）被 retroactive_mark 误判为
"未标记的长结果"再次外部化（round_tracker.py 豁免只认 [RESULT] 前缀），
套娃最深 18 层。

验证：
1. load_result 的返回（[FULL RESULT] 前缀）不再被 retroactive_mark 再次标记
2. 嵌套 1 层（workspace 内容本身是 [FULL RESULT] 包装）→ 自动剥壳拿原文
3. 取回内容本身是 [RESULT] 标记（含 → id:）→ 自动跟进再 load
4. 深嵌套（>3 层）→ 返回 [ERROR] 不套娃
"""

import json

import pytest


class TestNoRemark:
    """TICKET-OBS-1 ①: load_result 返回不再被 retroactive_mark 标记。"""

    @pytest.fixture
    def engine(self, tmp_path, monkeypatch):
        from core.engine import Engine
        from tests.mock_llm import MockLLMCaller, text_response
        import core.tool_runner as tr

        monkeypatch.setattr(tr.ToolRunnerMixin, "WORKSPACE_DIR", str(tmp_path / "workspace"))
        caller = MockLLMCaller([text_response("ok")])
        eng = Engine(caller, None, test_mode=True)
        eng.current_tool_round = 20
        return eng

    def test_full_result_not_remarked(self, engine):
        """load_result 的返回（长 [FULL RESULT] 内容）不应被 retroactive 标记。"""
        # 20 条工具消息：cutoff = 最后 10 条之前，即扫描 idx 0-9。
        # idx 0,2,4,6,8 是 load_result 返回（[FULL RESULT] 前缀，>500 字符）→ 应豁免；
        # idx 1,3,5,7,9 是普通长结果 → 对照：仍应被标记（标记系统未被误伤）。
        for i in range(20):
            if i < 10 and i % 2 == 0:
                content = "[FULL RESULT] read_local_file(...)\n\n" + "x" * 600
            else:
                content = "y" * 600
            engine.history.append({
                "role": "tool",
                "tool_call_id": f"call_{i}",
                "content": content,
            })
        engine.tracker.retroactive_mark()

        # load_result 返回保持原样（不被再次外部化）
        for i in (0, 2, 4, 6, 8):
            content = engine.history[i]["content"]
            assert content.startswith("[FULL RESULT]"), (
                f"load_result 返回在 {i} 被再次标记: {content[:80]}"
            )
        # 对照：同扫描区内的普通长结果仍正常标记
        for i in (1, 3, 5, 7, 9):
            assert engine.history[i]["content"].startswith("[RESULT]"), (
                f"普通长结果在 {i} 应被标记"
            )

    def test_idempotent_with_full_result(self, engine):
        """多次 retroactive_mark 对 [FULL RESULT] 内容幂等（不累积套娃）。"""
        for i in range(20):
            if i < 10 and i % 2 == 0:
                content = "[FULL RESULT] read_local_file(...)\n\n" + "x" * 600
            else:
                content = "y" * 600
            engine.history.append({
                "role": "tool",
                "tool_call_id": f"call_{i}",
                "content": content,
            })
        engine.tracker.retroactive_mark()
        first_pass = [m["content"] for m in engine.history]
        engine.tracker.retroactive_mark()
        second_pass = [m["content"] for m in engine.history]
        assert first_pass == second_pass, "重复 retroactive_mark 对 [FULL RESULT] 不幂等"


class TestFollowNested:
    """TICKET-OBS-1 ②③: 防御兜底 — 取回内容仍是标记时自动跟进，限深 3。"""

    @pytest.fixture
    def workspace(self, tmp_path, monkeypatch):
        import tools.load_result as lr

        ws = tmp_path / "workspace"
        monkeypatch.setattr(lr, "_workspace_dir", lambda: str(ws))
        return ws

    @staticmethod
    def _write(workspace, mid, tool, args, content):
        workspace.mkdir(exist_ok=True)
        (workspace / f"{mid}.json").write_text(
            json.dumps({"tool": tool, "args": args, "content": content}),
            encoding="utf-8",
        )

    def test_nested_full_result_follows(self, workspace):
        """嵌套 1 层：workspace 存的是旧版 load_result 返回包装 → 自动剥壳拿原文。"""
        original = "这是真实文件全文。" + "真" * 800
        self._write(workspace, "retro_7_aaa", "tool", "{}",
                    f"[FULL RESULT] read_local_file(...)\n\n{original}")
        from tools.load_result import execute

        result = execute("retro_7_aaa", max_chars=5000)
        assert result.startswith("[FULL RESULT]")
        assert result.count("[FULL RESULT]") == 1, "返回仍含嵌套包装"
        assert "这是真实文件全文。" in result
        assert "真" * 800 in result

    def test_nested_marker_id_follows(self, workspace):
        """取回内容本身是 [RESULT] 标记（含 → id:）→ 提取 id 自动跟进。"""
        self._write(workspace, "retro_3_bbb", "tool", "{}",
                    "[RESULT] tool\n  → 摘要\n  → id: 5_abc12345, 900 chars")
        self._write(workspace, "5_abc12345", "web_search", '{"query":"x"}',
                    "真实搜索结果内容")
        from tools.load_result import execute

        result = execute("retro_3_bbb")
        assert "真实搜索结果内容" in result
        assert "→ id:" not in result, "已跟进解析，不应再暴露标记"

    def test_deep_nesting_errors(self, workspace):
        """深嵌套（4 层 [FULL RESULT] 包装）→ [ERROR] 报错，不套娃。"""
        content = "底层原文"
        for _ in range(4):
            content = f"[FULL RESULT] tool(...)\n\n{content}"
        self._write(workspace, "retro_9_ccc", "tool", "{}", content)
        from tools.load_result import execute

        result = execute("retro_9_ccc")
        assert result.startswith("[ERROR]")
        assert "嵌套超过" in result
        assert "拒绝继续跟进" in result

    def test_three_layer_boundary_ok(self, workspace):
        """边界：3 层包装仍自动剥壳成功（限深 3 内）。"""
        content = "边界原文"
        for _ in range(3):
            content = f"[FULL RESULT] tool(...)\n\n{content}"
        self._write(workspace, "retro_9_ddd", "tool", "{}", content)
        from tools.load_result import execute

        result = execute("retro_9_ddd")
        assert "边界原文" in result
        assert result.count("[FULL RESULT]") == 1
