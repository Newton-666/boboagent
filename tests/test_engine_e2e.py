"""Engine 状态机端到端测试台 — feat/engine-e2e-harness

零真实依赖：假 LLM caller + 假工具执行器驱动完整 Engine.run() 回合。
覆盖五场景：简单问答、工具回合、错误恢复、中途 kill 模拟、多轮连续。
"""

import pytest

# ── 假组件 ──────────────────────────────────────────────────────────


class FakeLLMCaller:
    """预编程响应队列，模拟真实 llm_caller 返回协议。

    响应格式：
    - 正常文本: {"choices": [{"message": {"content": "hello"}}], "usage": {}}
    - 工具调用: {"choices": [{"message": {"content": None, "tool_calls": [...]}}], "usage": {}}
    - 错误: {"error": "...", "error_type": "...", "retryable": False}
    """

    def __init__(self, responses: list):
        self.responses = list(responses)
        self.calls: list[dict] = []
        self.call_count = 0

    def __call__(self, messages, stream_callback=None, retry_callback=None, tools_override=None, **kwargs):
        self.call_count += 1
        self.calls.append({
            "messages": list(messages),
            "tools_override": tools_override,
        })
        if self.call_count > len(self.responses):
            # 默认兜底：文本结束
            return {"choices": [{"message": {"content": "done"}}], "usage": {}}
        resp = self.responses[self.call_count - 1]
        if isinstance(resp, dict) and "error" in resp:
            return resp
        if isinstance(resp, tuple):
            content, tool_calls = resp
            return {
                "choices": [{"message": {"content": content, "tool_calls": tool_calls}}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10},
            }
        return resp


def _make_tool_call(tc_id: str, name: str, args: dict = None) -> dict:
    """构建单个 tool_call dict（OpenAI 格式）。"""
    import json
    return {
        "id": tc_id,
        "type": "function",
        "function": {
            "name": name,
            "arguments": json.dumps(args or {}),
        },
    }


class FakeToolExecutor:
    """假工具执行器：白名单工具，记录每次调用。

    返回格式为 _execute_tool_loop 可用的原始字符串。
    """

    def __init__(self, responses: dict = None):
        self.responses = responses or {}
        self.calls: list[tuple] = []

    def __call__(self, tool_name: str, args: dict) -> str:
        self.calls.append((tool_name, args))
        if tool_name in self.responses:
            return self.responses[tool_name]
        return f"[fake result of {tool_name}: {args}]"


# ── 辅助函数 ────────────────────────────────────────────────────────


def _make_test_engine(llm_caller, tool_executor=None, monkeypatch=None):
    """创建零外部依赖的 Engine 实例。

    核心：注入假 llm_caller 和假 tool_executor。
    还需 monkeypatch PromptInjector.build_messages 以避免 v5_memory 等
    磁盘/网络依赖在 _call_llm 注入阶段被触发。
    """
    import core.engine as engine_mod

    # 1. 轻量 system prompt，避免 _build_system_prompt 走完整工具扫描
    monkeypatch.setattr(engine_mod.Engine, "_build_system_prompt", lambda self: "You are a helpful assistant.")

    # 2. 构造 Engine
    engine = engine_mod.Engine(
        llm_caller=llm_caller,
        tool_executor=tool_executor,
        test_mode=True,
    )

    # 3. 替换 injector.build_messages 为最小实现
    def _fake_build_messages(system_prompt, user_input, tools_schema, extra_categories, session_id=""):
        msgs = [
            {"role": "system", "content": system_prompt},
        ]
        # 只在存在 history 时附加
        if engine.history:
            msgs.extend(engine.history)
        return msgs

    monkeypatch.setattr(engine.injector, "build_messages", _fake_build_messages)

    # 4. 禁用 proactive（避免访问 memory）
    monkeypatch.setattr(engine.proactive, "inject_context", lambda msgs: msgs)
    monkeypatch.setattr(engine.proactive, "mode", "off")

    # 5. 禁用 skill_loader（避免扫描 skill-standards 目录）
    monkeypatch.setattr(engine.skill_loader, "load_standards", lambda: [])

    # 6. 禁用 verifier（避免额外 LLM 调用）
    engine.verifier.check_and_inject = lambda *a, **kw: False

    # 7. 抑制 spawn_worker 提醒系统消息注入（_call_llm 在 _step_count >= 1 时触发）
    engine._worker_reminded = True
    # 同时确保 _check_guards 不注入额外内容
    monkeypatch.setattr(engine, "_check_guards", lambda: False)

    return engine


