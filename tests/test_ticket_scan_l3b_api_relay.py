"""TICKET-SCAN-L3b 验收测试：API 直采（免自身 tmux）+ 全透明互传显示。

覆盖验收：
  1. 非 tmux 环境 bobo 可发起连接（find_own_pane=None → API 直采模式，不中止）
  2. 互传内容逐句全文出现在对话流，BOBO/PI 双色加粗、零表情
  3. 对方仍走 tmux：发送前复核路径原样保留（send_safe 调用断言）
  4. /scan 显示自我状态行（pane 模式 / API 直采模式）
  5. 日志文件含全部通信全文（无 ANSI）
  6. 回归：relay_hooks 基础收发、prompts 挂接点

用 mock 隔离真实 tmux 与引擎（与 SCAN-L3 测试同风格）。
"""
import os
import sys
import threading
import time
import types
from unittest import mock

import pytest

sys.path.insert(0, ".")
from bobo_tui_gateway.handlers import prompts
from tools import agent_connect, relay_hooks

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ── 工具 ──

def make_ctx():
    ctx = types.SimpleNamespace()
    ctx.scan_candidates = {}
    ctx.relay_links = {}
    ctx.auto_mode = {}
    ctx.sessions = {}
    ctx.sessions_lock = mock.MagicMock()
    ctx.pending_confirm = {}
    ctx.pending_confirm_result = {}
    ctx.confirm_lock = mock.MagicMock()
    ctx.engine_cache = {}
    # handle_prompt_submit → run_engine args 引用的属性
    ctx.current_engines = {}
    ctx.current_engines_lock = mock.MagicMock()
    ctx.session_usage = {}
    ctx.session_usage_lock = mock.MagicMock()
    ctx.save_session_to_disk = lambda *a, **kw: None
    ctx.active_engine_threads = []
    ctx.engine_threads_lock = mock.MagicMock()
    return ctx


def fake_candidate(pane="x:0.1", kind="pi", cwd="/tmp", lstart="Aug 10 13:00"):
    return {"pane": pane, "pid": "123", "cmd": "node", "title": "π",
            "kind": kind, "kind_src": "cmd", "match_pid": "456",
            "match_cmd": "pi", "lstart": lstart, "cwd": cwd}


def run_relay_api(sid, target, rounds, emit, cap_value="", pi_reply="pi 的完整回复"):
    """以 API 直采模式启动 relay 线程（find_own_pane=None），返回线程 + 记录器。

    注意：mock 必须在线程存活期间保持（线程在后台跑，with 块退出即失效），
    所以这里手动 start()，由调用方在 join 后 stop()。
    """
    sent = []
    patches = [
        mock.patch("tools.agent_connect.find_own_pane", return_value=None),
        mock.patch("tools.agent_connect.cap", return_value=cap_value),
        mock.patch("tools.agent_connect.send_safe",
                   side_effect=lambda pane, text, cand: sent.append((pane, text))),
        mock.patch("tools.agent_connect.wait_pi_finished", return_value=pi_reply),
    ]
    for p in patches:
        p.start()
    t = threading.Thread(
        target=agent_connect.run_relay_thread,
        args=(sid, target, rounds, emit),
        daemon=True,
    )
    t.start()
    return t, sent, patches


def stop_patches(patches):
    for p in patches:
        p.stop()


# ── 验收 1：非 tmux 环境 bobo 可发起连接（API 直采模式全流程）──

