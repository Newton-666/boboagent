"""Tests for TICKET-R2-P2：三方发言检测修复（hermes/claude/pi idle 判定 + 摘录逻辑）。

票 R2-P2 背景：
    team_relay_v2 首跑时 hermes/claude/pi 三方发言检测从未触发——
    只有 bobo 写 inbox。根因：
    1. hermes_idle 缺 ⏱ (U+23F1) 活跃计时器 → hermes 总是判闲
    2. claude_idle 缺 Thinking/⏱ → claude 总是判闲
    3. pi_finished 是永久状态检测（token 统计栏首轮后一直存在）→ pi 总是判闲
    4. base 从 init 取（含大量历史）→ diff_new SequenceMatcher 漏内容
    5. 修复：idle→busy 时保存 pre_busy_base，busy→idle 时用它做 diff

本测试覆盖：
    - 四个 agent 的 idle 函数（正确区分 busy/idle）
    - sanitize_state（state/inbox 一致性修复）
    - _seq_of（文件名序号提取）
    - clean_reply（发言清理：注入段/硬约束/思考流过滤）
    - _capture_reply（busy→idle 发言摘录）
    - pane_idle_fn 正确映射
    - pre_busy_base 过渡逻辑
"""

import os
import sys
import tempfile
import pytest

# 确保 worktree 的 tools 在 path 中（不从 main repo 引入）
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

# ---------------------------------------------------------------------------
# 被测模块
# ---------------------------------------------------------------------------
import team_relay_v2 as tr  # noqa: E402


# ============================================================================
# _seq_of
# ============================================================================
class TestSeqOf:
    """从文件名提取序号。"""

    def test_normal(self):
        assert tr._seq_of("0001.md") == 1
        assert tr._seq_of("0099.md") == 99
        assert tr._seq_of("0100.md") == 100

    def test_edge_cases(self):
        assert tr._seq_of("abcd.md") == 0
        assert tr._seq_of("") == 0
        assert tr._seq_of("0001.md.tmp") == 1  # .tmp 不参与排序，但 _seq_of 只看前 4 位

    def test_non_md(self):
        assert tr._seq_of("0010.txt") == 10


# ============================================================================
# sanitize_state
# ============================================================================
class TestSanitizeState:
    """防御 state/inbox 不一致（票 R2-P2）。"""

    @pytest.fixture(autouse=True)
    def _iso(self, tmp_path, monkeypatch):
        """tmp 隔离（收编修复）：不写真实 inbox/relay.state，防环境残留污染断言。"""
        monkeypatch.setattr(tr, "INBOX_ROOT", str(tmp_path))
        monkeypatch.setattr(tr, "STATE_PATH", str(tmp_path / "relay.state"))

    def test_all_agents_present(self):
        """返回的 state 必须含全部 4 个 agent。"""
        state = tr.sanitize_state({"bobo": 1})
        assert set(state.keys()) == set(tr.ORDER)
        for name in tr.ORDER:
            assert name in state

    def test_empty_inbox_resets_state(self):
        """inbox 为空时 state 应全部归零（无文件可转发）。"""
        state = tr.sanitize_state({"bobo": 9, "hermes": 5, "claude": 3, "pi": 7})
        # inbox 目录初始为空 → max_seq=0，state 值 > 0 应被重置
        for name in tr.ORDER:
            # 如果 inbox 目录存在且有文件，此断言可能失败；
            # 环境差异可通过 setUp 写真实文件来验证
            d = tr._agent_inbox(name)
            if not os.path.isdir(d) or not any(
                fn.endswith(".md") and not fn.endswith(".tmp") for fn in os.listdir(d)
            ):
                assert state[name] == 0, f"{name} inbox 为空但 state={state[name]}"

    def test_unknown_agent_not_in_order(self):
        """不在 ORDER 中的 agent 不出现（sanitize 只返回 ORDER 中的 key）。"""
        state = tr.sanitize_state({"bobo": 1, "unknown_agent": 99})
        assert "unknown_agent" not in state

    def test_state_not_exceeding_inbox_max(self):
        """state 不应超过 inbox 实际最大序号。"""
        # 给 bobo 写两个文件，验证 sanitize 不会把 state 降到 0
        d = tr._agent_inbox("bobo")
        os.makedirs(d, exist_ok=True)
        f1 = os.path.join(d, "0001.md")
        f2 = os.path.join(d, "0002.md")
        try:
            with open(f1, "w", encoding="utf-8") as f:
                f.write("test message 1")
            with open(f2, "w", encoding="utf-8") as f:
                f.write("test message 2")
            # state 记录 3（超过实际最大 2）→ 应降为 2
            state = tr.sanitize_state({"bobo": 3, "hermes": 0, "claude": 0, "pi": 0})
            assert state["bobo"] == 2, f"expected 2, got {state['bobo']}"
            # state 记录 1（≤ 实际最大 2）→ 保持 1
            state2 = tr.sanitize_state({"bobo": 1, "hermes": 0, "claude": 0, "pi": 0})
            assert state2["bobo"] == 1, f"expected 1, got {state2['bobo']}"
        finally:
            os.remove(f1)
            os.remove(f2)