def _collect_states(engine):
    """包装 _step 以记录每次 _step 调用后的状态序列。"""
    original_step = engine._step
    states = []

    def tracking_step():
        original_step()
        states.append(engine.state)

    engine._step = tracking_step
    return states


# ══════════════════════════════════════════════════════════════════════
# 场景测试
# ══════════════════════════════════════════════════════════════════════


class TestEmptyResponse:
    """场景 f：THINKING 内部重试 — 空响应重试 1 次 / 2 次兜底。"""

    def test_empty_response_retry_once(self, monkeypatch):
        """THINKING→THINKING 重试：空 content 无 tool_calls → 重试 1 次后正常。"""
        fake_llm = FakeLLMCaller([
            ("", None),        # 空响应，触发重试
            ("ok after retry", None),
        ])
        fake_tools = FakeToolExecutor()
        engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)

        states = _collect_states(engine)
        engine.run(user_input="test")

        assert engine.state == engine.STATE_DONE

        # THINKING 出现两次（第一次空→重试，第二次正常）
        seq = [s for s in states if s != engine.STATE_IDLE]
        ti = [s for s in seq if s == engine.STATE_THINKING]
        assert len(ti) == 2, f"expected 2 THINKING (retry), got: {seq}"

    def test_empty_response_twice_gives_fallback(self, monkeypatch):
        """两次空响应 → RESPONDING 兜底错误消息。"""
        # 3 个响应：两次空触发重试到 current_depth=2，
        # 第三次 _call_llm 被调用（因 current_depth=2 不满足 <2
        # 条件但在此之前已调用了 _call_llm）
        fake_llm = FakeLLMCaller([
            ("", None),   # 空 1 → depth: 0, retry
            ("", None),   # 空 2 → depth: 1, retry
            ("", None),   # 空 3 → 此时 depth=2, 不满足 <2, 但 _call_llm 已在 depth check 前被调用
        ])
        fake_tools = FakeToolExecutor()
        engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)
        engine.run(user_input="test")

        assert engine.state == engine.STATE_DONE
        asst = [m for m in engine.history if m.get("role") == "assistant"]
        assert len(asst) >= 1
        # 兜底错误消息包含"空响应"
        assert "空响应" in asst[-1].get("content", "")


class TestSimpleQA:
    """场景 a：简单问答 — 单轮文本进 → STATE_DONE，history 结构正确。"""

    def test_single_text_round(self, monkeypatch):
        fake_llm = FakeLLMCaller([
            ("你好！我是 Bobo。", None),  # 文本响应，无 tool_calls
        ])
        fake_tools = FakeToolExecutor()
        engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)

        states = _collect_states(engine)
        engine.run(user_input="hello")

        assert engine.state == engine.STATE_DONE
        assert fake_llm.call_count == 1

        # 状态序列精确断言：IDLE → THINKING → RESPONDING → DONE
        # 除 IDLE 外的序列必须严格固定（纯文本轮不会有 EXECUTING）
        seq = [s for s in states if s != engine.STATE_IDLE]
        assert seq == [
            engine.STATE_THINKING,
            engine.STATE_RESPONDING,
            engine.STATE_DONE,
        ], f"unexpected state sequence: {seq}"

        # history 结构：user + assistant
        roles = [m["role"] for m in engine.history]
        assert roles == ["user", "assistant"]
        assert engine.history[0]["content"] == "hello"
        assert engine.history[1]["content"] == "你好！我是 Bobo。"

    def test_single_text_round_no_input(self, monkeypatch):
        """空输入场景 — 不 crash。"""
        fake_llm = FakeLLMCaller([
            ("我准备好了。", None),
        ])
        fake_tools = FakeToolExecutor()
        engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)

        engine.run(user_input="")

        assert engine.state == engine.STATE_DONE
        assert len(engine.history) >= 1  # 至少 assistant 回复