class TestApiRelay:
    def test_api_mode_full_flow(self):
        """find_own_pane=None → 不中止；话题/回复经内部通道收发，发给对方。"""
        emitted = []
        sid, rounds = "s1", 2
        target = fake_candidate()
        # emit 签名：emit(event_type, sid, data)；取 data["text"] 进对话流
        t, sent, patches = run_relay_api(sid, target, rounds,
                                         lambda ev, s, d: emitted.append(d.get("text", "")))
        try:
            # 等线程 register 完成（API 模式入口）
            deadline = time.monotonic() + 5
            while not relay_hooks.is_active(sid) and time.monotonic() < deadline:
                time.sleep(0.02)

            assert relay_hooks.is_active(sid), "API 模式应注册 hooks（不因无 pane 中止）"

            # 用户话题 + bobo 回复（模拟 prompt.submit 与 engine complete 直取）
            topic1 = "帮我总结一下这个项目"
            reply1 = "项目总结：这是一个多 Agent 互传系统。" * 3  # 足够长的全文
            relay_hooks.push_user_input(sid, topic1)
            relay_hooks.push_bobo_reply(sid, reply1)
            # 第二轮
            topic2 = "第二轮话题"
            reply2 = "第二轮回复：" + "内容".join(str(i) for i in range(20))
            deadline = time.monotonic() + 20
            # 等线程已发送第一轮（进入第二轮等用户输入）再 push
            while time.monotonic() < deadline:
                if len(sent) >= 1:
                    break
                time.sleep(0.02)
            assert len(sent) >= 1, "第一轮应在超时前发出"
            relay_hooks.push_user_input(sid, topic2)
            relay_hooks.push_bobo_reply(sid, reply2)

            t.join(timeout=30)
            assert not t.is_alive(), "relay 线程应在 2 轮后自然退出"

            # 对方侧：两轮 bobo 回复都经 send_safe 发给 pi（发送前复核路径保留）
            assert len(sent) == 2, f"应发送 2 轮，实际 {len(sent)}"
            assert sent[0][0] == target["pane"] and sent[0][1] == reply1
            assert sent[1][0] == target["pane"] and sent[1][1] == reply2

            # 对话流：全文不裁剪 + 双色加粗 + 零表情
            stream = "\n".join(emitted)
            assert reply1 in stream, "bobo 回复全文必须出现在对话流（不裁剪）"
            assert reply2 in stream, "第二轮回复全文必须出现"
            assert "pi 的完整回复" in stream, "pi 回复全文必须出现"
            assert "\x1b[1;38;2;124;147;168m" in stream, "BOBO 行必须莫兰迪蓝加粗 (#7C93A8)"
            assert "\x1b[1;38;2;182;154;148m" in stream, "PI 行必须莫兰迪粉加粗 (#B69A94)"
            assert "\x1b[38;2;154;160;166m" in stream, "分隔线必须莫兰迪灰 (#9AA0A6)"
            assert "BOBO → PI" in stream and "PI → BOBO" in stream

            # hooks 已释放
            assert not relay_hooks.is_active(sid), "线程结束应 unregister hooks"
        finally:
            t.join(timeout=5)
            stop_patches(patches)
            relay_hooks.unregister(sid)

    def test_api_mode_timeout_no_input(self):
        """等用户话题超时（无输入）→ 停止并回报，不挂死。"""
        emitted = []
        sid = "s-to"
        target = fake_candidate()
        patches = [
            mock.patch("tools.agent_connect.find_own_pane", return_value=None),
            mock.patch("tools.agent_connect.cap", return_value=""),
            # 模拟 600s 超时（poll 返回 None）→ 线程应走超时停止路径，不挂死
            mock.patch("tools.relay_hooks.poll_user_input", return_value=None),
        ]
        for p in patches:
            p.start()
        try:
            t = threading.Thread(
                target=agent_connect.run_relay_thread,
                args=(sid, target, 1, lambda ev, s, d: emitted.append(d.get("text", ""))),
                daemon=True,
            )
            t.start()
            t.join(timeout=10)
            assert not t.is_alive(), "用户话题超时后线程应停止退出"
            assert any("未检测到输入" in m for m in emitted), "应回报超时停止"
            assert not relay_hooks.is_active(sid), "超时退出后 hooks 应释放"
        finally:
            stop_patches(patches)
            relay_hooks.unregister(sid)


# ── 验收 2：显示层——双色加粗、全文不裁剪、零表情 ──

class TestRelayDisplay:
    def test_relay_msg_line_bobo_blue_bold(self):
        line = agent_connect.relay_msg_line("BOBO", "PI", "14:32:05", "第一行\n第二行")
        assert "\x1b[1;38;2;124;147;168mBOBO → PI  14:32:05\x1b[0m" in line, "BOBO 头部行必须蓝加粗"
        assert "  第一行" in line and "  第二行" in line, "正文逐行缩进、不裁剪"

    def test_relay_msg_line_pi_pink_bold(self):
        line = agent_connect.relay_msg_line("PI", "BOBO", "14:33:12", "对方回复内容")
        assert "\x1b[1;38;2;182;154;148mPI → BOBO  14:33:12\x1b[0m" in line, "PI 头部行必须粉加粗"
        assert "对方回复内容" in line

    def test_relay_msg_line_full_text_uncut(self):
        """验收 2：全文不裁剪断言（超长回复完整保留）。"""
        long_text = "行" * 5000
        line = agent_connect.relay_msg_line("BOBO", "PI", "00:00:00", long_text)
        assert long_text in line, "5000 字长文必须完整保留"

    def test_relay_header_footer_muted_gray(self):
        head = agent_connect.relay_header_line("BOBO", "PI", "x:0.1", "14:00:00", 1, 5)
        assert "\x1b[38;2;154;160;166m" in head, "分隔线/状态行必须莫兰迪灰"
        assert "BOBO ↔ PI（x:0.1）" in head
        assert "第 1/5 轮" in head
        foot = agent_connect.relay_footer_line()
        assert "\x1b[38;2;154;160;166m" in foot
        assert "日志留底" in foot

    def test_strip_ansi_pure_text(self):
        """验收 5：日志文件为纯文本（无 ANSI）。"""
        colored = agent_connect.relay_msg_line("BOBO", "PI", "14:32:05", "正文")
        plain = agent_connect.strip_ansi(colored)
        assert "\x1b" not in plain
        assert "BOBO → PI  14:32:05" in plain
        assert "  正文" in plain

    def test_no_emoji_in_relay_lines(self):
        """零表情：头部行/分隔线不含 emoji。"""
        head = agent_connect.relay_header_line("BOBO", "PI", "x:0.1", "14:00:00", 1, 5)
        msg = agent_connect.relay_msg_line("PI", "BOBO", "14:00:00", "内容")
        foot = agent_connect.relay_footer_line()
        for block in (head, msg, foot):
            assert not any(ord(ch) > 0x1F600 for ch in block), f"互传显示不允许 emoji: {block[:40]}"


