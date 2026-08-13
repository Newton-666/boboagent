"""TICKET-CORE-R1：工具轮次智能分流 —— 60% 水位早提示 / 150 线死循环硬掐·在推进软着陆。

验收锚点：
  1. 60% 水位（默认 150 的 90 轮）：轻量收束提示，只提示不限制，记 round.watermark，只发一次
  2. 撞 150 线：连续 5 轮同模式或无推进信号 → stuck 硬掐（强制收尾指令）；
     仍在推进 → progressing 软提醒（完成当前子任务后收工）；均记 loop.verdict
  3. BOBO_MAX_TOOL_ROUNDS：未设置/非法 → 默认 150；合法值生效（水位按比例缩放）
  4. 铁律不动：200 深度硬断、500 步保险丝、收工闸语义
"""

import json
import pytest


@pytest.fixture
def engine():
    """构造非 test_mode 的 Engine（仅用判定逻辑，不需要真实 LLM 调用）。"""
    from core.engine import Engine
    from core.tool_executor import execute_tool
    from tests.mock_llm import MockLLMCaller, text_response

    caller = MockLLMCaller([text_response("Hello! I am Bobo.")])
    eng = Engine(caller, execute_tool, test_mode=False)
    eng.test_mode = False  # pytest 环境强制覆盖，确保不短路
    return eng


def _tool_round(tool_parts):
    """构造一轮带 tool_calls 的 assistant 消息。

    tool_parts: [(name, args_json_str), ...]
    """
    tcs = [
        {"id": f"call_{i}", "type": "function",
         "function": {"name": name, "arguments": args}}
        for i, (name, args) in enumerate(tool_parts)
    ]
    return {"role": "assistant", "content": "thinking...", "tool_calls": tcs}


def _read_events(path, etype):
    """从 event_bus 文件读指定类型的事件列表。"""
    import os
    if not os.path.exists(path):
        return []
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except Exception:
                continue
            if ev.get("type") == etype:
                out.append(ev)
    return out


class TestWatermark:
    """验收 1：60% 水位早提示（默认 150 → 90 轮）。"""

    def test_watermark_at_90_rounds(self, engine, monkeypatch, tmp_path):
        from core import event_bus as eb
        eb.event_bus.reset(log_dir=str(tmp_path))
        engine.current_tool_round = 90
        assert engine._check_guards() is False  # 只提示不限制
        # history 注入轻量收束提示
        user_msgs = [m["content"] for m in engine.history if m.get("role") == "user"]
        assert any("轮次过半" in c and "合并工具调用" in c for c in user_msgs), \
            f"90 轮应注入水位提示，实际: {user_msgs}"
        # 不注入强制收尾（语义区分：只提示不限制）
        assert not any("强制收尾" in c for c in user_msgs)
        # 事件留痕 round.watermark
        evs = _read_events(str(tmp_path / "events.jsonl"), "round.watermark")
        assert evs and evs[-1]["round"] == 90 and evs[-1]["max"] == 150

    def test_watermark_only_once(self, engine, monkeypatch, tmp_path):
        from core import event_bus as eb
        eb.event_bus.reset(log_dir=str(tmp_path))
        engine.current_tool_round = 90
        engine._check_guards()
        n_first = len([m for m in engine.history if m.get("role") == "user" and "轮次过半" in m.get("content", "")])
        engine.current_tool_round = 91
        engine._check_guards()
        engine.current_tool_round = 100
        engine._check_guards()
        n_total = len([m for m in engine.history if m.get("role") == "user" and "轮次过半" in m.get("content", "")])
        assert n_first == 1 and n_total == 1, "水位提示只发一次"

    def test_below_watermark_no_hint(self, engine, tmp_path):
        engine.current_tool_round = 89
        engine._check_guards()
        user_msgs = [m.get("content", "") for m in engine.history if m.get("role") == "user"]
        assert not any("轮次过半" in c for c in user_msgs)

    def test_watermark_scales_with_env(self, engine, monkeypatch, tmp_path):
        monkeypatch.setenv("BOBO_MAX_TOOL_ROUNDS", "100")
        from core import event_bus as eb
        eb.event_bus.reset(log_dir=str(tmp_path))
        engine.current_tool_round = 60  # 100 的 60%
        engine._check_guards()
        evs = _read_events(str(tmp_path / "events.jsonl"), "round.watermark")
        assert evs and evs[-1]["max"] == 100 and evs[-1]["watermark_round"] == 60