class TestToolRound:
    """场景 b：工具回合 — 完整走 THINKING→EXECUTING→THINKING→RESPONDING→DONE。"""

    def test_tool_round_state_sequence(self, monkeypatch):
        fake_llm = FakeLLMCaller([
            # 第 1 轮：发 tool_calls
            (None, [_make_tool_call("call_1", "echo", {"msg": "ping"})]),
            # 第 2 轮：最终文本
            ("工具执行完成，结果: pong", None),
        ])
        fake_tools = FakeToolExecutor({
            "echo": "pong",
        })
        engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)

        states = _collect_states(engine)
        engine.run(user_input="ping")

        assert engine.state == engine.STATE_DONE

        # 状态转换序列断言：IDLE→THINKING→EXECUTING→THINKING→RESPONDING→DONE
        assert engine.STATE_THINKING in states
        assert engine.STATE_EXECUTING in states
        assert engine.STATE_RESPONDING in states
        assert states[-1] == engine.STATE_DONE

        # 验证完整序列顺序
        seq = [s for s in states if s != engine.STATE_IDLE]
        # 期望: THINKING, EXECUTING, THINKING, RESPONDING, DONE
        assert seq[0] == engine.STATE_THINKING, f"expected THINKING first, got {seq}"
        assert engine.STATE_EXECUTING in seq
        assert engine.STATE_RESPONDING in seq
        # EXECUTING 出现在两个 THINKING 之间
        ti = [i for i, s in enumerate(seq) if s == engine.STATE_THINKING]
        ei = seq.index(engine.STATE_EXECUTING)
        assert ti[0] < ei < ti[1], f"EXECUTING ({ei}) should be between THINKING {ti}"

    def test_tool_round_history_pairing(self, monkeypatch):
        fake_llm = FakeLLMCaller([
            (None, [_make_tool_call("call_a", "add", {"x": 1, "y": 2})]),
            ("结果是 3", None),
        ])
        fake_tools = FakeToolExecutor({
            "add": "3",
        })
        engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)
        engine.run(user_input="1+2")

        # assistant tool_calls 与 tool 结果正确配对
        asst_msgs = [m for m in engine.history if m.get("role") == "assistant" and m.get("tool_calls")]
        tool_msgs = [m for m in engine.history if m.get("role") == "tool"]

        assert len(asst_msgs) == 1
        assert len(tool_msgs) == 1
        assert asst_msgs[0]["tool_calls"][0]["id"] == tool_msgs[0]["tool_call_id"]
        # tool 结果包含 content（标准格式无 name 字段）

    def test_multi_tool_calls_in_one_round(self, monkeypatch):
        """同一轮多个 tool_calls — 全部执行并正确配对。"""
        fake_llm = FakeLLMCaller([
            (
                None,
                [
                    _make_tool_call("tc1", "echo", {"msg": "a"}),
                    _make_tool_call("tc2", "echo", {"msg": "b"}),
                ],
            ),
            ("got a and b", None),
        ])
        fake_tools = FakeToolExecutor({
            "echo": "ok",
        })
        engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)
        engine.run(user_input="test multi")

        tool_msgs = [m for m in engine.history if m.get("role") == "tool"]
        assert len(tool_msgs) == 2
        tool_ids = {m["tool_call_id"] for m in tool_msgs}
        assert tool_ids == {"tc1", "tc2"}

        # fake_tools 被调用了两次
        assert len(fake_tools.calls) == 2


class TestErrorRecovery:
    """场景 c：错误恢复 — caller 返回 error → ERROR → 下一轮恢复正常。"""

    def test_error_then_recovery(self, monkeypatch):
        """非重试错误：_call_llm 设 STATE_ERROR 后被 _step 覆写为 RESPONDING→DONE，
        错误以文本形式进入 history。下一轮正常恢复。"""
        fake_llm = FakeLLMCaller([
            {"error": "API 500", "error_type": "server_error", "retryable": False},
        ])
        fake_tools = FakeToolExecutor()
        engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)

        # 第一轮：收到非重试错误 → 进入 RESPONDING→DONE，错误写入 history
        engine.run(user_input="crash me")
        assert engine.state == engine.STATE_DONE
        assert fake_llm.call_count == 1
        # 错误以文本形式出现在 assistant 回复中
        asst_msgs = [m for m in engine.history if m.get("role") == "assistant"]
        assert len(asst_msgs) >= 1
        assert "API 500" in asst_msgs[-1].get("content", "")

        # 第二轮：换新 caller，正常响应
        engine.llm_caller = FakeLLMCaller([
            ("恢复了！", None),
        ])
        engine.run(user_input="recover")
        assert engine.state == engine.STATE_DONE
        assert engine.history[-1]["content"] == "恢复了！"

    def test_retryable_error_does_not_set_error_state(self, monkeypatch):
        """retryable 错误不应设 ERROR 状态（caller 自己重试）。"""
        # retryable error — engine 不应 set state to ERROR
        fake_llm = FakeLLMCaller([
            {"error": "rate limit", "error_type": "rate_limit", "retryable": True},
        ])
        fake_tools = FakeToolExecutor()
        engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)

        engine.run(user_input="test")
        # retryable 错误：engine 返回 error_msg 但 state 不变 ERROR
        # 实际上是 _call_llm 返回 (error_msg, [])，没有 tool_calls，
        # 进入 RESPONDING → DONE
        # 但 error_msg 不为空 string，所以 history 中 assistant 会有错误消息
        assert engine.state == engine.STATE_DONE
        # history 中 assistant 回复包含错误信息
        asst_content = engine.history[-1].get("content", "")
        assert "rate limit" in asst_content


