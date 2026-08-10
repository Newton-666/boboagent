"""TICKET-O2 验收测试：/office 开关 + office_manager 搭建器 + 新窗口自动打开。

覆盖（O2-5）：
1. /office 翻转 / 角色闸拒绝 / 会话隔离 / emit 事件 / resume 恢复
2. office_manager：launch 注入 BOBO_ROLE（mock execute_terminal 断言）、
   只动自建 session 红线、status 解析
3. 新窗口：TERM_PROGRAM 三分支 + 降级不炸
4. 普通模式对照组：无 office 状态，/office 外行为不变

全程 mock execute_terminal + 临时目录（registry/audit 不碰真实 data）。
"""

import os

import pytest

from bobo_tui_gateway.handlers import prompts as prompts_mod
from bobo_tui_gateway.handlers.prompts import handle_slash_exec


@pytest.fixture
def ctx():
    from bobo_tui_gateway.server import _ServerContext
    return _ServerContext()


# ── 1. /office 开关 ──

class TestOfficeSlash:
    def _exec(self, ctx, sid, command):
        return handle_slash_exec({"command": command, "session_id": sid}, "rid1", ctx)

    def test_office_toggles_on(self, ctx):
        r = self._exec(ctx, "o1", "office")
        assert ctx.office_state.get("o1", {}).get("on") is True
        assert "开启" in r["result"]["output"]

    def test_office_toggles_off(self, ctx):
        ctx.office_state["o2"] = {"on": True, "session": None}
        r = self._exec(ctx, "o2", "office")
        assert ctx.office_state["o2"]["on"] is False
        assert "关闭" in r["result"]["output"]

    def test_office_on_explicit(self, ctx):
        self._exec(ctx, "o3", "office on")
        assert ctx.office_state["o3"]["on"] is True

    def test_office_off_explicit(self, ctx):
        ctx.office_state["o4"] = {"on": True, "session": "office-x"}
        self._exec(ctx, "o4", "office off")
        assert ctx.office_state["o4"]["on"] is False

    def test_office_on_guide(self, ctx):
        """开 → 引导语（几个人配合/分工/几个窗口）"""
        r = self._exec(ctx, "o5", "office on")
        assert "OFFICE 模式" in r["result"]["output"]
        assert "几个人配合" in r["result"]["output"]

    def test_office_is_session_scoped(self, ctx):
        """会话隔离：一个会话开 office 不影响另一个会话"""
        self._exec(ctx, "sA", "office on")
        assert ctx.office_state.get("sB", {}).get("on", False) is False

    def test_office_registered_in_catalog(self):
        from bobo_tui_gateway.handlers.prompts import _COMMANDS
        assert "/office" in _COMMANDS["canon"]

    def test_office_emits_state_event_on(self, ctx, monkeypatch):
        """开 → 推送 session.office_state（on=True）"""
        emitted = []
        monkeypatch.setattr(
            "bobo_tui_gateway.handlers.prompts.emit",
            lambda event, sid, payload=None: emitted.append((event, sid, payload)),
        )
        self._exec(ctx, "o7", "office on")
        assert emitted[0][0] == "session.office_state"
        assert emitted[0][2]["on"] is True

    def test_office_emits_state_event_off(self, ctx, monkeypatch):
        """关 → 推送 session.office_state（on=False）"""
        emitted = []
        monkeypatch.setattr(
            "bobo_tui_gateway.handlers.prompts.emit",
            lambda event, sid, payload=None: emitted.append((event, sid, payload)),
        )
        self._exec(ctx, "o8", "office off")
        assert emitted[0][0] == "session.office_state"
        assert emitted[0][2]["on"] is False


# ── 2. 角色闸（员工拒绝）──

class TestOfficeRoleGuard:
    def _exec(self, ctx, sid, command, role):
        monkey = pytest.MonkeyPatch()
        if role:
            monkey.setenv("BOBO_ROLE", role)
        else:
            monkey.delenv("BOBO_ROLE", raising=False)
        try:
            return handle_slash_exec({"command": command, "session_id": sid}, "rid1", ctx)
        finally:
            monkey.undo()

    def test_staff_rejected(self, ctx, tmp_path, monkeypatch):
        """员工（BOBO_ROLE=staff）→ 拒绝 + 审计 office.guard"""
        # 审计路径改到临时目录，不碰真实 data
        monkeypatch.setattr(prompts_mod, "BOBO_DATA_DIR", tmp_path)
        r = self._exec(ctx, "g1", "office on", "staff")
        assert "员工没有这个命令" in r["result"]["output"]
        assert ctx.office_state.get("g1", {}).get("on", False) is False
        audit = (tmp_path / "office_audit.jsonl").read_text(encoding="utf-8")
        assert "office.guard" in audit
        assert "BOBO_ROLE=staff" in audit

    def test_dispatcher_rejected(self, ctx):
        r = self._exec(ctx, "g2", "office", "dispatcher")
        assert "员工没有这个命令" in r["result"]["output"]

    def test_owner_passes(self, ctx):
        """无 BOBO_ROLE（owner）→ 放行"""
        r = self._exec(ctx, "g3", "office on", "")
        assert ctx.office_state["g3"]["on"] is True
        assert "员工没有" not in r["result"]["output"]