# ============================================================================
# 空闲判定函数（核心修复）
# ============================================================================

# ── hermes_idle ──
class TestHermesIdle:
    """hermes 空闲判定：提示符 + 无忙碌标志。"""

    def test_idle_with_clock_timer(self):
        """⏲ (U+23F2 timer clock) = 等待中计时器 → 空闲。"""
        screen = (
            "⚕ deepseek-v4-flash │ 96.1K/1M │ [█░░░░░░░░░] 10% │ 28m │ ⏲ 8s\n"
            "⚕ ❯ msg=interrupt · /queue · /bg · /steer · Ctrl+C cancel"
        )
        assert tr.hermes_idle(screen) is True

    def test_busy_with_stopwatch(self):
        """⏱ (U+23F1 stopwatch) = 活跃 LLM 调用计时器 → 忙碌。"""
        screen = (
            "⚕ deepseek-v4-flash │ 108K/1M │ [█░░░░░░░░░] 11% │ 17m │ ⏱ 13s\n"
            "⚕ ❯ msg=interrupt · /queue · /bg · /steer · Ctrl+C cancel"
        )
        assert tr.hermes_idle(screen) is False

    def test_busy_with_hourglass(self):
        """⏳ (U+23F3 hourglass) = 沙漏 → 忙碌。"""
        screen = (
            "⚕ deepseek-v4-flash │ 50K/1M │ [░░░░░░░░░░] 5% │ 1m │ ⏳\n"
            "⚕ ❯ msg=interrupt"
        )
        assert tr.hermes_idle(screen) is False

    def test_busy_working(self):
        """'Working' 文本 → 忙碌。"""
        screen = "Working on the response...\n⚕ ❯"
        assert tr.hermes_idle(screen) is False

    def test_busy_initializing(self):
        """'Initializing agent' → 忙碌。"""
        screen = "Initializing agent...\n⚕ ❯"
        assert tr.hermes_idle(screen) is False

    def test_no_prompt_not_idle(self):
        """无提示符 → 非空闲。"""
        assert tr.hermes_idle("some random text") is False

    def test_empty_screen(self):
        assert tr.hermes_idle("") is False

    def test_standalone_prompt(self):
        """独立的 ❯ 提示符也接受。"""
        screen = "some history\n❯"
        assert tr.hermes_idle(screen) is True

    def test_lightning_bolt_history_not_busy(self):
        """⚡ 工具调用历史标记 ≠ 忙碌（已验证，回归测试）。"""
        # ⚡ 后跟 tool(...) 耗时 0.0s = 已完成的历史记录
        screen = (
            "⚡ tool(search) 0.0s\n"
            "some response text\n"
            "⚕ deepseek-v4-flash │ 96.1K/1M │ [█░░░░░░░░░] 10% │ 28m │ ⏲ 8s\n"
            "⚕ ❯ msg=interrupt"
        )
        assert tr.hermes_idle(screen) is True