class TestKillSimulation:
    """场景 d：中途 kill 模拟 — 孤儿产生 → 清洗 → 合法。

    模拟崩溃时的历史状态：assistant tool_calls 已入 history，
    tool 结果丢失。这是 crash 案的回归测试。
    """

    def test_orphan_produced_then_cleaned(self, monkeypatch):
        from core.context import clean_orphan_tool_calls

        # 先正常跑一轮工具回合
        fake_llm = FakeLLMCaller([
            (None, [_make_tool_call("call_ok", "echo", {"msg": "hi"})]),
            ("done", None),
        ])
        fake_tools = FakeToolExecutor({"echo": "result"})
        engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)
        engine.run(user_input="go")

        # 此时 history 有完整的 user → assistant(tool_calls) → tool → assistant(text)
        # 现在注入孤儿：手动添加一个 assistant 带 tool_calls 但没有 tool 结果，
        # 模拟崩溃时历史持久化状态（assistant 发了 tool_calls，结果丢失）
        engine.history.append({
            "role": "assistant",
            "content": None,
            "tool_calls": [
                _make_tool_call("orphan_1", "web_search", {"q": "test"}),
                _make_tool_call("orphan_2", "read_file", {"path": "/x"}),
            ],
        })
        # 再加一个游离 tool 消息（无对应 assistant tool_calls）
        engine.history.append({
            "role": "tool",
            "tool_call_id": "stray_99",
            "content": "stray result with no assistant",
        })

        # 清洗前确认有孤儿
        asst_with_tc = [m for m in engine.history if m.get("role") == "assistant" and m.get("tool_calls")]
        tool_msgs_before = [m for m in engine.history if m.get("role") == "tool"]
        orphan_asst = [m for m in asst_with_tc if any(
            tc["id"] not in {t["tool_call_id"] for t in tool_msgs_before}
            for tc in m.get("tool_calls", [])
        )]
        assert len(orphan_asst) >= 1, "注入孤儿失败：缺少无配对 tool 结果的 assistant"

        # 清洗
        cleaned, report = clean_orphan_tool_calls(engine.history)

        assert report["inserted"] == 2  # orphan_1 + orphan_2 占位
        assert report["removed"] == 1   # stray_99 删除

        # 清洗后：每个 assistant tool_call 都有配对 tool 结果
        cleaned_tool_ids = {m["tool_call_id"] for m in cleaned if m.get("role") == "tool"}
        for m in cleaned:
            if m.get("role") == "assistant" and m.get("tool_calls"):
                for tc in m["tool_calls"]:
                    assert tc["id"] in cleaned_tool_ids, (
                        f"tool_call {tc['id']} 在清洗后仍无配对 tool 结果"
                    )

        # 占位 tool 消息内容
        placeholder = [m for m in cleaned if m.get("tool_call_id") == "orphan_1"]
        assert len(placeholder) == 1
        assert placeholder[0]["content"] == "[工具结果因中断丢失]"
        assert placeholder[0]["name"] == "web_search"

    def test_clean_history_after_orphan_cleaning_is_api_safe(self, monkeypatch):
        """清洗后的 history 可安全发给 API（结构合法）。"""
        from core.context import clean_orphan_tool_calls

        fake_llm = FakeLLMCaller([
            (None, [_make_tool_call("call_x", "echo", {})]),
            ("final", None),
        ])
        fake_tools = FakeToolExecutor({"echo": "ok"})
        engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)
        engine.run(user_input="test")

        # 注入孤儿
        engine.history.append({
            "role": "assistant",
            "content": None,
            "tool_calls": [_make_tool_call("orphan_z", "crash_tool", {})],
        })

        cleaned, _ = clean_orphan_tool_calls(engine.history)

        # API 结构合法性验证：
        # 1. 不存在游离 tool 消息
        asst_tc_ids = set()
        for m in cleaned:
            if isinstance(m, dict) and m.get("role") == "assistant" and m.get("tool_calls"):
                for tc in m["tool_calls"]:
                    asst_tc_ids.add(tc.get("id", ""))
        for m in cleaned:
            if isinstance(m, dict) and m.get("role") == "tool":
                assert m["tool_call_id"] in asst_tc_ids, (
                    f"游离 tool 消息: {m['tool_call_id']}"
                )

        # 2. 每个 assistant tool_call 都有配对
        tool_ids_in_cleaned = {m["tool_call_id"] for m in cleaned if m.get("role") == "tool"}
        for tc_id in asst_tc_ids:
            assert tc_id in tool_ids_in_cleaned, f"孤儿 tool_call: {tc_id}"

    def test_real_interrupt_in_executing_phase(self, monkeypatch):
        """真实 EXECUTING 中断模拟：拦截 _append_to_history("tool", ...)
        模拟"助理 tool_calls 已持久化但 tool 结果写入前崩溃"。

        与手动注入版本不同：本测试在 engine._step 内 EXECUTING 分支
        的真实执行路径中触发中断，验证中断后的完整恢复链路。
        """
        from core.context import clean_orphan_tool_calls

        fake_llm = FakeLLMCaller([
            (None, [_make_tool_call("c_int", "echo", {"msg": "ping"})]),
            ("恢复后的最终回复", None),
        ])
        fake_tools = FakeToolExecutor({"echo": "pong"})
        engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)

        # Monkeypatch _append_to_history：拦截 "tool" 角色写入，
        # 模拟崩溃——assistant 已入 history，tool 结果丢失
        original_append = engine._append_to_history
        tool_blocked = []

        def crash_append(role, content=None, tool_calls=None, tool_results=None, thinking=None):  # thinking: F8 新增 kwargs，桩签名对齐
            if role == "tool":
                tool_blocked.append({"results": tool_results})
                return  # 模拟崩溃：tool 结果丢弃
            return original_append(role, content=content, tool_calls=tool_calls, tool_results=tool_results)

        monkeypatch.setattr(engine, "_append_to_history", crash_append)

        engine.run(user_input="ping")

        # 确认 tool executor 确实执行了
        assert len(fake_tools.calls) == 1
        assert fake_tools.calls[0] == ("echo", {"msg": "ping"})

        # 确认孤儿存在：assistant tool_calls 入 history，tool 结果未入
        asst_with_tc = [m for m in engine.history if m.get("role") == "assistant" and m.get("tool_calls")]
        tool_msgs = [m for m in engine.history if m.get("role") == "tool"]
        assert len(asst_with_tc) >= 1
        assert len(tool_msgs) == 0, "tool 结果应该被拦截为 0 条"

        # 恢复链路：清洗 history
        cleaned, report = clean_orphan_tool_calls(engine.history)
        assert report["inserted"] >= 1  # c_int 占位
        assert report["removed"] == 0   # 无游离 tool

        # 清洗后 history 结构合法
        cleaned_tool_ids = {m["tool_call_id"] for m in cleaned if m.get("role") == "tool"}
        for m in cleaned:
            if m.get("role") == "assistant" and m.get("tool_calls"):
                for tc in m["tool_calls"]:
                    assert tc["id"] in cleaned_tool_ids, f"tool_call {tc['id']} 清洗后仍无配对"

        placeholder = [m for m in cleaned if m.get("tool_call_id") == "c_int"]
        assert len(placeholder) == 1
        assert placeholder[0]["content"] == "[工具结果因中断丢失]"

        # 关键验证：engine 状态一致，无残留
        assert engine.state == engine.STATE_DONE
        # _pending_tool_calls 在 EXECUTING 完成后被清空为 None 或 []
        assert not engine._pending_tool_calls, f"expected empty, got {engine._pending_tool_calls}"
        assert engine._pending_content is None


