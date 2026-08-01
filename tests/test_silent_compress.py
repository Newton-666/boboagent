"""静默压缩回归（用户 2026-07-29 需求）：压缩默认不占 TUI 状态栏。

背景：压缩提示 "正在压缩历史上下文..." 挂在 TUI 上让用户误以为出事；
压缩是后台维护动作，可观测性走事件总线 context.compressed，不打扰用户。
BOBO_SHOW_COMPRESS=1 可恢复提示（调试用）。
"""

import os
import sys
import pytest

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _project_root)


@pytest.fixture
def engine():
    from tests.mock_llm import MockLLMCaller, text_response
    from core.tool_executor import execute_tool
    from core.engine import Engine
    caller = MockLLMCaller([text_response("摘要"), text_response("ok")])
    return Engine(caller, execute_tool, test_mode=True)


def _fill_history(engine, n_pairs=40):
    engine.history = []
    for i in range(n_pairs):
        engine.history.append({"role": "user", "content": f"输入 {i}"})
        engine.history.append({"role": "assistant", "content": f"回复 {i}"})


class TestSilentCompress:

    def test_compress_silent_by_default(self, engine, monkeypatch):
        """默认：压缩触发时不发 compressing 状态通知。"""
        monkeypatch.setenv("BOBO_CONTEXT_BUDGET", "30")
        # TICKET-024：token 预算 + 层0上限适配，确保压缩真正触发
        import core.context as ctx_module
        monkeypatch.setattr(ctx_module, "_get_context_budget", lambda _engine=None: 1)
        engine._LAYER_0_TOKEN_LIMIT = 200
        monkeypatch.delenv("BOBO_SHOW_COMPRESS", raising=False)
        _fill_history(engine)

        notices = []
        orig_notify = engine._notify
        engine._notify = lambda t, d: notices.append((t, d)) or orig_notify(t, d)

        engine.current_user_input = "继续"
        engine.state = engine.STATE_IDLE
        engine._step()  # IDLE → THINKING
        engine._step()  # THINKING → 压缩 + 回复

        compressing = [d for t, d in notices if d.get("phase") == "compressing"]
        assert not compressing, f"默认不应显示压缩提示，实际: {compressing}"
        # 压缩确实发生了（摘要落 history，TICKET-024: L2/L1/兜底 格式）
        summaries = [m for m in engine.history
                     if m.get("role") == "system"
                     and (m.get("content", "").startswith("[L2 极简摘要]")
                          or m.get("content", "").startswith("[L1 段摘要]")
                          or m.get("content", "").startswith("[对话历史摘要]"))]
        assert summaries, "压缩未生效"

    def test_compress_notice_with_env_flag(self, engine, monkeypatch):
        """BOBO_SHOW_COMPRESS=1：恢复压缩提示（调试通道）。"""
        monkeypatch.setenv("BOBO_CONTEXT_BUDGET", "30")
        monkeypatch.setenv("BOBO_SHOW_COMPRESS", "1")
        _fill_history(engine)

        notices = []
        orig_notify = engine._notify
        engine._notify = lambda t, d: notices.append((t, d)) or orig_notify(t, d)

        engine.current_user_input = "继续"
        engine.state = engine.STATE_IDLE
        engine._step()
        engine._step()

        compressing = [d for t, d in notices if d.get("phase") == "compressing"]
        assert compressing, "BOBO_SHOW_COMPRESS=1 时应显示压缩提示"