# ── 验收 4：/scan 自我状态行 ──

class TestScanSelfStatus:
    def test_scan_self_status_pane_mode(self):
        ctx = make_ctx()
        results = [fake_candidate(pane="a:0.0", kind="bobo"),
                   fake_candidate(pane="a:0.1", kind="pi")]
        with mock.patch("tools.agent_scan.scan", return_value=results), \
             mock.patch("tools.agent_connect.find_own_pane", return_value="a:0.0"):
            resp = prompts.handle_slash_exec({"command": "scan", "session_id": "s1"}, "r1", ctx)
        out = resp["result"]["output"]
        assert "当前 bobo：pane 模式（a:0.0）" in out

    def test_scan_self_status_api_mode(self):
        ctx = make_ctx()
        results = [fake_candidate(pane="a:0.1", kind="pi")]
        with mock.patch("tools.agent_scan.scan", return_value=results), \
             mock.patch("tools.agent_connect.find_own_pane", return_value=None):
            resp = prompts.handle_slash_exec({"command": "scan", "session_id": "s1"}, "r1", ctx)
        out = resp["result"]["output"]
        assert "当前 bobo：API 直采模式 ✓（无需 tmux）" in out


# ── relay_hooks 基础 + 挂接点 ──

class TestRelayHooks:
    def test_register_push_poll_unregister(self):
        sid = "s-hook"
        relay_hooks.register(sid)
        assert relay_hooks.is_active(sid)
        relay_hooks.push_user_input(sid, "话题A")
        relay_hooks.push_bobo_reply(sid, "回复B")
        assert relay_hooks.poll_user_input(sid, 0.1) == "话题A"
        assert relay_hooks.poll_bobo_reply(sid, 0.1) == "回复B"
        assert relay_hooks.poll_user_input(sid, 0.05) is None, "取空后应返回 None"
        relay_hooks.unregister(sid)
        assert not relay_hooks.is_active(sid)

    def test_register_idempotent(self):
        sid = "s-dup"
        relay_hooks.register(sid)
        hook = relay_hooks.register(sid)
        assert hook is relay_hooks.register(sid)
        relay_hooks.unregister(sid)

    def test_push_without_hook_noop(self):
        # 无 hooks 时推送不报错、不残留
        relay_hooks.push_user_input("no-hook", "x")
        relay_hooks.push_bobo_reply("no-hook", "y")
        assert relay_hooks.poll_user_input("no-hook", 0.05) is None

    def test_drain(self):
        sid = "s-drain"
        relay_hooks.register(sid)
        relay_hooks.push_user_input(sid, "a")
        relay_hooks.push_user_input(sid, "b")
        relay_hooks.push_bobo_reply(sid, "c")
        assert relay_hooks.drain(sid) == (2, 1)
        relay_hooks.unregister(sid)