class TestMultiTurn:
    """场景 e：多轮连续 — 3 轮对话后 history 长度与结构正确。"""

    def test_three_turns_history_integrity(self, monkeypatch):
        fake_llm = FakeLLMCaller([
            ("第一轮回复", None),
            ("第二轮回复", None),
            ("第三轮回复", None),
        ])
        fake_tools = FakeToolExecutor()
        engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)

        engine.run(user_input="turn 1")
        assert engine.state == engine.STATE_DONE

        engine.run(user_input="turn 2")
        assert engine.state == engine.STATE_DONE

        engine.run(user_input="turn 3")
        assert engine.state == engine.STATE_DONE

        # history 结构：user, assistant, user, assistant, user, assistant
        roles = [m["role"] for m in engine.history]
        assert roles == ["user", "assistant", "user", "assistant", "user", "assistant"]

        # 内容完整，无丢失
        user_msgs = [m["content"] for m in engine.history if m["role"] == "user"]
        assert user_msgs == ["turn 1", "turn 2", "turn 3"]

    def test_multi_turn_with_tools(self, monkeypatch):
        """3 轮中混合文本轮和工具轮。"""
        fake_llm = FakeLLMCaller([
            # 轮 1: 文本
            ("hello", None),
            # 轮 2: 工具
            (None, [_make_tool_call("c1", "echo", {"m": "x"})]),
            ("got x", None),
            # 轮 3: 文本
            ("bye", None),
        ])
        fake_tools = FakeToolExecutor({"echo": "x_result"})
        engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)

        engine.run(user_input="hi")
        # 设台账避免无账闸误拦（本轮有工具调用但无台账）
        engine.task_ledger = [{"id": "1", "title": "multi-turn", "status": "done"}]
        engine.run(user_input="echo x")
        engine.run(user_input="bye")

        roles = [m["role"] for m in engine.history]
        # user, assistant, user, assistant(tool_calls), tool, assistant, user, assistant
        assert roles == [
            "user", "assistant",          # round 1
            "user", "assistant", "tool", "assistant",  # round 2 (tool)
            "user", "assistant",          # round 3
        ]

        # 无消息丢失
        assert len(engine.history) == 8

        # 工具结果正确
        tool_msgs = [m for m in engine.history if m.get("role") == "tool"]
        assert len(tool_msgs) == 1
        assert tool_msgs[0]["content"] == "x_result"

    def test_engine_reset_between_runs_preserves_history(self, monkeypatch):
        """run() 之间不 reset，history 累积。"""
        fake_llm = FakeLLMCaller([
            ("first", None),
            ("second", None),
        ])
        fake_tools = FakeToolExecutor()
        engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)

        engine.run(user_input="q1")
        engine.run(user_input="q2")

        # 4 条消息：user, asst, user, asst
        assert len(engine.history) == 4

        # reset 后清空
        engine.reset()
        assert engine.history == []


