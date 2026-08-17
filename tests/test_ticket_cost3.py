"""票 COST-3 验收测试：工作锚点移位（不入 history）+ 工具集会话内稳定。

对应票据验收 c)：
  1. 锚点不入 history（压缩跳过 + 主路径后 history 均无 [工作锚点 消息）
  2. 锚点内容压缩后仍可得（_work_anchor 属性含当前任务/已写文件，压缩豁免语义）
  3. tools 数组跨轮字节稳定（_get_filtered_tools 不再被调用；tools_override == 全量 TOOLS_SCHEMA）
  4. 工具可用性全集不缩水（全量 schema 均在 override 中，owner 红线）
  5. work_anchor 注入 COST-2 尾部动态块（最后 user content 含 [工作锚点）
  6. 相邻两轮组装：历史区 user 消息逐字节稳定（动态块固化），动态块随轮刷新
"""

import pytest

from core.engine import Engine
from core.tool_executor import execute_tool
from core.event_bus import EventBus
from tests.mock_llm import MockLLMCaller, text_response
from tools import TOOLS_SCHEMA


def _fill_history(engine, n_pairs=20, long=False):
    for i in range(n_pairs):
        body = ("x" * 800) if long else ""
        engine.history.append({"role": "user", "content": f"Question {i} {body}"})
        engine.history.append({"role": "assistant", "content": f"Answer {i} {body}"})


def _mk_engine(caller, sid):
    """构造最小可用 Engine（test_mode）。"""
    eng = Engine(caller, execute_tool, test_mode=True)
    eng.sid = sid
    eng.tracker._change_log = [{"ts": 1, "desc": "a.py（write）", "path": "a.py"}]
    eng.task_ledger = [{"id": "1", "title": "COST-3 任务", "status": "pending"}]
    return eng


# ═══════════════════════════════════════════════════════════════════════
# ① 工作锚点移位：不入 history / 压缩豁免
# ═══════════════════════════════════════════════════════════════════════

class TestWorkAnchorMoved:

    def _patch_budget(self, monkeypatch):
        monkeypatch.setenv("BOBO_CONTEXT_BUDGET", "30")
        import core.context as ctx_module
        monkeypatch.setattr(ctx_module, "_get_msg_count_budget", lambda: 200)
        monkeypatch.setattr(ctx_module, "_get_context_budget", lambda _engine=None: 7000)

    def test_anchor_not_in_history_after_compress(self, monkeypatch, tmp_path):
        """金标准 1：正常压缩后锚点不入 history，_work_anchor 属性持有内容。"""
        self._patch_budget(monkeypatch)
        EventBus.reset(str(tmp_path / "ev1"))
        eng = _mk_engine(MockLLMCaller([text_response("x")]), "cost3-001")
        eng.current_user_input = "压缩锚点测试"
        _fill_history(eng, n_pairs=40, long=True)  # 80 条 × ~120 tokens ≈ 9.6K > 预算 8.4K → 主压缩路径
        eng._compressing = False
        eng._compressed_this_turn = False
        eng._compress_history()

        anchors = [m for m in eng.history
                   if m.get("role") == "system"
                   and str(m.get("content", "")).startswith("[工作锚点")]
        assert anchors == [], f"压缩后锚点不得留在 history（COST-3 移位）: {anchors}"
        assert getattr(eng, "_work_anchor", None), "压缩后 _work_anchor 属性应非空"
        content = eng._work_anchor["content"]
        assert "压缩锚点测试" in content, "锚点应含当前任务"
        assert "a.py" in content, "锚点应含已写文件"

    def test_anchor_survives_skip_path(self, monkeypatch, tmp_path):
        """金标准 1b：compress_skipped 分支同样刷新属性锚点（锚点内容不因压缩丢失）。"""
        self._patch_budget(monkeypatch)
        EventBus.reset(str(tmp_path / "ev2"))
        eng = _mk_engine(MockLLMCaller([text_response("x")]), "cost3-002")
        eng.current_user_input = "跳过路径任务"
        # 60 条长消息 ≈ 7.2K tokens > 预算 7K（触发压缩评估），但层0 上限 15K 全装
        # → archivable = 0 < 15% → 走 compress_skipped 跳过路径
        _fill_history(eng, n_pairs=30, long=True)
        eng._compressing = False
        eng._compressed_this_turn = False
        eng._compress_history()

        assert getattr(eng, "_work_anchor", None), "跳过路径也应刷新 _work_anchor"
        assert "跳过路径任务" in eng._work_anchor["content"]
        anchors = [m for m in eng.history
                   if m.get("role") == "system"
                   and str(m.get("content", "")).startswith("[工作锚点")]
        assert anchors == [], "跳过路径锚点也不得留在 history"

    def test_injector_injects_work_anchor_tail_block(self, monkeypatch, tmp_path):
        """金标准 2：work_anchor 随 COST-2 动态块注入最后 user content 前部。"""
        self._patch_budget(monkeypatch)
        EventBus.reset(str(tmp_path / "ev3"))
        eng = _mk_engine(MockLLMCaller([text_response("x")]), "cost3-003")
        eng.history = [{"role": "user", "content": "第一轮问题"},
                       {"role": "assistant", "content": "第一轮回答"}]
        eng.current_user_input = "当前任务 X"
        msgs = eng.injector.build_messages(
            system_prompt="You are Bobo.",
            user_input="当前任务 X",
            tools_schema=TOOLS_SCHEMA,
            extra_categories=set(),
            session_id="cost3-003",
        )
        last_user = next((m for m in reversed(msgs) if m.get("role") == "user"), None)
        assert last_user is not None, "应有最后 user 消息"
        content = str(last_user.get("content", ""))
        assert "[工作锚点" in content, "work_anchor 应注入最后 user 的动态块"
        assert "当前任务 X" in content, "锚点应含当前任务"
        assert "COST-2 动态块" in content, "应走 COST-2 动态块机制"

    def test_history_stable_across_rounds(self, monkeypatch, tmp_path):
        """金标准 3：相邻两轮——R1 的 user（含动态块）逐字节出现在 R2 历史区。"""
        self._patch_budget(monkeypatch)
        EventBus.reset(str(tmp_path / "ev4"))
        eng = _mk_engine(MockLLMCaller([text_response("a1"), text_response("a2")]), "cost3-004")
        eng.tracker._change_log = []

        eng.history = []
        # 真实流程：本轮输入先 append 进 history，再组装（动态块附加后写回共享引用）
        eng.history.append({"role": "user", "content": "R1 输入"})
        eng.current_user_input = "R1 输入"
        msgs1 = eng.injector.build_messages(
            system_prompt="You are Bobo.", user_input="R1 输入",
            tools_schema=TOOLS_SCHEMA, extra_categories=set(), session_id="cost3-004")
        # 模拟 R1 轮固化：assistant 回复 + 下一轮输入
        eng.history.append({"role": "assistant", "content": "a1"})
        eng.history.append({"role": "user", "content": "R2 输入"})
        eng.current_user_input = "R2 输入"
        msgs2 = eng.injector.build_messages(
            system_prompt="You are Bobo.", user_input="R2 输入",
            tools_schema=TOOLS_SCHEMA, extra_categories=set(), session_id="cost3-004")

        # R1 组装时最后 user（R1u，含动态块1）应被 R2 历史区原样携带
        r1_last_user = next((m for m in reversed(msgs1) if m.get("role") == "user"), None)
        r2_users = [m for m in msgs2 if m.get("role") == "user"]
        assert len(r2_users) >= 2, "R2 组装应含历史 user + 本轮 user"
        assert r2_users[0]["content"] == r1_last_user["content"], \
            "R1 的 user（含动态块1）应逐字节出现在 R2 历史区（前缀稳定）"
        assert "R1 输入" in str(r2_users[0]["content"]), "动态块1 应含 R1 输入"
        assert "R2 输入" in str(r2_users[-1]["content"]), "R2 动态块应随轮刷新"