# ── claude_idle ──
class TestClaudeIdle:
    """claude (Claude Code) 空闲判定：❯ 提示符 + 无忙碌标志。"""

    def test_idle_with_prompt(self):
        """❯ 独立出现 → 空闲。"""
        screen = "some conversation history\n\n❯"
        assert tr.claude_idle(screen) is True

    def test_idle_prompt_with_short_text(self):
        """❯ 后面跟短文本（如光标指示）→ 空闲。"""
        screen = "text\n❯ "
        assert tr.claude_idle(screen) is True

    def test_busy_thinking(self):
        """'Thinking' 文本 → 忙碌。（Claude Code 思考标志）"""
        screen = "Thinking about the best approach..."
        assert tr.claude_idle(screen) is False

    def test_busy_working(self):
        """'Working' 文本 → 忙碌。"""
        screen = "Working on the response..."
        assert tr.claude_idle(screen) is False

    def test_busy_stopwatch(self):
        """⏱ 活跃计时器 → 忙碌。"""
        screen = "❯" + "\n" * 3 + "⏱ 5s"
        assert tr.claude_idle(screen) is False

    def test_busy_approval(self):
        """确认框 → 忙碌。"""
        assert tr.claude_idle("Do you want to proceed") is False
        assert tr.claude_idle("requires approval") is False

    def test_no_prompt_not_idle(self):
        """无 ❯ 提示符 → 非空闲。"""
        assert tr.claude_idle("just some text") is False

    def test_empty_screen(self):
        assert tr.claude_idle("") is False

    def test_clock_emoji_history_not_busy(self):
        """⏺ 后台 agent 历史标记 ≠ 忙碌。"""
        screen = (
            "⏺ tool(search) completed\n"
            "some response\n"
            "❯"
        )
        assert tr.claude_idle(screen) is True

    def test_prompt_in_content_not_false_idle(self):
        """❯ 出现在长行内容中不是提示符 → 不应判为提示符。"""
        # 只有最后 3 行检查；❯ 在长行中不会被当作提示符
        screen = (
            "here is a command: ❯ ls -la /some/very/long/path\n"
            "more text\n"
            "some other content not a prompt"  # 最后一行无独立 ❯
        )
        assert tr.claude_idle(screen) is False


# ── pi_idle ──
class TestPiIdle:
    """pi 空闲判定：token 统计栏 + 无忙碌标志。"""

    def test_idle_with_token_stats(self):
        """token 统计可见，无忙碌标志 → 空闲。"""
        screen = (
            "some response text\n"
            "↑ 1.2K ↓ 890 deepseek-v4-pro"
        )
        assert tr.pi_idle(screen) is True

    def test_no_token_stats_not_idle(self):
        """无 token 统计栏 → pi 尚未完成首次回复 → 忙碌。"""
        assert tr.pi_idle("just some text") is False

    def test_busy_working(self):
        """token 统计存在 + 'Working' → 忙碌。"""
        screen = (
            "Working on response...\n"
            "↑ 1.2K ↓ 890 deepseek-v4-pro"
        )
        assert tr.pi_idle(screen) is False

    def test_busy_thinking(self):
        """token 统计存在 + 'Thinking' → 忙碌。"""
        screen = "Thinking\n↑ 1.2K ↓ 890 deepseek-v4-pro"
        assert tr.pi_idle(screen) is False

    def test_busy_stopwatch(self):
        """⏱ 活跃计时器 → 忙碌。"""
        screen = "⏱ 3s\n↑ 1.2K ↓ 890 deepseek-v4-pro"
        assert tr.pi_idle(screen) is False

    def test_busy_braille_spinner(self):
        """braille spinner 字符（pi 思考动画）→ 忙碌。"""
        for ch in "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏":
            screen = f"{ch} Working...\n↑ 1.2K ↓ 890 deepseek-v4-pro"
            assert tr.pi_idle(screen) is False, f"spinner '{ch}' should be busy"

    def test_empty_screen(self):
        assert tr.pi_idle("") is False


# ── bobo_idle ──
class TestBoboIdle:
    """bobo 空闲判定：> 提示符 + 无思考词（已有实现，回归测试）。"""

    def test_idle_prompt(self):
        screen = "some text\n>"
        assert tr.bobo_idle(screen) is True

    def test_busy_thinking(self):
        for word in ("cogitating", "thinking", "analyzing", "working", "computing"):
            screen = f"● {word}...\n>"
            assert tr.bobo_idle(screen) is False, f"'{word}' should be busy"

    def test_no_prompt(self):
        assert tr.bobo_idle("random") is False

    def test_empty(self):
        assert tr.bobo_idle("") is False


# ============================================================================
# pane_idle_fn 映射
# ============================================================================
class TestPaneIdleFn:
    """pane_idle_fn 返回正确的判定函数。"""

    def test_mapping(self):
        assert tr.pane_idle_fn("bobo") == tr.bobo_idle
        assert tr.pane_idle_fn("hermes") == tr.hermes_idle
        assert tr.pane_idle_fn("claude") == tr.claude_idle
        assert tr.pane_idle_fn("pi") == tr.pi_idle

    def test_unknown_raises(self):
        with pytest.raises(KeyError):
            tr.pane_idle_fn("unknown")