# ── 3. resume 恢复 ──

class TestOfficeResume:
    def test_resume_returns_office_state(self, ctx, monkeypatch):
        """resume 带回 office_state（底栏指示跟随会话）"""
        from bobo_tui_gateway.handlers.sessions import handle_session_resume

        class FakeMgr:
            def load_session(self, sid):
                return {"title": "t", "created_at": "", "messages": []}

        monkeypatch.setattr(
            "bobo_tui_gateway.handlers.sessions._get_session_mgr",
            lambda: FakeMgr(),
        )
        ctx.office_state["r1"] = {"on": True, "session": "office-x"}
        r = handle_session_resume({"session_id": "r1"}, "rid1", ctx)
        assert r["result"]["office_state"] is True

        ctx.office_state["r1b"] = {"on": False, "session": None}
        r2 = handle_session_resume({"session_id": "r1b"}, "rid1", ctx)
        assert r2["result"]["office_state"] is False

    def test_activate_returns_office_state(self, ctx):
        from bobo_tui_gateway.handlers.sessions import handle_session_activate
        ctx.sessions["r2"] = {"messages": [], "title": "t", "created_at": ""}
        ctx.office_state["r2"] = {"on": True, "session": None}
        r = handle_session_activate({"session_id": "r2"}, "rid1", ctx)
        assert r["result"]["office_state"] is True


# ── 4. office_manager：launch 注入 BOBO_ROLE ──