# ═══════════════════════════════════════════════════════════════════════
# ② 工具集会话内稳定
# ═══════════════════════════════════════════════════════════════════════

class TestToolsStable:

    def _patch_budget(self, monkeypatch):
        import core.context as ctx_module
        monkeypatch.setattr(ctx_module, "_get_msg_count_budget", lambda: 200)
        monkeypatch.setattr(ctx_module, "_get_context_budget", lambda _engine=None: 7000)

    def test_override_full_schema_and_no_filter_call(self, monkeypatch, tmp_path):
        """tools_override == 全量 TOOLS_SCHEMA；_get_filtered_tools 不再被调用。"""
        self._patch_budget(monkeypatch)
        EventBus.reset(str(tmp_path / "ev5"))
        captured = {}

        class RecordingCaller(MockLLMCaller):
            def __call__(self, messages, use_tools=True, stream_callback=None,
                         retry_callback=None, tools_override=None, **kwargs):
                captured["tools_override"] = tools_override
                return {"choices": [{"message": {"content": "ok"}}]}

        eng = _mk_engine(RecordingCaller([]), "cost3-005")
        eng.tracker._change_log = []
        eng.task_ledger = []

        calls = {"n": 0}
        orig = eng._get_filtered_tools

        def spy(*a, **k):
            calls["n"] += 1
            return orig(*a, **k)

        eng._get_filtered_tools = spy
        eng.run("测试工具稳定性", depth=0)

        assert calls["n"] == 0, \
            f"_get_filtered_tools 被调用 {calls['n']} 次（COST-3 应固定全量，不再按分类过滤）"
        ov = captured.get("tools_override")
        assert ov == TOOLS_SCHEMA, f"tools_override 应为全量 TOOLS_SCHEMA，实际 {len(ov or [])} 个"
        names = [t["function"]["name"] for t in ov]
        full_names = [t["function"]["name"] for t in TOOLS_SCHEMA]
        assert names == full_names, "工具可用性全集不得缩水（顺序亦须一致）"
        assert len(names) == len(TOOLS_SCHEMA)
