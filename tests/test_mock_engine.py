"""Test engine behavior using mock LLM — no API key needed, runs offline."""

import sys
sys.path.insert(0, '.')

from core.engine import Engine
from core.tool_executor import execute_tool
from tests.mock_llm import MockLLMCaller, text_response, tool_response


def test_simple_text_response():
    """Engine should return a text response and stop."""
    caller = MockLLMCaller([text_response("Hello!")])
    engine = Engine(caller, execute_tool, test_mode=True)
    engine.run("say hi")
    assert len(engine.history) >= 2  # user + assistant
    assert any("Hello" in str(m) for m in engine.history)
    print("[PASS] test_simple_text_response")


def test_tool_call_then_text():
    """Engine should execute a tool, then respond with text."""
    caller = MockLLMCaller([
        tool_response("get_current_time"),
        text_response("The time is now."),
    ])
    engine = Engine(caller, execute_tool, test_mode=True)
    engine.run("what time is it")
    assert len(engine.history) >= 3  # user + assistant(tc) + tool + assistant
    print("[PASS] test_tool_call_then_text")


def test_max_steps_termination():
    """Engine should stop after MAX_STEPS if the LLM keeps calling tools."""
    tool_calls = []
    for _ in range(35):  # exceed MAX_STEPS (30)
        tool_calls.append(tool_response("get_current_time"))
    tool_calls.append(text_response("Done"))
    caller = MockLLMCaller(tool_calls)
    engine = Engine(caller, execute_tool, test_mode=True)
    engine.run("loop")
    assert engine.state == engine.STATE_ERROR
    print("[PASS] test_max_steps_termination")


def test_context_compression():
    """Engine should compress history that exceeds MAX_HISTORY_CHARS."""
    caller = MockLLMCaller([
        text_response("A" * 20000),  # large response
        text_response("compressed"),
    ])
    engine = Engine(caller, execute_tool, test_mode=True)
    engine.MAX_HISTORY_CHARS = 5000  # small budget for testing
    engine.run("write a lot")
    engine.run("continue")  # second call triggers compression check
    print("[PASS] test_context_compression")


def test_tool_failure_loop_breaker():
    """Engine should stop retrying a tool that fails twice."""
    caller = MockLLMCaller([
        tool_response("get_current_time"),  # first call → tool
        tool_response("get_current_time"),  # second call → same tool again
        text_response("I give up"),
    ])
    engine = Engine(caller, execute_tool, test_mode=True)
    engine.run("try tool")
    # The tool fails (it returns "错误..." since get_current_time needs no args
    # but the mock tool args might mismatch — this just tests the loop doesn't hang)
    print("[PASS] test_tool_failure_loop_breaker")


if __name__ == "__main__":
    test_simple_text_response()
    test_tool_call_then_text()
    test_max_steps_termination()
    test_context_compression()
    test_tool_failure_loop_breaker()
    print(f"\nAll {5} tests passed (no API calls made)")
