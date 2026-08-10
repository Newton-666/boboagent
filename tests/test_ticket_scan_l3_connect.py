"""TICKET-SCAN-L3 验收测试：/scan → 确认 → 自动互传 + 发送前复核 + 安全闸。

覆盖验收 5 条中的逻辑层（用 mock 隔离真实 tmux 与引擎）：
  1. /scan 列出候选（bobo/pi 列出，unknown 不列）
  2. /connect 确认后建通道（成功/失败回报）
  3. 发送前复核：身份变化 → 拒绝并报错
  4. unknown pane 永不成为发送目标（scan 过滤 + connect 白名单）
  5. 回归：prompts.py 其他 slash 分支不受影响
"""
import json
import sys
import types
from unittest import mock

import pytest

sys.path.insert(0, ".")
from bobo_tui_gateway.handlers import prompts


# ── mock ctx ──

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
    return ctx


def fake_candidate(pane="sess:0.1", kind="pi", cwd="/tmp", lstart="Aug 10 13:00"):
    return {"pane": pane, "pid": "123", "cmd": "node", "title": "π",
            "kind": kind, "kind_src": "cmd", "match_pid": "456",
            "match_cmd": "pi", "lstart": lstart, "cwd": cwd}


# ── 验收 1：/scan 列出候选，unknown 不列 ──

class TestScan:
    def test_lists_bobo_and_pi_skips_unknown(self):
        ctx = make_ctx()
        results = [
            fake_candidate(pane="a:0.0", kind="bobo"),
            fake_candidate(pane="a:0.1", kind="pi"),
            fake_candidate(pane="a:0.2", kind="unknown"),
        ]
        with mock.patch("tools.agent_scan.scan", return_value=results):
            resp = prompts.handle_slash_exec({"command": "scan", "session_id": "s1"}, "r1", ctx)
        out = resp["result"]["output"]
        assert "[BOBO]" in out and "a:0.0" in out
        assert "[PI]" in out and "a:0.1" in out
        assert "unknown" not in out  # unknown 不列
        assert "a:0.2" not in out
        assert "/connect" in out  # 提示连接方式
        # 候选已暂存
        assert len(ctx.scan_candidates["s1"]) == 2
        assert all(c["kind"] in ("bobo", "pi") for c in ctx.scan_candidates["s1"])

    def test_no_candidates(self):
        ctx = make_ctx()
        with mock.patch("tools.agent_scan.scan", return_value=[fake_candidate(kind="unknown")]):
            resp = prompts.handle_slash_exec({"command": "scan", "session_id": "s1"}, "r1", ctx)
        out = resp["result"]["output"]
        assert "未发现可对话对象" in out

    def test_scan_error_reported(self):
        ctx = make_ctx()
        with mock.patch("tools.agent_scan.scan", side_effect=RuntimeError("boom")):
            resp = prompts.handle_slash_exec({"command": "scan", "session_id": "s1"}, "r1", ctx)
        assert "执行失败" in resp["result"]["output"]


# ── 验收 2+3+4：/connect 确认建通道、复核、安全闸 ──

class TestConnect:
    def test_connect_requires_scan_first(self):
        ctx = make_ctx()
        resp = prompts.handle_slash_exec({"command": "connect 1", "session_id": "s1"}, "r1", ctx)
        assert "请先运行 /scan" in resp["result"]["output"]

    def test_connect_rejects_non_numeric(self):
        ctx = make_ctx()
        ctx.scan_candidates["s1"] = [fake_candidate()]
        resp = prompts.handle_slash_exec({"command": "connect abc", "session_id": "s1"}, "r1", ctx)
        assert "编号必须是数字" in resp["result"]["output"]

    def test_connect_rejects_out_of_range(self):
        ctx = make_ctx()
        ctx.scan_candidates["s1"] = [fake_candidate()]
        resp = prompts.handle_slash_exec({"command": "connect 5", "session_id": "s1"}, "r1", ctx)
        assert "编号超出范围" in resp["result"]["output"]

    def test_connect_rejects_when_identity_changed(self):
        """验收 3：发送前复核失败 → 拒绝并报错"""
        ctx = make_ctx()
        ctx.scan_candidates["s1"] = [fake_candidate(pane="x:0.1", kind="pi")]
        with mock.patch("tools.agent_connect.verify_pane_identity",
                        return_value=(False, "pane x:0.1 身份已从 pi 变为 unknown")):
            resp = prompts.handle_slash_exec({"command": "connect 1", "session_id": "s1"}, "r1", ctx)
        out = resp["result"]["output"]
        assert "身份已变化" in out
        assert "已中止" in out
        assert "x:0.1" not in ctx.relay_links  # 未建立连接

    def test_connect_rejects_duplicate_link(self):
        """同会话已有连接 → 拒绝重复"""
        ctx = make_ctx()
        ctx.scan_candidates["s1"] = [fake_candidate()]
        ctx.relay_links["s1"] = {"target_pane": "x:0.1", "target_kind": "pi",
                                 "thread": mock.MagicMock()}
        with mock.patch("tools.agent_connect.verify_pane_identity", return_value=(True, "")):
            resp = prompts.handle_slash_exec({"command": "connect 1", "session_id": "s1"}, "r1", ctx)
        assert "已有互传通道" in resp["result"]["output"]

    def test_connect_success_starts_thread(self):
        """验收 2：确认后建立互传（后台线程启动，返回明确回报）"""
        ctx = make_ctx()
        cand = fake_candidate(pane="x:0.1", kind="pi")
        ctx.scan_candidates["s1"] = [cand]
        fake_thread = mock.MagicMock()
        with mock.patch("tools.agent_connect.verify_pane_identity", return_value=(True, "")), \
             mock.patch("threading.Thread", return_value=fake_thread) as m_thread:
            resp = prompts.handle_slash_exec({"command": "connect 1 3", "session_id": "s1"}, "r1", ctx)
        out = resp["result"]["output"]
        assert "已连接 pi" in out
        assert "x:0.1" in out
        assert "3 轮" in out
        # 线程已启动，relay_links 已记录
        fake_thread.start.assert_called_once()
        assert ctx.relay_links["s1"]["target_pane"] == "x:0.1"
        assert ctx.relay_links["s1"]["target_kind"] == "pi"
        # 线程参数：run_relay_thread(sid, target, rounds, emit)
        args = m_thread.call_args.kwargs["args"]
        assert args[0] == "s1"
        assert args[1] == cand
        assert args[2] == 3

    def test_connect_default_rounds_5(self):
        ctx = make_ctx()
        ctx.scan_candidates["s1"] = [fake_candidate()]
        fake_thread = mock.MagicMock()
        with mock.patch("tools.agent_connect.verify_pane_identity", return_value=(True, "")), \
             mock.patch("threading.Thread", return_value=fake_thread) as m_thread:
            prompts.handle_slash_exec({"command": "connect 1", "session_id": "s1"}, "r1", ctx)
        assert m_thread.call_args.kwargs["args"][2] == 5

    def test_connect_no_args_lists_hint(self):
        ctx = make_ctx()
        ctx.scan_candidates["s1"] = [fake_candidate(pane="x:0.1", kind="pi")]
        resp = prompts.handle_slash_exec({"command": "connect", "session_id": "s1"}, "r1", ctx)
        out = resp["result"]["output"]
        assert "用法" in out and "x:0.1" in out