class TestStateMachineEdgeCases:
    """L3B 审查补充：遗漏的状态转换覆盖。"""

    def test_max_steps_protection(self, monkeypatch):
        """步数超过 MAX_STEPS → break → STATE_RESPONDING（不入 DONE，因为 break 跳过了 _step() 的 RESPONDING→DONE）。"""
        responses = [("looping", None)] * 100
        fake_llm = FakeLLMCaller(responses)
        fake_tools = FakeToolExecutor()
        engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)
        engine.MAX_STEPS = 2  # 第 3 步时 _step_count=3 > 2，触发 break

        engine.run(user_input="test")
        # break 后 state 为 RESPONDING（run() line 805-806: self.state = RESPONDING; break）
        assert engine.state in (engine.STATE_RESPONDING, engine.STATE_DONE)
        assert engine._step_count > engine.MAX_STEPS

    def test_nonretryable_error_state_error_is_dead(self, monkeypatch):
        """文档化 STATE_ERROR 死状态。

        _call_llm 设置 self.state = STATE_ERROR → 返回 (error_msg, [])。
        THINKING 分支因 error_msg 非空走到 else 分支，执行
        self.state = STATE_RESPONDING，覆盖了 STATE_ERROR。

        run() 循环终止条件 while state not in (DONE, ERROR) 中的
        ERROR 分支不会被非重试错误触发。
        """
        fake_llm = FakeLLMCaller([
            {"error": "auth failed", "error_type": "auth", "retryable": False},
        ])
        fake_tools = FakeToolExecutor()
        engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)

        states = _collect_states(engine)
        engine.run(user_input="should not crash")

        # STATE_ERROR 从未出现在状态序列中（被覆盖了）
        assert engine.STATE_ERROR not in states, (
            f"STATE_ERROR should be dead（被 RESPONDING 覆盖），实际 states={states}"
        )
        assert engine.state == engine.STATE_DONE
        # 错误以文本形式进入 assistant history
        asst = [m for m in engine.history if m.get("role") == "assistant"]
        assert any("auth failed" in m.get("content", "") for m in asst)

    def test_run_level_interrupt_sets_error(self, monkeypatch):
        """run() 主循环中 _interrupt_event.is_set() → STATE_ERROR。"""
        import threading
        fake_llm = FakeLLMCaller([
            ("reply", None),
        ])
        fake_tools = FakeToolExecutor()
        engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)

        # 在 _step 执行前设置中断信号
        engine._interrupt_event = threading.Event()
        engine._interrupt_event.set()

        engine.run(user_input="test")
        assert engine.state == engine.STATE_ERROR

    def test_step_level_interrupt_sets_error(self, monkeypatch):
        """_step() 入口 _interrupt_event.is_set() → STATE_ERROR。

        关键：中断必须在 _step() 执行**期间**注入（如在 _call_llm 内部 set），
        而非 _step() 返回后（那会被 run() 循环捕获，走 run 级中断）。
        """
        import threading
        fake_llm = FakeLLMCaller([
            ("reply", None),
        ])
        fake_tools = FakeToolExecutor()
        engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)

        engine._interrupt_event = threading.Event()

        # 注入 _call_llm 的 monkeypatch：在执行时设置中断信号
        # 这样第二次 _step() 调用时（第一轮 THINKING→RESPONDING→DONE 结束后
        # 的下一轮 IDLE→THINKING），_step 入口会检测到中断
        original_call_llm = engine._call_llm
        call_count = 0

        def instrumented_call_llm():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # 第一次 _call_llm 执行期间设置中断——这模拟的是：
                # 在 _step 执行期间（THINKING 分支的 _call_llm 调用内），
                # 中断信号到达。第一次 _step() 会正常走完（因为 _step 入口
                # 检测在 _call_llm 之前），但第二次 _step() 入口会检测到。
                # ref: engine.py line 601-603
                engine._interrupt_event.set()
            return original_call_llm()

        monkeypatch.setattr(engine, "_call_llm", instrumented_call_llm)

        engine.run(user_input="test")
        # 中断被 _step() 入口捕获 → STATE_ERROR
        assert engine.state == engine.STATE_ERROR
        assert call_count == 1


