"""票 S：extract_takeaways 空转治理 — 测试套件

验收金标准：
- 闲聊回合（"谢谢"、"好的"）：llm_caller 调用次数 = 1（仅主回合，无 takeaway 调用）
- 价值回合（含价值关键词）：llm_caller 调用次数 = 2（主回合 + takeaway 提取）
"""

import pytest

from tests.test_engine_e2e import FakeLLMCaller, FakeToolExecutor, _make_test_engine, _collect_states

# ── 辅助：启用主动模式 ──


def _enable_proactive(engine, mode: str = "subtle"):
    """启用 engine 的 proactive 模式，使 takeaway 提取生效。"""
    engine.proactive.mode = mode


class TestTakeawayGate:
    """_takeaway_worthy 预筛闸门测试"""

    def test_chitchat_skipped(self, monkeypatch):
        """闲聊回合：call_count == 1（取消失败意味着多了一次 LLM 调用）"""
        fake_llm = FakeLLMCaller([
            ("好的，没问题。", None),
        ])
        fake_tools = FakeToolExecutor()
        engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)
        _enable_proactive(engine)

        engine.run(user_input="谢谢")

        assert engine.state == engine.STATE_DONE
        # 金标准：闲聊回合只调 1 次 LLM（主回复），takeaway 被闸门拦截
        assert fake_llm.call_count == 1, (
            f"闲聊回合应仅 1 次 LLM 调用（主回合），实际 {fake_llm.call_count}"
        )

    def test_confirm_skipped(self, monkeypatch):
        """确认词回合：call_count == 1"""
        fake_llm = FakeLLMCaller([
            ("好的，继续。", None),
        ])
        fake_tools = FakeToolExecutor()
        engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)
        _enable_proactive(engine)

        engine.run(user_input="好的")

        assert engine.state == engine.STATE_DONE
        assert fake_llm.call_count == 1, (
            f"确认回合应仅 1 次 LLM 调用，实际 {fake_llm.call_count}"
        )

    def test_short_qa_skipped(self, monkeypatch):
        """短问答（asst < 60 字且无价值关键词）：call_count == 1"""
        fake_llm = FakeLLMCaller([
            ("是 Python。", None),
        ])
        fake_tools = FakeToolExecutor()
        engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)
        _enable_proactive(engine)

        engine.run(user_input="这是啥语言")

        assert engine.state == engine.STATE_DONE
        assert fake_llm.call_count == 1, (
            f"短问答应仅 1 次 LLM 调用（无价值关键词），实际 {fake_llm.call_count}"
        )

    def test_value_decision_passes(self, monkeypatch):
        """价值回合（含"决定"关键词）：call_count == 2"""
        fake_llm = FakeLLMCaller([
            ("好的，已记住。", None),
        ])
        fake_tools = FakeToolExecutor()
        engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)
        _enable_proactive(engine)

        # 注意：_extract_takeaways 取 user[-1] 和 asst[-1]
        # 但 engine.run 内部会先调一次 llm_caller 回复用户，
        # 然后在 RESPONDING 阶段再调 _extract_takeaways。
        # 不过 FakeLLMCaller 只有 1 个 response，所以第二次调用（takeaway）会走兜底。
        # 不影响 call_count 计数。
        engine.run(user_input="我决定用 PostgreSQL")

        assert engine.state == engine.STATE_DONE
        assert fake_llm.call_count == 2, (
            f"价值回合应 2 次 LLM 调用（主回合 + takeaway），实际 {fake_llm.call_count}"
        )

    def test_long_content_passes(self, monkeypatch):
        """长内容（user > 100 字）：call_count == 2"""
        fake_llm = FakeLLMCaller([
            ("好详细的说明。", None),
        ])
        fake_tools = FakeToolExecutor()
        engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)
        _enable_proactive(engine)

        long_input = "用户" * 60  # 120 字，超过 100 字阈值
        engine.run(user_input=long_input)

        assert engine.state == engine.STATE_DONE
        assert fake_llm.call_count == 2, (
            f"长内容回合应 2 次 LLM 调用（主回合 + takeaway），实际 {fake_llm.call_count}"
        )

    def test_remember_keyword_passes(self, monkeypatch):
        """价值关键词"记住"：call_count == 2"""
        fake_llm = FakeLLMCaller([
            ("记住了。", None),
        ])
        fake_tools = FakeToolExecutor()
        engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)
        _enable_proactive(engine)

        engine.run(user_input="记住这个设置")

        assert engine.state == engine.STATE_DONE
        assert fake_llm.call_count == 2, (
            f"含'记住'关键词应 2 次 LLM 调用，实际 {fake_llm.call_count}"
        )

    def test_bobo_takeaways_off_disables_extraction(self, monkeypatch):
        """BOBO_TAKEAWAYS=off 彻底禁用提取，即使价值回合也仅 1 次"""
        import os
        monkeypatch.setattr(os, "environ", {**os.environ, "BOBO_TAKEAWAYS": "off"})
        fake_llm = FakeLLMCaller([
            ("好的，记住。", None),
        ])
        fake_tools = FakeToolExecutor()
        engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)
        _enable_proactive(engine)

        engine.run(user_input="记住用 PostgreSQL")

        assert engine.state == engine.STATE_DONE
        assert fake_llm.call_count == 1, (
            f"BOBO_TAKEAWAYS=off 时应仅 1 次 LLM 调用，实际 {fake_llm.call_count}"
        )

    def test_prefilter_method_directly(self, monkeypatch):
        """直接测试 _takeaway_worthy 静态方法"""
        from core.engine import Engine

        # ── 跳过场景 ──
        assert Engine._takeaway_worthy("谢谢", "不客气") is False, "纯闲聊应跳过"
        assert Engine._takeaway_worthy("好的", "好的继续") is False, "确认词应跳过"
        assert Engine._takeaway_worthy("嗯", "是的") is False, "单字确认应跳过"
        assert Engine._takeaway_worthy("继续", "好的继续") is False, "过渡词应跳过"
        assert Engine._takeaway_worthy("这是啥", "是 Python") is False, "短问答无价值应跳过"

        # ── 放行场景 ──
        assert Engine._takeaway_worthy("我决定用A", "好的") is True, "含决定应放行"
        assert Engine._takeaway_worthy("记住这个配置", "好的") is True, "含记住应放行"
        assert Engine._takeaway_worthy("以后都用这个方案", "好的") is True, "含以后都应放行"
        assert Engine._takeaway_worthy("a" * 110, "b") is True, "长user应放行"
        assert Engine._takeaway_worthy("hi", "b" * 310) is True, "长asst应放行"

        # 短内容但带价值关键词 → 放行
        assert Engine._takeaway_worthy("密码是 123", "收到") is True, "含密码应放行"
        assert Engine._takeaway_worthy("部署到服务器", "好的") is True, "含部署应放行"

    def test_tool_round_releases_gate(self, monkeypatch):
        """工具回合无条件放行（终审补漏 2026-07-29）：工作回合即便收尾文字
        很短（'改完了'），也必须打 takeaway 调用——宁可多打不可漏记。"""
        fake_llm = FakeLLMCaller([("改完了", None)])
        fake_tools = FakeToolExecutor()
        engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)
        _enable_proactive(engine)

        # 模拟刚经历工具回合的工作现场
        engine.current_tool_round = 2
        engine.history = [
            {"role": "user", "content": "把配置改一下"},
            {"role": "assistant", "content": "改完了"},
        ]

        engine._extract_takeaways()

        assert fake_llm.call_count >= 1, (
            "工具回合应放行 takeaway 调用，实际 LLM 未被调用"
        )

    def test_no_tool_round_short_text_still_skipped(self, monkeypatch):
        """对照组：无工具回合 + 同样的短文字 → 仍然跳过。"""
        fake_llm = FakeLLMCaller([("改完了", None)])
        fake_tools = FakeToolExecutor()
        engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)
        _enable_proactive(engine)

        engine.current_tool_round = 0
        engine.history = [
            {"role": "user", "content": "帮忙弄一下"},
            {"role": "assistant", "content": "弄好了"},
        ]

        engine._extract_takeaways()

        assert fake_llm.call_count == 0, (
            f"无工具回合的短文字应跳过，实际调了 {fake_llm.call_count} 次"
        )
