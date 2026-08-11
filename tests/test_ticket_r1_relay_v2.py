"""TICKET-R1 验收测试：relay v2 评审转正——结构化通道并入 main。

六条评审点逐一覆盖（先审后改，改动带票号注释）：
  1. 消息带 ID + 单调序号（断点续传/重放去重）
  2. 消费确认 ack（转发后标记已消费，防重复注入——v1 hermes 队列堆 10 条根因）
  3. 思考流（💭 块）不进通道（结构化通道只收正式发言）
  4. 空闲判定与内容提取分离（capture 只做 idle 判定，不做内容提取）
  5. unknown pane 永不通过身份复核（L3 铁律沿用）
  6. 会话名参数化（不硬编码，O-2 搭建器传不同 session 名）

全程 mock tmux + 临时目录，不碰真实 relay_v2 目录、不碰真实库。
"""

import importlib
import os
import sys

import pytest

sys.path.insert(0, ".")
import tools.team_relay_v2 as rv


# ── 评审点 1：ID + 单调序号 / 断点续传 / 重放去重 ──

class TestSeqAndResume:
    def test_write_inbox_seq_monotonic(self, tmp_path, monkeypatch):
        """连续写入 → 序号单调递增 0001/0002/0003（消息 ID = 文件名序号）"""
        monkeypatch.setattr(rv, "INBOX_ROOT", str(tmp_path / "inbox"))
        a1 = rv.write_inbox("bobo", "第一条")
        a2 = rv.write_inbox("bobo", "第二条")
        a3 = rv.write_inbox("bobo", "第三条")
        assert (a1, a2, a3) == (1, 2, 3)
        files = sorted(os.listdir(tmp_path / "inbox" / "bobo"))
        assert files == ["0001.md", "0002.md", "0003.md"]

    def test_read_new_inbox_resume_no_dup(self, tmp_path, monkeypatch):
        """断点续传：last_seq=1 → 只读 2,3，不重不丢"""
        monkeypatch.setattr(rv, "INBOX_ROOT", str(tmp_path / "inbox"))
        for i in range(1, 4):
            rv.write_inbox("hermes", f"msg{i}")
        got = rv.read_new_inbox("hermes", 1)
        assert [s for s, _ in got] == [2, 3]
        assert [t for _, t in got] == ["msg2", "msg3"]

    def test_read_new_inbox_after_ack_empty(self, tmp_path, monkeypatch):
        """ack 后（last_seq=3）→ 无新消息（重放去重）"""
        monkeypatch.setattr(rv, "INBOX_ROOT", str(tmp_path / "inbox"))
        for i in range(1, 4):
            rv.write_inbox("claude", f"msg{i}")
        assert rv.read_new_inbox("claude", 3) == []
        assert rv.read_new_inbox("claude", 5) == []


# ── 评审点 2：消费确认 ack（relay.state 持久化，防重复注入）──

class TestAckState:
    def test_state_roundtrip(self, tmp_path, monkeypatch):
        """save_state → load_state 往返一致（ack 标记持久化）"""
        monkeypatch.setattr(rv, "STATE_PATH", str(tmp_path / "relay.state"))
        st = {"bobo": 2, "hermes": 5, "claude": 0, "pi": 1}
        rv.save_state(st)
        assert rv.load_state() == st

    def test_load_state_default_all_zero(self, tmp_path, monkeypatch):
        """无 relay.state → 全 0（从未 ack，从头续传）"""
        monkeypatch.setattr(rv, "STATE_PATH", str(tmp_path / "nonexist" / "relay.state"))
        assert rv.load_state() == {"bobo": 0, "hermes": 0, "claude": 0, "pi": 0}

    def test_ack_prevents_reforward(self, tmp_path, monkeypatch):
        """转发→ack 后同一消息不再被读第二次（防重复注入）"""
        monkeypatch.setattr(rv, "INBOX_ROOT", str(tmp_path / "inbox"))
        monkeypatch.setattr(rv, "STATE_PATH", str(tmp_path / "relay.state"))
        rv.write_inbox("bobo", "only one")
        # 第一轮：last_seq=0 → 读到 1 条
        first = rv.read_new_inbox("bobo", 0)
        assert len(first) == 1
        # 转发后 ack：state["bobo"] = 该条序号
        st = rv.load_state()
        st["bobo"] = first[0][0]
        rv.save_state(st)
        # 第二轮：last_seq=1 → 空（不重复注入）
        assert rv.read_new_inbox("bobo", rv.load_state()["bobo"]) == []


# ── 评审点 3：思考流（💭 块）不进通道 ──

class TestThinkingStream:
    def test_clean_reply_filters_thinking(self):
        """💭 块被过滤，正式发言保留"""
        text = "💭 我在思考这个问题的答案……\n好的，我同意这个方案。"
        out = rv.clean_reply(text)
        assert "💭" not in out
        assert "我同意这个方案" in out

    def test_capture_reply_filters_thinking(self, monkeypatch):
        """摘录链路（diff→clean_reply）同样滤掉思考流"""
        before = "用户：你好\n💭 思考中……"
        after = "用户：你好\n💭 思考中……\n这是我的正式回复。"
        out = rv._capture_reply("bobo", before, after)
        assert "💭" not in out
        assert "正式回复" in out

    def test_clean_reply_filters_relay_injections(self):
        """relay 注入段（【来自…的发言】/【硬约束】）过滤，防回声"""
        text = "【来自 bobo 的发言】\n【硬约束·必须遵守】\n正式内容"
        out = rv.clean_reply(text)
        assert "【来自" not in out
        assert "【硬约束" not in out
        assert "正式内容" in out