class TestOfficeManagerLaunch:
    @pytest.fixture
    def om(self, tmp_path, monkeypatch):
        import tools.office_manager as om
        monkeypatch.setattr(om, "_REGISTRY_PATH", str(tmp_path / "registry.json"))
        monkeypatch.setattr(om, "_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
        # 全量 mock 命令执行：记录命令，返回成功（空输出）
        captured = []

        def fake_sh(cmd, timeout=30):
            captured.append(cmd)
            return ""

        monkeypatch.setattr(om, "_sh", fake_sh)
        # 新窗口：mock 为其他终端（降级路径，不触发 osascript）
        monkeypatch.setenv("TERM_PROGRAM", "vscode")
        om.env_ok = True
        return om, captured

    def test_launch_injects_bo_role(self, om):
        """launch 的员工 pane 启动命令注入 BOBO_ROLE"""
        om_mod, captured = om
        r = om_mod.launch(session="office-t", staff="bobo,hermes")
        joined = "\n".join(captured)
        assert "BOBO_ROLE=bobo" in joined
        assert "BOBO_ROLE=hermes" in joined
        # detached 建 session（skill 纪律）
        assert "tmux new-session -d -s office-t" in joined
        # relay 带 RELAY_SESSION（R1 参数化复用）
        assert "RELAY_SESSION=office-t" in joined
        assert "团队讨论结束" not in r  # 正常返回布局图

    def test_launch_injects_ticket(self, om):
        """有票时注入 BOBO_TICKET"""
        om_mod, captured = om
        om_mod.launch(session="office-t2", staff="bobo", ticket="T-1")
        joined = "\n".join(captured)
        assert "BOBO_TICKET=T-1" in joined

    def test_launch_registers_registry(self, om, tmp_path):
        """launch 后登记台账（teardown 红线的依据）"""
        om_mod, _ = om
        om_mod.launch(session="office-t3", staff="bobo")
        reg = om_mod._load_registry()
        assert "office-t3" in reg
        assert reg["office-t3"]["staff"] == ["bobo"]

    def test_launch_rejects_dup_session(self, om):
        om_mod, _ = om
        om_mod.launch(session="office-dup", staff="bobo")
        r = om_mod.launch(session="office-dup", staff="bobo")
        assert "已在台账中" in r

    def test_launch_rejects_too_many_staff(self, om):
        om_mod, _ = om
        r = om_mod.launch(session="office-big", staff="a,b,c,d,e")
        assert "最多 4 个员工" in r

    def test_launch_requires_session(self, om):
        om_mod, _ = om
        r = om_mod.launch(session="  ")
        assert "需要 session 参数" in r


# ── 5. office_manager：红线（只动自建 session）──

class TestOfficeManagerRedline:
    @pytest.fixture
    def om(self, tmp_path, monkeypatch):
        import tools.office_manager as om
        monkeypatch.setattr(om, "_REGISTRY_PATH", str(tmp_path / "registry.json"))
        monkeypatch.setattr(om, "_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
        # 预置一个自建 session
        om._save_registry({"office-mine": {"created_at": "t", "staff": ["bobo"]}})
        captured = []

        def fake_sh(cmd, timeout=30):
            captured.append(cmd)
            return ""

        monkeypatch.setattr(om, "_sh", fake_sh)
        return om, captured

    def test_teardown_rejects_foreign_session(self, om):
        """红线：teardown 指向非自建 session（如 bobo-pi-chat）→ 拒绝 + 审计"""
        om_mod, captured = om
        r = om_mod.teardown("bobo-pi-chat")
        assert "拒绝" in r
        assert "红线" in r
        assert captured == []  # 未执行任何 tmux 命令
        audit = open(om_mod._AUDIT_PATH, encoding="utf-8").read()
        assert "office.redline" in audit
        assert "bobo-pi-chat" in audit

    def test_teardown_allows_self_created(self, om):
        """自建 session → 放行：停 relay + 员工退出指令 + 审计"""
        om_mod, captured = om
        r = om_mod.teardown("office-mine", keep=True)
        assert "收尾完成" in r
        assert any("team_relay_v2.py" in c for c in captured)  # 停 relay
        assert any("send-keys" in c and "停止信号" in c for c in captured)  # 员工退出
        audit = open(om_mod._AUDIT_PATH, encoding="utf-8").read()
        assert "office.teardown" in audit
        # 台账已删（session 移交 owner）
        assert "office-mine" not in om_mod._load_registry()


# ── 6. office_manager：status ──

class TestOfficeManagerStatus:
    @pytest.fixture
    def om(self, tmp_path, monkeypatch):
        import tools.office_manager as om
        monkeypatch.setattr(om, "_REGISTRY_PATH", str(tmp_path / "registry.json"))
        monkeypatch.setattr(om, "_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
        return om

    def test_status_empty_registry(self, om):
        assert "尚无自建 office" in om.status()

    def test_status_lists_self_created(self, om, monkeypatch):
        om._save_registry({"office-s": {"created_at": "2026", "staff": ["bobo"],
                                        "layout": "even-horizontal"}})

        def fake_sh(cmd, timeout=30):
            if "has-session" in cmd:
                return "ALIVE"
            if "list-panes" in cmd:
                return "0 zsh\n1 zsh"
            return "1234"

        monkeypatch.setattr(om, "_sh", fake_sh)
        r = om.status()
        assert "office-s" in r
        assert "存活" in r

    def test_status_rejects_foreign(self, om):
        """status 指向非自建 session → 拒绝（红线一致）"""
        r = om.status("staff_office")
        assert "拒绝" in r


# ── 7. 新窗口：TERM_PROGRAM 三分支 + 降级 ──

class TestOpenNewWindow:
    @pytest.fixture
    def om(self, tmp_path, monkeypatch):
        import tools.office_manager as om
        monkeypatch.setattr(om, "_REGISTRY_PATH", str(tmp_path / "registry.json"))
        monkeypatch.setattr(om, "_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
        return om

    def test_apple_terminal_opens(self, om, monkeypatch):
        """Apple_Terminal → Terminal.app do script attach"""
        monkeypatch.setenv("TERM_PROGRAM", "Apple_Terminal")
        calls = []
        monkeypatch.setattr(om, "_sh",
                            lambda cmd, timeout=30: calls.append(cmd) or "")
        r = om._open_new_window("office-x")
        assert "新 Terminal 窗口" in r
        assert "osascript" in calls[0]
        assert "tmux attach -t office-x" in calls[0]

    def test_iterm_opens(self, om, monkeypatch):
        """iTerm.app → iTerm2 create window"""
        monkeypatch.setenv("TERM_PROGRAM", "iTerm.app")
        calls = []
        monkeypatch.setattr(om, "_sh",
                            lambda cmd, timeout=30: calls.append(cmd) or "")
        r = om._open_new_window("office-y")
        assert "iTerm2" in r
        assert "osascript" in calls[0]

    def test_other_terminal_degrades(self, om, monkeypatch):
        """vscode 等 → 降级：不失败，返回 attach 命令文本"""
        monkeypatch.setenv("TERM_PROGRAM", "vscode")
        r = om._open_new_window("office-z")
        assert "手动执行" in r
        assert "tmux attach -t office-z" in r

    def test_no_term_program_degrades(self, om, monkeypatch):
        """无 TERM_PROGRAM → 降级不炸"""
        monkeypatch.delenv("TERM_PROGRAM", raising=False)
        r = om._open_new_window("office-w")
        assert "手动执行" in r

    def test_osascript_error_degrades(self, om, monkeypatch):
        """osascript 报错 → 降级返回手动命令（不炸）"""
        monkeypatch.setenv("TERM_PROGRAM", "Apple_Terminal")
        monkeypatch.setattr(om, "_sh",
                            lambda cmd, timeout=30: "execution error: not allowed")
        r = om._open_new_window("office-v")
        assert "手动" in r


# ── 8. 普通模式对照组 ──

class TestOrdinaryModeControl:
    def test_no_office_state_by_default(self, ctx):
        """未开 /office：ctx.office_state 无该 sid（普通模式零影响）"""
        assert ctx.office_state.get("nobody", None) is None

    def test_help_includes_office(self, ctx):
        """/help 列出 /office（不影响其他命令）"""
        r = handle_slash_exec({"command": "help", "session_id": "h1"}, "rid1", ctx)
        assert "/office" in r["result"]["output"]
        assert "/auto" in r["result"]["output"]
