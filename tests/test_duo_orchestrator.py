'''Duo 商讨模式编排器 — 单元/集成测试'''

from unittest.mock import MagicMock, patch


class TestBriefing:
    '''_briefing() — 项目现状扫描'''

    def test_briefing_returns_string(self):
        from core.duo_orchestrator import _briefing
        result = _briefing()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_briefing_contains_commits(self):
        from core.duo_orchestrator import _briefing
        result = _briefing()
        assert "## 最近提交" in result or "README" in result


class TestEmitAssistant:
    '''_emit_assistant() — TUI 消息发射'''

    def test_emit_called_with_content(self):
        from core.duo_orchestrator import _emit_assistant
        emit = MagicMock()
        _emit_assistant(emit, "sid-1", "hello")
        emit.assert_called_once()
        args = emit.call_args[0]
        assert args[0] == "message.delta"
        assert args[1] == "sid-1"
        assert "hello" in str(args[2])

    def test_emit_fails_gracefully(self):
        from core.duo_orchestrator import _emit_assistant
        def broken_emit(*args, **kwargs):
            raise RuntimeError("emit crashed")
        # should not raise
        _emit_assistant(broken_emit, "sid-1", "ignore")


class TestProjectSignals:
    '''_PROJECT_SIGNALS 匹配逻辑'''

    def test_signals_match_project_keywords(self):
        from core.duo_orchestrator import _PROJECT_SIGNALS
        assert "bobo" in _PROJECT_SIGNALS
        assert "代码" in _PROJECT_SIGNALS


class TestSummarize:
    '''_summarize() — LLM 决策清单生成（Mock LLM）'''

    @patch("core.provider.resolve_provider")
    @patch("core.llm_caller.create_llm_caller")
    def test_summarize_formats_prompt(self, mock_create, mock_resolve):
        mock_resolve.return_value = {"api_key": "k", "base_url": "u", "model": "m"}
        mock_llm = MagicMock()
        mock_llm.return_value = {
            "choices": [{"message": {"content": "### 共识\n两者一致"}}]
        }
        mock_create.return_value = mock_llm

        from core.duo_orchestrator import _summarize
        result = _summarize("测试问题", "A方案", "B挑刺")
        assert "共识" in result or "两者一致" in result

    @patch("core.provider.resolve_provider")
    @patch("core.llm_caller.create_llm_caller")
    def test_summarize_llm_error_fallback(self, mock_create, mock_resolve):
        mock_resolve.return_value = {"api_key": "k", "base_url": "u", "model": "m"}
        mock_llm = MagicMock()
        mock_llm.return_value = {"error": "API timeout"}
        mock_create.return_value = mock_llm

        from core.duo_orchestrator import _summarize
        result = _summarize("q", "a", "b")
        assert "失败" in result or "timeout" in result

    @patch("core.provider.resolve_provider", side_effect=Exception("no config"))
    def test_summarize_exception_fallback(self, mock_resolve):
        from core.duo_orchestrator import _summarize
        result = _summarize("q", "a", "b")
        assert "失败" in result


class TestRunDeliberation:
    '''run_deliberation() — 完整编排流程（Mock 外部依赖）'''

    @patch("tools.spawn_worker.execute")
    @patch("tools.spawn_worker.execute_read_worker_result")
    @patch("core.duo_orchestrator._summarize")
    @patch("core.duo_orchestrator._briefing")
    def test_full_flow_on_topic(self, mock_brief, mock_sum, mock_read, mock_spawn):
        """项目信号匹配 -> 简报 + A + B + 汇总"""
        mock_brief.return_value = "## 最近提交\n  abc123 feat"
        mock_spawn.side_effect = [
            "[WORKER_COMPLETE:duo-A-propose]",
            "[WORKER_COMPLETE:duo-B-critique]",
        ]
        mock_read.side_effect = ["这是A的方案全文", "这是B的挑刺全文"]
        mock_sum.return_value = "### 共识\n一致"

        from core.duo_orchestrator import run_deliberation
        emit = MagicMock()
        run_deliberation("如何改进 bobo 引擎", emit, "sid-1")

        # 应发射至少 4 条消息
        assert emit.call_count >= 4

    @patch("tools.spawn_worker.execute")
    @patch("tools.spawn_worker.execute_read_worker_result")
    @patch("core.duo_orchestrator._summarize")
    @patch("core.duo_orchestrator._briefing")
    def test_skip_briefing_for_off_topic(self, mock_brief, mock_sum, mock_read, mock_spawn):
        """不匹配项目信号时跳过简报"""
        mock_brief.return_value = "## 最近提交"
        mock_spawn.return_value = "[WORKER_COMPLETE:duo-A-propose]"
        mock_read.return_value = "方案内容"
        mock_sum.return_value = "### 共识"

        from core.duo_orchestrator import run_deliberation
        emit = MagicMock()
        run_deliberation("how to bake bread", emit, "sid-2")

    @patch("tools.spawn_worker.execute")
    def test_a_worker_timeout(self, mock_spawn):
        mock_spawn.return_value = "[WORKER_TIMEOUT] Worker 执行超过 90s。"

        from core.duo_orchestrator import run_deliberation
        emit = MagicMock()
        run_deliberation("测试问题", emit, "sid-3")

        args_all = [c.args[2]["text"] for c in emit.call_args_list if c.args[0] == "message.delta"]
        assert any("失败" in str(a) for a in args_all)

    @patch("tools.spawn_worker.execute")
    def test_a_worker_error(self, mock_spawn):
        mock_spawn.side_effect = RuntimeError("worker crashed")

        from core.duo_orchestrator import run_deliberation
        emit = MagicMock()
        run_deliberation("测试问题", emit, "sid-4")

        args_all = [c.args[2]["text"] for c in emit.call_args_list if c.args[0] == "message.delta"]
        assert any("失败" in str(a) for a in args_all)

    @patch("tools.spawn_worker.execute")
    @patch("tools.spawn_worker.execute_read_worker_result")
    @patch("core.duo_orchestrator._summarize")
    def test_b_worker_timeout(self, mock_sum, mock_read, mock_spawn):
        mock_spawn.side_effect = [
            "[WORKER_COMPLETE:duo-A-propose]",
            "[WORKER_TIMEOUT] Worker 执行超过 90s。",
        ]
        mock_read.return_value = "A方案内容"

        from core.duo_orchestrator import run_deliberation
        emit = MagicMock()
        run_deliberation("测试问题", emit, "sid-5")

        args_all = [c.args[2]["text"] for c in emit.call_args_list if c.args[0] == "message.delta"]
        assert any("失败" in str(a) for a in args_all)