class TestEngineConstruction:
    """验证 Engine 在测试模式下正确构造且零外部依赖。"""

    def test_engine_constructs_in_test_mode(self, monkeypatch):
        fake_llm = FakeLLMCaller([])
        fake_tools = FakeToolExecutor()
        engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)

        assert engine.test_mode is True
        assert engine.state == engine.STATE_IDLE
        assert engine.history == []

    def test_engine_can_run_multiple_times_with_same_instance(self, monkeypatch):
        fake_llm = FakeLLMCaller([
            ("a", None),
            ("b", None),
            ("c", None),
        ])
        fake_tools = FakeToolExecutor()
        engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)

        for i in range(3):
            engine.run(user_input=f"q{i}")
            assert engine.state == engine.STATE_DONE

        assert fake_llm.call_count == 3


class TestFakeLLMCaller:
    """验证 FakeLLMCaller 自身行为正确。"""

    def test_returns_text_response(self):
        caller = FakeLLMCaller([("hello", None)])
        resp = caller([])
        assert resp["choices"][0]["message"]["content"] == "hello"
        assert resp["choices"][0]["message"].get("tool_calls") is None

    def test_returns_tool_calls_response(self):
        tc = _make_tool_call("id1", "echo", {"msg": "hi"})
        caller = FakeLLMCaller([(None, [tc])])
        resp = caller([])
        msg = resp["choices"][0]["message"]
        assert msg["content"] is None
        assert len(msg["tool_calls"]) == 1
        assert msg["tool_calls"][0]["id"] == "id1"

    def test_returns_error_response(self):
        err = {"error": "boom", "error_type": "fatal", "retryable": False}
        caller = FakeLLMCaller([err])
        resp = caller([])
        assert resp["error"] == "boom"

    def test_default_fallback(self):
        caller = FakeLLMCaller([])
        resp = caller([])
        assert resp["choices"][0]["message"]["content"] == "done"