class TestPromptSubmitHook:
    def test_prompt_submit_pushes_user_input_when_relay_active(self):
        """挂接点：relay 激活时，prompt.submit 的文本直取入队。"""
        ctx = make_ctx()
        ctx.sessions["s1"] = {"history": []}
        relay_hooks.register("s1")
        try:
            with mock.patch("bobo_tui_gateway.handlers.prompts._cancel_engine_and_wait",
                            return_value=True), \
                 mock.patch("core.engine_adapter.run_engine"):
                resp = prompts.handle_prompt_submit(
                    {"session_id": "s1", "text": "直采话题"}, "r1", ctx)
            assert resp["result"]["ok"] is True
            got = relay_hooks.poll_user_input("s1", 0.1)
            assert got == "直采话题", "relay 激活时用户话题应入队"
        finally:
            relay_hooks.unregister("s1")

    def test_prompt_submit_ignores_when_relay_inactive(self):
        """挂接点：relay 未激活时不入队（零副作用）。"""
        ctx = make_ctx()
        ctx.sessions["s1"] = {"history": []}
        with mock.patch("bobo_tui_gateway.handlers.prompts._cancel_engine_and_wait",
                        return_value=True), \
             mock.patch("core.engine_adapter.run_engine"):
            resp = prompts.handle_prompt_submit(
                {"session_id": "s1", "text": "普通话题"}, "r1", ctx)
        assert resp["result"]["ok"] is True
        assert relay_hooks.poll_user_input("s1", 0.05) is None, "未激活时不得入队"


class TestEngineCompleteHook:
    def test_engine_complete_pushes_reply_when_relay_active(self):
        """挂接点：engine complete 事件在 relay 激活时直取 bobo 完整回复。"""
        import core.engine_adapter as ea
        sid = "s-eng"
        relay_hooks.register(sid)

        class _FakeEngine:
            """run() 触发 callback("complete", content) 的替身。"""

            def __init__(self, *a, **kw):
                self._callback = kw.get("callback")
                self.proactive = mock.MagicMock()
                self.checkpoint_mgr = mock.MagicMock()
                self.task_ledger = []
                self.history = []
                self._interrupt_event = None
                self._exit_reason = "completed"

            def run(self, text):
                self._callback("complete", {"content": "完整回复内容"})

            def __getattr__(self, name):
                return mock.MagicMock()

        emitted = []
        try:
            with mock.patch("core.engine.Engine", _FakeEngine):
                ea.run_engine(
                    sid, {"messages": []}, "hi",
                    lambda ev, s, d: emitted.append((ev, d)),
                    get_llm_caller=lambda: mock.MagicMock(),
                    get_context_length=lambda: 100000,
                    register_engine_thread=lambda t, a, l: None,
                    pending_confirm={}, pending_confirm_result={},
                    confirm_lock=mock.MagicMock(),
                    auto_mode={}, current_engines={},
                    current_engines_lock=mock.MagicMock(),
                    session_usage={}, session_usage_lock=mock.MagicMock(),
                    save_session_to_disk=lambda *a, **kw: None,
                )
            got = relay_hooks.poll_bobo_reply(sid, 0.1)
            assert got == "完整回复内容", "engine complete 事件应入队（bobo 回复直取）"
        finally:
            relay_hooks.unregister(sid)


# ── 回归：SCAN-L3 关键路径不破（pane 模式仍可运行）──

class TestPaneModeRegression:
    def test_pane_mode_still_works(self):
        """find_own_pane 有值 → pane 模式（兼容路径），不注册 hooks。"""
        emitted = []
        sid = "s-pane"
        target = fake_candidate()
        sent = []
        # cap 按 pane 分发：bobo 侧先空屏后出现 "> 话题"（阶段 0 通过），
        # target 侧出现 pi 回复（p_base 取样 + 完成块再取一次）
        caps_by_pane = {
            "b:0.0": iter(["", "> 话题\nbobo 回复"]),
            target["pane"]: iter(["pi 正在回复\npi 的完整回复", "pi 正在回复\npi 的完整回复"]),
        }
        patches = [
            mock.patch("tools.agent_connect.find_own_pane", return_value="b:0.0"),
            mock.patch("tools.agent_connect.cap",
                       side_effect=lambda pane: next(caps_by_pane[pane])),
            mock.patch("tools.agent_connect.send_safe",
                       side_effect=lambda pane, text, cand: sent.append((pane, text))),
            mock.patch("tools.agent_connect.wait_bobo_busy", return_value=True),
            mock.patch("tools.agent_connect.wait_pi_finished", return_value="pi 正在回复\npi 的完整回复"),
            mock.patch("tools.agent_connect.wait_bobo_ready", return_value="> 话题\nbobo 回复2"),
        ]
        for p in patches:
            p.start()
        try:
            t = threading.Thread(
                target=agent_connect.run_relay_thread,
                args=(sid, target, 1, lambda ev, s, d: emitted.append(d.get("text", ""))),
                daemon=True,
            )
            t.start()
            t.join(timeout=15)
            assert not t.is_alive(), "pane 模式线程应完成退出"
            assert len(sent) >= 1, "pane 模式应照常发送"
            assert not relay_hooks.is_active(sid), "pane 模式不注册 hooks"
        finally:
            stop_patches(patches)
            relay_hooks.unregister(sid)