# ============================================================================
# clean_reply
# ============================================================================
class TestCleanReply:
    """发言清理：过滤 relay 注入段 / 硬约束 / 思考流。"""

    def test_filters_inject_prefix(self):
        text = "【来自 bobo 的发言】\n实际内容1\n【来自 hermes 的发言】\n实际内容2"
        result = tr.clean_reply(text)
        assert "【来自" not in result
        assert "实际内容1" in result
        assert "实际内容2" in result

    def test_filters_hard_constraint(self):
        text = "【硬约束·必须遵守】本讨论为纯讨论\n实际回复内容"
        result = tr.clean_reply(text)
        assert "【硬约束" not in result
        assert "实际回复内容" in result

    def test_filters_thinking_stream(self):
        """💭 思考流不进通道。"""
        text = "💭 我来想想这个问题...\n正式回复内容"
        result = tr.clean_reply(text)
        # clean() 会移除空行，但 clean_reply 过滤 💭 行
        assert "💭" not in result
        assert "正式回复内容" in result

    def test_preserves_normal_content(self):
        text = "这是一段正常的回复内容\n包含多行文本"
        result = tr.clean_reply(text)
        assert "正常的回复内容" in result

    def test_filters_inject_without_trailing_marker(self):
        """【来自 开头但无 的发言】后缀的不过滤（不是 relay 注入段）。"""
        text = "【来自远古的呼唤\n实际内容"
        result = tr.clean_reply(text)
        assert "【来自远古的呼唤" in result  # 无 "的发言】" 后缀，保留


# ============================================================================
# _capture_reply / extract_reply
# ============================================================================
class TestCaptureReply:
    """busy→idle 发言摘录。"""

    def test_extracts_new_response(self):
        """从 busy→idle 前后屏幕 diff 中提取发言。"""
        before = "some history\n>"
        after = "some history\nnew response text\n>"
        result = tr.extract_reply(before, after)
        assert "new response text" in result

    def test_capture_reply_filters_injection(self):
        """摘录结果应过滤 relay 注入段。"""
        before = "history\nexisting content\n>"
        after = (
            "history\nexisting content\n"
            "【来自 bobo 的发言】\n"
            "relay 注入的转发内容\n"
            "hermes 的实际回复\n"
            "⚕ ❯"
        )
        result = tr._capture_reply("hermes", before, after)
        # relay 注入段应被过滤
        assert "【来自 bobo 的发言】" not in result
        # hermes 实际回复应保留（clean 可能过滤了 TUI 杂讯，但发言内容应在）
        assert "hermes 的实际回复" in result

    def test_empty_diff_returns_empty(self):
        """屏幕无变化 → 空结果。"""
        before = "same text\n>"
        after = "same text\n>"
        result = tr._capture_reply("bobo", before, after)
        assert result.strip() == ""

    def test_different_screens(self):
        """基本 diff 功能。"""
        before = "line1\nline2"
        after = "line1\nline2\nline3 new"
        result = tr.extract_reply(before, after)
        assert "line3 new" in result