# ── 评审点 4：空闲判定与内容提取分离 ──

class TestIdleVsContent:
    def test_bobo_idle_pure_status(self):
        """bobo 空闲判定只依赖状态（提示符 + 思考词），不提取内容"""
        busy_screen = "> 用户问题\n─ ● 状态 │ working on it"
        idle_screen = "> 用户问题\n─ ● 状态 │ ready"
        assert not rv.bobo_idle(busy_screen)
        assert rv.bobo_idle(idle_screen)

    def test_hermes_idle_pure_status(self):
        """hermes 空闲判定：提示符存在 + 状态行无忙碌标志（⏱ 活跃计时器）。

        2026-08-11 演练 1 修订：忙碌判定收窄到状态行——hermes 本人确认
        其 TUI 忙碌时不显示 "Working" 字样，真正忙碌标志是状态行 ⏱
        计时器（⏲ = 等待计时器 = 空闲）。全屏扫描会被历史发言文本污染
        （历史引用 Working/⏳ 字样 → 误判忙碌 → 转发卡死）。
        """
        busy_screen = "⚕ ❯ 输入 ⏱ 5s"
        idle_screen = "⚕ ❯ 输入 ⏲ 53s"
        assert not rv.hermes_idle(busy_screen)
        assert rv.hermes_idle(idle_screen)

    def test_pane_idle_fn_all_agents_callable(self):
        """pane_idle_fn 返回各 agent 的判定函数（screen→bool，无内容副作用）"""
        for name in rv.ORDER:
            fn = rv.pane_idle_fn(name)
            assert callable(fn)

    def test_capture_reply_separated_from_idle(self, monkeypatch):
        """idle 判定与内容提取在函数层面分离：判定函数不改内容，_capture_reply 才提取"""
        before = "A"
        after = "A\nB"
        # 判定：只看状态
        assert rv.bobo_idle("> ") is True
        # 提取：独立函数
        assert "B" in rv._capture_reply("bobo", before, after)


# ── 评审点 5：unknown pane 永不通过身份复核（L3 铁律沿用）──

class TestUnknownPane:
    def test_verify_target_pane_rejects_unknown(self, monkeypatch):
        """目标 pane 无预期身份特征 → 拒绝（unknown 永不通过复核）"""
        monkeypatch.setattr(rv, "cap", lambda pane: "随便什么程序界面，没有提示符")
        ok, reason, _ = rv.verify_target_pane("bobo")
        assert ok is False
        assert "unknown" in reason

    def test_verify_target_pane_accepts_matching(self, monkeypatch):
        """身份特征匹配 → 放行"""
        monkeypatch.setattr(rv, "cap", lambda pane: "> 等待输入\n── 状态 │ ready")
        ok, reason, screen = rv.verify_target_pane("bobo")
        assert ok is True
        assert reason == ""
        assert "等待输入" in screen

    def test_verify_target_pane_unknown_name(self, monkeypatch):
        """不存在的 agent 名 → 拒绝"""
        ok, reason, _ = rv.verify_target_pane("evil")
        assert ok is False
        assert "未知 agent" in reason

    def test_verify_all_four_agents(self, monkeypatch):
        """四个 agent 各自的身份特征都被识别"""
        screens = {
            "bobo": "> 输入\n─ ● 状态 │ ready",
            "hermes": "⚕ ❯ 输入指令",
            "claude": "❯ 等待输入",
            "pi": "↑ 10 ↓ 5 deepseek v4",
        }

        def fake_cap(pane):
            for name in screens:
                if pane == rv.PANES[name]:
                    return screens[name]
            return ""

        monkeypatch.setattr(rv, "cap", fake_cap)
        for name in rv.ORDER:
            ok, reason, _ = rv.verify_target_pane(name)
            assert ok, f"{name} 应通过复核: {reason}"


# ── 评审点 6：会话名参数化 ──

class TestSessionParam:
    def test_build_panes_parameterized(self):
        """会话名参数化：传不同 session → 不同 pane 映射（O-2 搭建器用）"""
        panes = rv.build_panes("my_session")
        assert panes == {
            "bobo": "my_session:0.0",
            "hermes": "my_session:0.1",
            "claude": "my_session:0.2",
            "pi": "my_session:0.3",
        }

    def test_ses_default(self):
        """默认会话名 staff_office（env 未设时兜底）"""
        assert rv.SES == os.environ.get("RELAY_SESSION", "staff_office")

    def test_ses_env_overridable(self, monkeypatch):
        """RELAY_SESSION env 覆盖默认值（多会话并存不串台）"""
        monkeypatch.setenv("RELAY_SESSION", "team2")
        mod = importlib.reload(rv)
        assert mod.SES == "team2"
        assert mod.PANES["bobo"] == "team2:0.0"
        # 手动还原 env 并 reload，恢复模块默认态（避免污染后续测试）
        monkeypatch.delenv("RELAY_SESSION", raising=False)
        importlib.reload(rv)
        assert rv.SES == "staff_office"


# ── 票 R1-1 附加：docstring 分工说明 ──

class TestDocstringDivision:
    def test_docstring_mentions_agent_connect_division(self):
        """文件头部 docstring 写明 v2 与 agent_connect 的分工边界"""
        doc = rv.__doc__ or ""
        assert "agent_connect" in doc
        assert "分工" in doc
        assert "什么时候用哪个" in doc
