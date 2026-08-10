"""TICKET-SCAN-L3c 验收测试：多模式输入路由三修（实弹抓获）。

覆盖验收：
  1. 多模式下用户输入不触发引擎（relay active → push 后 return，is_running=False，
     relay 队列收到原文；run_engine 不被调用）
  2. 转发给 pi 的文本不含思考段（strip_thinking 剥离 💭 块；relay 发送路径断言）
  3. pi 模拟脏屏幕（$ 命令/Took/spinner/提示符）→ 显示文本只剩回复正文（clean_pi_output）
  4. /disconnect 后输入立即恢复正常引擎路径（relay 未激活 → run_engine 被调用）
  5. 多模式关闭时行为零变化（relay inactive 时 submit 与旧路径一致）
  6. 回归：run_relay_thread API 直采全流程（话题直发 + bobo 接话 + 净化显示）

用 mock 隔离真实 tmux 与引擎（与 SCAN-L3/L3b 测试同风格）。
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


# ── 验收 2：思考剥离（strip_thinking）──

class TestStripThinking:
    def test_removes_thinking_block(self):
        """含 💭 块的回复 → 剥离思考段，只留正文。"""
        text = ("最终回复正文第一行。\n"
                "\n"
                "── 💭 思考过程 ──\n"
                "内部推理：应该先做 A 再做 B。\n"
                "── 思考结束 ──\n"
                "\n"
                "正文第二行。")
        cleaned = agent_connect.strip_thinking(text)
        assert "💭" not in cleaned, "思考标记不得出现在转发文本"
        assert "内部推理" not in cleaned, "思考内容不得外泄"
        assert "思考结束" not in cleaned
        assert "最终回复正文第一行。" in cleaned, "正文必须保留"
        assert "正文第二行。" in cleaned, "块后正文必须保留"

    def test_no_block_unchanged(self):
        """无思考块 → 原样返回（零变化）。"""
        text = "普通回复，没有思考块。"
        assert agent_connect.strip_thinking(text) == text

    def test_thinking_only_returns_empty(self):
        """只有思考块 → 返回空（转发方会跳过）。"""
        text = "── 💭 思考过程 ──\n秘密\n── 思考结束 ──"
        assert agent_connect.strip_thinking(text) == ""


# ── 验收 3：pi 输出净化（clean_pi_output）──

class TestCleanPiOutput:
    DIRTY = (
        "$ ls -la\n"
        "total 24\n"
        "drwxr-xr-x  5 pi  staff  160 Aug 10 13:00 .\n"
        "Took 0.42s\n"
        "ctrl+o expand\n"
        "pi@macbook:~/project$ \n"
        "⠹ 处理中\n"
        "这是 pi 的实际回复内容。\n"
        "(12 lines omitted)\n"
        "回复结束语。\n"
    )

    def test_dirty_screen_cleaned(self):
        """脏屏幕 → 只剩回复正文（命令回显/Took/提示符/spinner/省略提示全滤掉）。"""
        cleaned = agent_connect.clean_pi_output(self.DIRTY)
        assert "$ ls -la" not in cleaned, "命令回显必须滤掉"
        assert "Took 0.42s" not in cleaned, "工具耗时必须滤掉"
        assert "ctrl+o expand" not in cleaned, "编辑提示必须滤掉"
        assert "pi@macbook" not in cleaned, "提示符必须滤掉"
        assert "⠹" not in cleaned, "spinner 必须滤掉"
        assert "lines omitted" not in cleaned, "行数省略提示必须滤掉"
        assert "这是 pi 的实际回复内容。" in cleaned, "正文必须保留"
        assert "回复结束语。" in cleaned, "结尾正文必须保留"

    def test_all_noise_returns_empty(self):
        """全噪音 → 返回空字符串（调用方显示占位，不倒垃圾）。"""
        noise = "$ echo hi\nTook 0.1s\n⠙ 等待\npi@mac:~\n"
        assert agent_connect.clean_pi_output(noise) == ""

    def test_clean_text_unchanged(self):
        """纯正文 → 原样保留。"""
        text = "pi 的干净回复。"
        assert agent_connect.clean_pi_output(text) == text

    def test_empty_input(self):
        assert agent_connect.clean_pi_output("") == ""


# ── 验收 1/4/5：路由闸（Bug 1）──

class TestRoutingGate:
    def test_relay_active_does_not_start_engine(self):
        """主犯修复：relay active 时 submit → push 后 return，run_engine 不被调用。"""
        ctx = make_ctx()
        ctx.sessions["s1"] = {"history": []}
        relay_hooks.register("s1")
        try:
            with mock.patch("bobo_tui_gateway.handlers.prompts._cancel_engine_and_wait",
                            return_value=True), \
                 mock.patch("core.engine_adapter.run_engine") as m_run:
                resp = prompts.handle_prompt_submit(
                    {"session_id": "s1", "text": "pi,你能看到吗"}, "r1", ctx)
            assert resp["result"]["ok"] is True
            assert resp["result"].get("relay") is True, "应标记 relay 路由"
            m_run.assert_not_called(), "relay active 时引擎不得启动（bobo 不抢答）"
            got = relay_hooks.poll_user_input("s1", 0.1)
            assert got == "pi,你能看到吗", "用户输入必须原样入 relay 队列"
            assert not ctx.active_engine_threads, "不得注册引擎线程"
        finally:
            relay_hooks.unregister("s1")

    def test_relay_inactive_normal_engine_path(self):
        """多模式关闭时行为零变化：relay 未激活 → 正常启动引擎。"""
        ctx = make_ctx()
        ctx.sessions["s1"] = {"history": []}
        with mock.patch("bobo_tui_gateway.handlers.prompts._cancel_engine_and_wait",
                        return_value=True), \
             mock.patch("core.engine_adapter.run_engine") as m_run:
            resp = prompts.handle_prompt_submit(
                {"session_id": "s1", "text": "普通话题"}, "r1", ctx)
        assert resp["result"]["ok"] is True
        m_run.assert_called_once(), "relay 关闭时引擎必须正常启动"
        assert relay_hooks.poll_user_input("s1", 0.05) is None, "未激活时不得入队"

    def test_disconnect_restores_normal_path(self):
        """验收 4：/disconnect 后输入立即恢复正常引擎路径（relay 释放后不拦截）。"""
        ctx = make_ctx()
        ctx.sessions["s1"] = {"history": []}
        relay_hooks.register("s1")
        relay_hooks.unregister("s1")  # 模拟 /disconnect 释放
        with mock.patch("bobo_tui_gateway.handlers.prompts._cancel_engine_and_wait",
                        return_value=True), \
             mock.patch("core.engine_adapter.run_engine") as m_run:
            resp = prompts.handle_prompt_submit(
                {"session_id": "s1", "text": "断开后的话题"}, "r1", ctx)
        assert resp["result"]["ok"] is True
        assert resp["result"].get("relay") is None, "断开后不得走 relay 路由"
        m_run.assert_called_once(), "断开后必须恢复引擎路径"
        assert relay_hooks.poll_user_input("s1", 0.05) is None, "断开后不得入队"


# ── 验收 2/3 的 relay 全流程（发送路径断言）──

class TestRelayFlowL3c:
    def test_forward_no_thinking_and_cleaned_pi(self):
        """relay 全流程：话题直发；bobo 回复剥思考；pi 脏屏净化后显示/转发。"""
        emitted = []
        sid, rounds = "s1", 2
        target = fake_candidate()
        dirty_pi = ("$ grep foo\n"
                    "Took 0.3s\n"
                    "pi 对话题的看法：值得深入。\n"
                    "pi@mac:~/x$ \n")
        bobo_with_thinking = ("── 💭 思考过程 ──\n"
                              "内部想法不应外泄。\n"
                              "── 思考结束 ──\n"
                              "bobo 的正式回应。")
        sent = []
        patches = [
            mock.patch("tools.agent_connect.find_own_pane", return_value=None),
            mock.patch("tools.agent_connect.cap", return_value=""),
            mock.patch("tools.agent_connect.send_safe",
                       side_effect=lambda pane, text, cand: sent.append((pane, text))),
            mock.patch("tools.agent_connect.wait_pi_finished", return_value=dirty_pi),
        ]
        for p in patches:
            p.start()
        try:
            # engine_runner 模拟 bobo 接话：返回含思考块的回复
            def _runner(text: str) -> str:
                return bobo_with_thinking

            t = threading.Thread(
                target=agent_connect.run_relay_thread,
                args=(sid, target, rounds,
                      lambda ev, s, d: emitted.append(d.get("text", ""))),
                kwargs={"engine_runner": _runner},
                daemon=True,
            )
            t.start()
            deadline = time.monotonic() + 5
            while not relay_hooks.is_active(sid) and time.monotonic() < deadline:
                time.sleep(0.02)
            relay_hooks.push_user_input(sid, "你觉得这个话题怎么样")
            t.join(timeout=30)
            assert not t.is_alive(), "relay 线程应在轮数用完后退出"

            # 发送序列：话题 + 2 次 bobo 接话（剥思考后）
            assert len(sent) == 3, f"发送序列={sent}"
            assert sent[0][1] == "你觉得这个话题怎么样", "话题直发 pi"
            for i in (1, 2):
                assert "💭" not in sent[i][1], "发送给 pi 的文本不得含思考块"
                assert "内部想法" not in sent[i][1], "思考内容不得外泄"
                assert sent[i][1] == "bobo 的正式回应。", "只发正文"

            # 显示流：pi 回复已净化（无 $ / Took / 提示符）；bobo 显示亦剥思考
            stream = "\n".join(emitted)
            assert "pi 对话题的看法：值得深入。" in stream, "pi 正文必须显示"
            assert "$ grep foo" not in stream, "命令回显不得显示"
            assert "Took 0.3s" not in stream, "工具耗时不得显示"
            assert "pi@mac" not in stream, "提示符不得显示"
            assert "💭" not in stream, "思考块不得出现在对话流"
            assert "bobo 的正式回应。" in stream
        finally:
            t.join(timeout=5)
            for p in patches:
                p.stop()
            relay_hooks.unregister(sid)

    def test_all_noise_pi_shows_placeholder(self):
        """pi 回复全噪音 → 显示占位 '[pi 输出解析中]'，不倒垃圾。"""
        emitted = []
        sid = "s-noise"
        target = fake_candidate()
        noise = "$ echo x\nTook 0.2s\n⠹ 等待\n"
        sent = []
        patches = [
            mock.patch("tools.agent_connect.find_own_pane", return_value=None),
            mock.patch("tools.agent_connect.cap", return_value=""),
            mock.patch("tools.agent_connect.send_safe",
                       side_effect=lambda pane, text, cand: sent.append((pane, text))),
            mock.patch("tools.agent_connect.wait_pi_finished", return_value=noise),
        ]
        for p in patches:
            p.start()
        try:
            t = threading.Thread(
                target=agent_connect.run_relay_thread,
                args=(sid, target, 1, lambda ev, s, d: emitted.append(d.get("text", ""))),
                kwargs={"engine_runner": lambda text: "bobo 接话"},
                daemon=True,
            )
            t.start()
            deadline = time.monotonic() + 5
            while not relay_hooks.is_active(sid) and time.monotonic() < deadline:
                time.sleep(0.02)
            relay_hooks.push_user_input(sid, "话题")
            t.join(timeout=30)
            stream = "\n".join(emitted)
            assert "[pi 输出解析中]" in stream, "全噪音必须显示占位"
            assert "$ echo x" not in stream and "⠹" not in stream, "噪音不得倒进对话流"
        finally:
            t.join(timeout=5)
            for p in patches:
                p.stop()
            relay_hooks.unregister(sid)