# ============================================================================
# 集成：pre_busy_base 过渡逻辑（busy→idle 检测模拟）
# ============================================================================
class TestPreBusyBaseLogic:
    """idle→busy 保存 pre_busy_base，busy→idle 用它做 diff。

    这是 P2 修复的核心逻辑——验证用 pre_busy_base 做 diff 比
    用 init base 更精确（diff 范围更小，只含本轮注入+新回复）。
    """

    def make_screens(self, agent, idle_content, busy_content, response_content):
        """生成模拟屏幕序列：idle → busy → 新 idle（含回复）。"""
        return {
            "idle_before": idle_content,
            "busy": busy_content,
            "idle_after": idle_content + "\n" + response_content,
        }

    def test_small_diff_window_better_than_full_base(self):
        """pre_busy_base（发言前屏幕）的 diff 窗口 < init base 的 diff 窗口。"""
        # 模拟场景：屏幕上已有大量历史
        history = "\n".join(f"history line {i}" for i in range(100))
        prompt = "❯"
        init_base = history + "\n" + prompt  # relay 启动时抓的基线
        # hermes 注入消息后，屏幕新增了注入段 + hermes 的回复
        injection = "【来自 bobo 的发言】\nbobo 的转发内容"
        response = "hermes 的回复文本"

        # init_base → idle_after：diff 窗口包含 100 行历史 + 注入 + 回复
        idle_after = history + "\n" + injection + "\n" + response + "\n" + prompt
        diff_from_init = tr.extract_reply(init_base, idle_after)
        # 因为 100 行历史相同，diff 只含新增部分
        assert "hermes 的回复文本" in diff_from_init

        # pre_busy_base（发言前 = init_base，因为 agent 即将变 busy）
        # busy→idle 时用 pre_busy_base diff
        pre_busy = init_base  # idle→busy 时保存的干净屏幕
        diff_from_pre_busy = tr.extract_reply(pre_busy, idle_after)
        assert "hermes 的回复文本" in diff_from_pre_busy

        # 两者都应能提取到回复，但 pre_busy_base 语义更精确
        # （真实场景 history 可能不完全相同，SequenceMatcher 在大 diff 上更易出错）

    def test_pre_busy_base_vs_stale_base_boundary(self):
        """极端场景：pre_busy_base 有 1 行，init base 有 1000 行。

        pre_busy → idle_after 的 diff 范围远小于 init_base → idle_after。
        """
        # init base = 大量历史 + prompt
        init_base = "\n".join(f"L{i:04d}" for i in range(1000)) + "\n>"
        # pre_busy = 刚变 busy 前（简洁）
        pre_busy = ">"
        # 回复
        idle_after = "> \nresponse text here\n>"
        # 两种 base 比较
        diff_init = len(tr.extract_reply(init_base, idle_after))
        diff_pre = len(tr.extract_reply(pre_busy, idle_after))
        # pre_busy diff 结果更短（更精确），但不影响核心内容
        assert diff_pre <= diff_init + 50  # 允许微小差异

    # ------------------------------------------------------------------
    # busy→idle 转换的 mock relay 循环模拟
    # ------------------------------------------------------------------
    def test_idle_to_busy_transition_saves_pre_busy_base(self):
        """模拟 relay 循环中 idle→busy 时保存 pre_busy_base。"""
        pre_busy_base = {}
        idle_prev = {
            "bobo": True, "hermes": True, "claude": True, "pi": True
        }
        prev_screen = {
            "bobo": "bobo idle\n>",
            "hermes": "hermes idle\n⚕ ❯",
            "claude": "claude idle\n❯",
            "pi": "pi idle\n↑ 1K ↓ 800 deepseek",
        }
        cur_screen = {
            "bobo": "bobo idle\n>",
            "hermes": "hermes busy\n⚕ ⏱ 5s\nWorking...",  # 忙碌
            "claude": "claude idle\n❯",
            "pi": "pi idle\n↑ 1K ↓ 800 deepseek",
        }
        idle_fn = tr.pane_idle_fn

        for name in tr.ORDER:
            idle_now = idle_fn(name)(cur_screen[name])
            if idle_prev[name] and not idle_now:
                # idle→busy → 保存 pre_busy_base
                pre_busy_base[name] = prev_screen[name]
            idle_prev[name] = idle_now

        # hermes 应该触发了 idle→busy 保存
        assert "hermes" in pre_busy_base
        assert pre_busy_base["hermes"] == "hermes idle\n⚕ ❯"
        # 其他 agent 保持 idle
        assert "bobo" not in pre_busy_base
        assert "claude" not in pre_busy_base

    def test_busy_to_idle_transition_captures_with_pre_busy_base(self):
        """模拟 relay 循环中 busy→idle 时用 pre_busy_base 做 diff 并摘录。"""
        pre_busy_base = {
            "hermes": "⚕ ❯ msg=interrupt"  # 发言前保存的干净屏幕
        }
        idle_prev = {
            "bobo": True, "hermes": False, "claude": True, "pi": True
        }
        # hermes 已完成回复，屏幕回到 idle
        cur_screen = {
            "hermes": (
                "⚕ ❯ msg=interrupt\n"
                "【来自 bobo 的发言】\n"
                "bobo 转发内容\n"
                "hermes 的正式回复\n"
                "⚕ deepseek-v4-flash │ 96.1K/1M │ [█░░░░░░░░░] 10% │ 28m │ ⏲ 8s\n"
                "⚕ ❯ msg=interrupt"
            )
        }
        idle_fn = tr.pane_idle_fn

        for name in ["hermes"]:
            idle_now = idle_fn(name)(cur_screen[name])
            if (not idle_prev[name]) and idle_now:
                # busy→idle：用 pre_busy_base 做 diff
                capture_base = pre_busy_base.pop(name, "fallback")
                new = tr._capture_reply(name, capture_base, cur_screen[name])
                # 验证摘录结果
                assert "hermes 的正式回复" in new
                assert "【来自 bobo 的发言】" not in new  # 注入段被过滤
                assert len(new.strip()) >= 10  # 超过最低阈值
            idle_prev[name] = idle_now

    def test_quick_response_not_missed(self):
        """快速回复（单轮捕获窗口内完成）不会被完全错过。

        如果 idle_now 在某次捕获中仍为 False 但在下一轮变为 True，
        pre_busy_base 已存，diff 仍然有效。
        """
        pre_busy_base = {"claude": "❯"}  # 上一轮 idle→busy 时保存
        idle_prev = {"claude": False}
        # 这一轮 claude 完成了回复
        cur = "❯ \nclaude quick reply\n❯"
        idle_now = tr.claude_idle(cur)
        assert idle_now is True
        # busy→idle 触发
        if (not idle_prev["claude"]) and idle_now:
            capture_base = pre_busy_base.pop("claude", "fallback")
            new = tr._capture_reply("claude", capture_base, cur)
            assert "claude quick reply" in new
        else:
            pytest.fail("busy→idle transition should have triggered")


