"""票 AUTO-E2：ESC 随时硬中断——运行中命令可杀。

验收口径（E2-3 钉死）：
  1. sleep 30 运行中触发中断 → 2s 内进程死亡、结果含"已被用户中断"、事件留痕
  2. 中断后说"继续" → session 进度完整（复用 E-1 测试范式，本文件做 engine 级验证）
  3. 中断的命令不被自动重试（断言中断后引擎不再发起同一 execute_terminal）
  4. 正常执行路径零变化：命令正常跑完时行为与现状一致
"""

import threading
import time

from tools.execute_terminal import execute


class TestInterruptKillsRunningCommand:
    """E2-3 单元层：execute_terminal 内部可中断。"""

    def test_interrupt_kills_sleep_within_2s(self):
        """ESC 中断 → 2s 内进程死亡、结果含中断标注。"""
        ev = threading.Event()
        t0 = time.time()

        def _delayed_set():
            time.sleep(0.5)
            ev.set()

        threading.Thread(target=_delayed_set, daemon=True).start()
        result = execute("sleep 30", timeout=30, _interrupt_event=ev)
        elapsed = time.time() - t0

        assert "已被用户中断" in result, result
        assert "ESC" in result
        assert elapsed < 2.0, f"ESC → 进程死亡应 ≤2s，实际 {elapsed:.2f}s"

    def test_interrupt_returns_partial_output(self):
        """中断时已产生的部分输出不丢（现场证据）。"""
        ev = threading.Event()

        def _delayed_set():
            time.sleep(0.3)
            ev.set()

        threading.Thread(target=_delayed_set, daemon=True).start()
        result = execute("echo START; sleep 30", timeout=30, _interrupt_event=ev)

        assert "已被用户中断" in result
        assert "START" in result

    def test_interrupt_kills_child_process_group(self):
        """子进程的子进程也被杀（整组终止，不成孤儿）。"""
        ev = threading.Event()

        def _delayed_set():
            time.sleep(0.5)
            ev.set()

        threading.Thread(target=_delayed_set, daemon=True).start()
        result = execute("bash -c 'sleep 30'", timeout=30, _interrupt_event=ev)

        assert "已被用户中断" in result

    def test_normal_completion_unchanged(self):
        """正常跑完路径零变化：输出与旧行为一致。"""
        result = execute("echo hello", timeout=5)
        assert result == "hello"
        assert "已被用户中断" not in result

    def test_no_interrupt_event_behaves_as_before(self):
        """未注入中断事件（_interrupt_event=None）时行为不变。"""
        result = execute("echo normal", timeout=5, _interrupt_event=None)
        assert result == "normal"

    def test_timeout_still_kills_and_reports(self):
        """超时语义保持：超过 timeout 仍终止并报告。"""
        result = execute("sleep 30", timeout=1)
        assert "命令执行超过 1s" in result
        assert "已终止" in result

    def test_stderr_still_captured(self):
        """stderr 照常捕获（管道排空线程不丢 stderr）。"""
        result = execute("echo out; echo err >&2", timeout=5)
        assert "out" in result
        assert "err" in result


class TestEngineLevelInterruptNoRetry:
    """E2-3 engine 层：中断的命令不被自动重试、回合正常收束。

    复用 E-1 测试范式（假 LLM + 假工具执行器驱动 Engine.run），
    在工具执行途中 set _interrupt_event，验证：
      - execute_terminal 恰好被调用 1 次（不重试）
      - 工具结果含"已被用户中断"标注（LLM 看到的是中断而非超时/错误）
      - engine 中断后收束（state == STATE_ERROR）
    """

    def test_interrupted_command_not_retried(self, monkeypatch):
        from tests.test_engine_e2e import FakeLLMCaller, _make_test_engine, _make_tool_call

        fake_llm = FakeLLMCaller([
            (None, [_make_tool_call("tc_term", "execute_terminal", {"command": "sleep 30", "timeout": 30})]),
        ])

        captured = {"calls": 0, "result": ""}

        def tool_executor(tool_name, args):
            if tool_name == "execute_terminal":
                captured["calls"] += 1
                from tools.execute_terminal import execute
                captured["result"] = execute(
                    args.get("command", ""),
                    timeout=args.get("timeout", 30),
                    _interrupt_event=engine._interrupt_event,
                )
                return captured["result"]
            return f"[fake result of {tool_name}: {args}]"

        engine = _make_test_engine(fake_llm, tool_executor, monkeypatch)
        engine._interrupt_event = threading.Event()

        def _delayed_set():
            time.sleep(0.5)
            engine._interrupt_event.set()

        threading.Thread(target=_delayed_set, daemon=True).start()
        engine.run(user_input="执行 sleep 30")

        # 1. execute_terminal 恰好一次——中断的命令不被自动重试
        assert captured["calls"] == 1, f"execute_terminal 被调用 {captured['calls']} 次（应 1 次，不重试）"
        # 2. 中断标注完整
        assert "已被用户中断" in captured["result"], captured["result"]
        # 3. engine 中断收束（E-1 语义：interrupted 不进入正常完成）
        assert engine.state == engine.STATE_ERROR, f"state={engine.state} 应为 STATE_ERROR(interrupted)"