class TestLoopVerdict:
    """验收 2：撞 150 线死循环硬掐 / 在推进软着陆。"""

    def _stuck_history(self, engine):
        # 连续 5 轮完全相同模式（read_local_file 同参）
        for _ in range(5):
            engine.history.append(_tool_round([
                ("read_local_file", json.dumps({"filepath": "/tmp/x.py"})),
            ]))

    def _progressing_history(self, engine):
        # 5 轮不同工具 + 有写类工具（edit_file）→ 推进信号
        engine.history.append(_tool_round([("read_local_file", json.dumps({"filepath": "/a"}))]))
        engine.history.append(_tool_round([("grep_code", json.dumps({"pattern": "foo"}))]))
        engine.history.append(_tool_round([("edit_file", json.dumps({"file_path": "/a", "old_string": "x", "new_string": "y"}))]))
        engine.history.append(_tool_round([("list_directory", json.dumps({"path": "/b"}))]))
        engine.history.append(_tool_round([("execute_terminal", json.dumps({"command": "ls"}))]))

    def test_stuck_hard_stop(self, engine, monkeypatch, tmp_path):
        from core import event_bus as eb
        eb.event_bus.reset(log_dir=str(tmp_path))
        self._stuck_history(engine)
        engine.current_tool_round = 151
        assert engine._check_guards() is False  # 注入强制收尾后放行最后一轮
        user_msgs = [m.get("content", "") for m in engine.history if m.get("role") == "user"]
        assert any("强制收尾" in c and "死循环" in c for c in user_msgs), \
            f"stuck 应注入强制收尾指令，实际: {user_msgs}"
        evs = _read_events(str(tmp_path / "events.jsonl"), "loop.verdict")
        assert evs and evs[-1]["verdict"] == "stuck", f"event 应留 loop.verdict=stuck: {evs}"

    def test_progressing_soft_reminder(self, engine, monkeypatch, tmp_path):
        from core import event_bus as eb
        eb.event_bus.reset(log_dir=str(tmp_path))
        self._progressing_history(engine)
        engine.current_tool_round = 151
        assert engine._check_guards() is False
        user_msgs = [m.get("content", "") for m in engine.history if m.get("role") == "user"]
        assert any("长回合收尾阶段" in c and "整理台账" in c for c in user_msgs), \
            f"progressing 应注入温和收尾提醒，实际: {user_msgs}"
        assert not any("强制收尾" in c for c in user_msgs), "progressing 不得硬掐"
        evs = _read_events(str(tmp_path / "events.jsonl"), "loop.verdict")
        assert evs and evs[-1]["verdict"] == "progressing", f"event 应留 loop.verdict=progressing: {evs}"

    def test_zero_progress_also_stuck(self, engine, monkeypatch, tmp_path):
        """5 轮不同但纯读且无更早轮次 → 无推进信号 → stuck。"""
        from core import event_bus as eb
        eb.event_bus.reset(log_dir=str(tmp_path))
        for i in range(5):
            engine.history.append(_tool_round([
                ("read_local_file", json.dumps({"filepath": f"/tmp/f{i}"})),
            ]))
        engine.current_tool_round = 151
        engine._check_guards()
        evs = _read_events(str(tmp_path / "events.jsonl"), "loop.verdict")
        assert evs and evs[-1]["verdict"] == "stuck", \
            f"纯读无推进应 stuck: {evs}"

    def test_at_limit_no_verdict(self, engine, tmp_path):
        """恰在 150 线（未超）→ 不触发分流。"""
        engine.current_tool_round = 150
        engine._check_guards()
        user_msgs = [m.get("content", "") for m in engine.history if m.get("role") == "user"]
        assert not any("强制收尾" in c or "长回合收尾阶段" in c for c in user_msgs)


class TestMaxToolRoundsEnv:
    """验收 3：BOBO_MAX_TOOL_ROUNDS 默认 150 / 非法回退 / 合法生效。"""

    def test_default_150(self, engine, monkeypatch):
        monkeypatch.delenv("BOBO_MAX_TOOL_ROUNDS", raising=False)
        assert engine._max_tool_rounds() == 150

    def test_invalid_fallback_150(self, engine, monkeypatch):
        for bad in ("abc", "-5", "0", "150.5", "", "  "):
            monkeypatch.setenv("BOBO_MAX_TOOL_ROUNDS", bad)
            assert engine._max_tool_rounds() == 150, f"{bad!r} 应回退 150"

    def test_valid_takes_effect(self, engine, monkeypatch):
        monkeypatch.setenv("BOBO_MAX_TOOL_ROUNDS", "100")
        assert engine._max_tool_rounds() == 100
        monkeypatch.setenv("BOBO_MAX_TOOL_ROUNDS", "300")
        assert engine._max_tool_rounds() == 300


class TestIronRulesUntouched:
    """验收 4：200 深度硬断、500 步保险丝、收工闸语义不动。"""

    def test_depth_200_hard_break(self, engine):
        engine.current_depth = 201
        assert engine._check_guards() is True, ">200 深度硬断必须触发"
        assert engine.current_depth == 201

    def test_depth_200_boundary_not_break(self, engine):
        engine.current_depth = 200
        assert engine._check_guards() is False, "恰 200 不触发硬断"

    def test_max_steps_fuse_untouched(self, engine):
        assert engine.MAX_STEPS == 500, "500 步保险丝值不变"