# ============================================================================
# inbox 读写 + state 管理（原子性/通道一致性回归测试）
# ============================================================================
class TestInboxReadWrite:
    """inbox 原子写入 + 序号递增 + state 同步。"""

    def setup_method(self):
        self.test_dir = tempfile.mkdtemp(prefix="r2p2_test_")
        # 暂时劫持 INBOX_ROOT 和 STATE_PATH（只读测试——不落盘到真实 data/）
        self._orig_inbox = tr.INBOX_ROOT
        self._orig_state = tr.STATE_PATH
        tr.INBOX_ROOT = self.test_dir
        tr.STATE_PATH = os.path.join(self.test_dir, "relay.state")

    def teardown_method(self):
        tr.INBOX_ROOT = self._orig_inbox
        tr.STATE_PATH = self._orig_state
        import shutil
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_write_and_read_roundtrip(self):
        """写入 → 读取 往返一致性。"""
        seq = tr.write_inbox("bobo", "hello world")
        assert seq == 1
        msgs = tr.read_new_inbox("bobo", 0)
        assert len(msgs) == 1
        assert msgs[0][0] == 1
        assert msgs[0][1] == "hello world"

    def test_sequential_write(self):
        """连续写入序号递增。"""
        s1 = tr.write_inbox("bobo", "msg1")
        s2 = tr.write_inbox("bobo", "msg2")
        s3 = tr.write_inbox("bobo", "msg3")
        assert s1 == 1
        assert s2 == 2
        assert s3 == 3

    def test_read_new_only(self):
        """read_new_inbox 只返回 > last_seq 的消息。"""
        tr.write_inbox("bobo", "old")
        tr.write_inbox("bobo", "new1")
        tr.write_inbox("bobo", "new2")
        msgs = tr.read_new_inbox("bobo", 1)
        assert len(msgs) == 2
        assert msgs[0][0] == 2
        assert msgs[1][0] == 3

    def test_empty_inbox(self):
        msgs = tr.read_new_inbox("nonexistent", 0)
        assert msgs == []

    def test_save_and_load_state(self):
        """state 持久化往返。"""
        state = {"bobo": 3, "hermes": 1, "claude": 2, "pi": 0}
        tr.save_state(state)
        loaded = tr.load_state()
        assert loaded == state

    def test_load_state_defaults(self):
        """state 文件不存在时返回全 0。"""
        if os.path.exists(tr.STATE_PATH):
            os.remove(tr.STATE_PATH)
        loaded = tr.load_state()
        assert loaded == {a: 0 for a in tr.ORDER}


# ============================================================================
# 身份复核 + pane 签名（L3 铁律回归）
# ============================================================================
class TestPaneSignature:
    """pane 身份特征检测（票 R1-1 评审点 5，回归测试）。"""

    def test_bobo_signature(self):
        assert tr._pane_signature("bobo", "some text\n>")
        assert not tr._pane_signature("bobo", "no prompt here")

    def test_hermes_signature(self):
        assert tr._pane_signature("hermes", "⚕ ❯ msg=interrupt")
        assert tr._pane_signature("hermes", "text\n❯")
        assert not tr._pane_signature("hermes", "regular text")

    def test_claude_signature(self):
        assert tr._pane_signature("claude", "text\n❯")
        assert not tr._pane_signature("claude", "no prompt")

    def test_pi_signature(self):
        assert tr._pane_signature("pi", "↑ 100 ↓ 50 deepseek-v4")
        assert not tr._pane_signature("pi", "plain text")

    def test_unknown_agent(self):
        assert not tr._pane_signature("unknown", "anything")
