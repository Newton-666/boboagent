"""TICKET-SCAN-L4 验收测试：轮次自主 + 持久多模式（键盘选择器见前端 vitest）。

覆盖验收：
  1. 简单话题（如"1+1 等于几"）→ 自主评估 ≤2 轮，不跑满 5
  2. 用户明确"5 轮"→ 从用户 5 轮（提前收敛则说明原因）
  4. 连接后连续丢 2 个话题 → 各自独立评估轮次、上下文连续、无需重连
  5. 每轮开屏有"预计 N 轮（上限 5）"明示
  6. 多模式关闭零变化（延续 L3c 断言）；auto 环零回归（全量 pytest）

用 mock 隔离真实 tmux 与引擎（与 SCAN-L3/L3b/L3c 测试同风格）。
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


def fake_candidate(pane="x:0.1", kind="pi", cwd="/tmp", lstart="Aug 10 13:00"):
    return {"pane": pane, "pid": "123", "cmd": "node", "title": "π",
            "kind": kind, "kind_src": "cmd", "match_pid": "456",
            "match_cmd": "pi", "lstart": lstart, "cwd": cwd}


def wait_until(cond, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if cond():
            return True
        time.sleep(0.02)
    return False


# ── 验收 1/2：轮次评估（estimate_rounds）──

class TestEstimateRounds:
    def test_simple_question_two_rounds(self):
        """简单问答（'1+1 等于几'）→ 2 轮，不跑满 5。"""
        assert agent_connect.estimate_rounds("1+1 等于几") == 2
        assert agent_connect.estimate_rounds("你能看到吗") == 2
        assert agent_connect.estimate_rounds("确认") == 2

    def test_complex_five_rounds(self):
        """复杂设计/辩论 → 5 轮（上限）。"""
        assert agent_connect.estimate_rounds("如何设计高可用架构") == 5
        assert agent_connect.estimate_rounds("对比两种方案并给出选型建议") == 5

    def test_opinion_three_rounds(self):
        """普通观点讨论 → 3 轮。"""
        assert agent_connect.estimate_rounds("你觉得这个话题怎么样") == 3

    def test_user_specified_wins(self):
        """用户明确指定轮数 → 从用户（跳过评估）。"""
        assert agent_connect.estimate_rounds("1+1 等于几", 5) == 5
        assert agent_connect.estimate_rounds("复杂话题", 1) == 1

    def test_user_specified_capped(self):
        """硬上限 5：超上限截断，下限 1。"""
        assert agent_connect.estimate_rounds("x", 99) == 5
        assert agent_connect.estimate_rounds("x", 0) == 1
        assert agent_connect.estimate_rounds("x", "abc") == 5  # 非法值兜底 5

    def test_empty_topic(self):
        assert agent_connect.estimate_rounds("") == 1
        assert agent_connect.estimate_rounds(None) == 1


class TestShouldConverge:
    def test_converge_markers(self):
        assert agent_connect.should_converge("好，我们达成共识了。")
        assert agent_connect.should_converge("无新观点，讨论结束。")
        assert agent_connect.should_converge("这个问题已解决。")

    def test_no_converge(self):
        assert not agent_connect.should_converge("我不同意，需要再分析。")
        assert not agent_connect.should_converge("")


# ── 验收 4/5：持久多模式（多话题循环 + 开屏明示）──

class TestRelayMultiTopic:
    def _start_relay(self, emitted, rounds=None):
        """启动 API 直采 relay 线程（mock tmux），返回 (t, sent, patches)。"""
        sent = []
        patches = [
            mock.patch("tools.agent_connect.find_own_pane", return_value=None),
            mock.patch("tools.agent_connect.cap", return_value=""),
            mock.patch("tools.agent_connect.send_safe",
                       side_effect=lambda pane, text, cand: sent.append((pane, text))),
            mock.patch("tools.agent_connect.wait_pi_finished", return_value="pi 回复正文"),
        ]
        for p in patches:
            p.start()
        t = threading.Thread(
            target=agent_connect.run_relay_thread,
            args=("s1", fake_candidate(), rounds,
                  lambda ev, s, d: emitted.append(d.get("text", ""))),
            kwargs={"engine_runner": lambda text: "我们达成共识了。"},
            daemon=True,
        )
        t.start()
        return t, sent, patches

    def test_two_topics_independent_rounds_no_reconnect(self):
        """验收 4/5：连续丢 2 个话题 → 各自独立评估轮次、无需重连、开屏明示。"""
        emitted = []
        sid = "s1"
        t, sent, patches = self._start_relay(emitted)
        try:
            assert wait_until(lambda: relay_hooks.is_active(sid)), "API 模式应注册 hooks"

            # 话题 1：简单问答 → 预计 2 轮
            relay_hooks.push_user_input(sid, "1+1 等于几")
            assert wait_until(lambda: any("互传结束" in e for e in emitted)), "话题1 应互传结束"

            # 话题 2：复杂设计 → 预计 5 轮（同一连接，无需重连）
            relay_hooks.push_user_input(sid, "如何设计高可用架构")
            assert wait_until(lambda: sum(1 for e in emitted if "互传结束" in e) >= 2), "话题2 应互传结束"

            # 连接保持：线程仍活跃、hooks 仍注册
            assert relay_hooks.is_active(sid), "持久多模式：连接常驻不销毁"
            assert t.is_alive(), "relay 线程应常驻等待下一话题"

            # 开屏明示（验收 5）
            stream = "\n".join(emitted)
            assert "本话题预计 2 轮（上限 5）" in stream, "简单话题必须明示 2 轮"
            assert "本话题预计 5 轮（上限 5）" in stream, "复杂话题必须明示 5 轮"

            # 发送序列：话题1 + 收敛回复 + 话题2 + 收敛回复（提前收敛各 1 轮）
            assert len(sent) == 4, f"发送序列={sent}"
            assert sent[0][1] == "1+1 等于几" and sent[2][1] == "如何设计高可用架构"
            assert "达成共识" in sent[1][1] and "达成共识" in sent[3][1]

            # 提前收敛说明（验收 2 精神：说明原因）
            assert "提前结束" in stream, "收敛时须说明提前结束"
        finally:
            relay_hooks.unregister(sid)  # 释放 → 线程退出
            t.join(timeout=5)
            for p in patches:
                p.stop()

    def test_user_specified_rounds_respected(self):
        """验收 2：用户明确指定轮数（rounds=5）→ 从用户；收敛则说明未跑满。"""
        emitted = []
        sid = "s-u"
        sent = []
        patches = [
            mock.patch("tools.agent_connect.find_own_pane", return_value=None),
            mock.patch("tools.agent_connect.cap", return_value=""),
            mock.patch("tools.agent_connect.send_safe",
                       side_effect=lambda pane, text, cand: sent.append((pane, text))),
            mock.patch("tools.agent_connect.wait_pi_finished", return_value="pi 回复正文"),
        ]
        for p in patches:
            p.start()
        try:
            t = threading.Thread(
                target=agent_connect.run_relay_thread,
                args=("s-u", fake_candidate(), 5,  # 用户显式 5 轮
                      lambda ev, s, d: emitted.append(d.get("text", ""))),
                kwargs={"engine_runner": lambda text: "我们达成共识了。"},
                daemon=True,
            )
            t.start()
            assert wait_until(lambda: relay_hooks.is_active(sid))
            relay_hooks.push_user_input(sid, "1+1 等于几")
            assert wait_until(lambda: any("互传结束" in e for e in emitted)), "应互传结束"
            stream = "\n".join(emitted)
            # 用户指定 5 轮 → 评估直接 5；收敛后说明未跑满
            assert "本话题预计 5 轮（上限 5）" in stream, "用户指定轮数必须从用户"
            assert "提前结束（第 1 轮，未跑满 5 轮）" in stream, "收敛必须说明未跑满"
        finally:
            relay_hooks.unregister(sid)
            t.join(timeout=5)
            for p in patches:
                p.stop()