class TestVerifyIdentity:
    """发送前复核（Kimi 补丁③）核心逻辑"""

    def test_pane_missing_rejected(self):
        from tools.agent_connect import verify_pane_identity
        with mock.patch("tools.agent_scan.pane_pid", return_value=""):
            ok, reason = verify_pane_identity({"pane": "gone:0.1", "kind": "pi"})
        assert not ok
        assert "已不存在" in reason

    def test_identity_changed_rejected(self):
        from tools.agent_connect import verify_pane_identity
        with mock.patch("tools.agent_scan.pane_pid", return_value="999"), \
             mock.patch("tools.agent_scan.process_tree", return_value=[("999", "vim")]), \
             mock.patch("tools.agent_scan.classify_by_cmd", return_value=("unknown", "", "")):
            ok, reason = verify_pane_identity({"pane": "x:0.1", "kind": "pi"})
        assert not ok
        assert "身份已从 pi 变为 unknown" in reason

    def test_identity_matches_ok(self):
        from tools.agent_connect import verify_pane_identity
        with mock.patch("tools.agent_scan.pane_pid", return_value="999"), \
             mock.patch("tools.agent_scan.process_tree", return_value=[("999", "pi")]), \
             mock.patch("tools.agent_scan.classify_by_cmd", return_value=("pi", "999", "pi")):
            ok, reason = verify_pane_identity({"pane": "x:0.1", "kind": "pi"})
        assert ok
        assert reason == ""

    def test_unknown_kind_never_passes(self):
        """安全闸：unknown 候选即使 classify 也是 unknown 也不放行"""
        from tools.agent_connect import verify_pane_identity
        with mock.patch("tools.agent_scan.pane_pid", return_value="999"), \
             mock.patch("tools.agent_scan.process_tree", return_value=[("999", "vim")]), \
             mock.patch("tools.agent_scan.classify_by_cmd", return_value=("unknown", "", "")):
            ok, reason = verify_pane_identity({"pane": "x:0.0", "kind": "unknown"})
        assert not ok
        assert "unknown 永不通过复核" in reason

    def test_empty_kind_rejected(self):
        from tools.agent_connect import verify_pane_identity
        ok, reason = verify_pane_identity({"pane": "x:0.0", "kind": ""})
        assert not ok
        assert "身份无效" in reason


class TestSendSafe:
    """安全闸（L3-4）：身份变化时拒绝发送"""

    def test_identity_changed_raises(self):
        from tools.agent_connect import send_safe
        with mock.patch("tools.agent_connect.verify_pane_identity",
                        return_value=(False, "pane x:0.1 身份已从 pi 变为 unknown")):
            with pytest.raises(RuntimeError, match="身份已变化"):
                send_safe("x:0.1", "hello", {"pane": "x:0.1", "kind": "pi"})

    def test_identity_ok_sends(self):
        from tools.agent_connect import send_safe
        with mock.patch("tools.agent_connect.verify_pane_identity", return_value=(True, "")), \
             mock.patch("tools.agent_connect._send_keys") as m_send:
            send_safe("x:0.1", "hello", {"pane": "x:0.1", "kind": "pi"})
        m_send.assert_called_once_with("x:0.1", "hello")


class TestRegression:
    """验收 5：既有 slash 分支零回归"""

    def test_help_still_works(self):
        ctx = make_ctx()
        resp = prompts.handle_slash_exec({"command": "help", "session_id": "s1"}, "r1", ctx)
        assert "/scan" in resp["result"]["output"]
        assert "/connect" in resp["result"]["output"]
        assert "/duo" in resp["result"]["output"]

    def test_commands_catalog_includes_new(self):
        resp = prompts.handle_commands_catalog({}, "r1")
        canon = resp["result"]["commands"]["canon"]
        assert "/scan" in canon
        assert "/connect" in canon
        assert "/disconnect" in canon
        assert "/duo" in canon  # 旧命令仍在

    def test_unknown_command_still_handled(self):
        ctx = make_ctx()
        resp = prompts.handle_slash_exec({"command": "nonsense", "session_id": "s1"}, "r1", ctx)
        assert "未知命令" in resp["result"]["output"]
