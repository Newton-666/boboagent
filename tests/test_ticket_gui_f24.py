"""票 GUI-F24 专项测试 — Request 面板：会话级 Roles/Rules 设定与注入。

覆盖（票验收专项四项）：
- F24-1 RPC：session.set_request 写字段（roles/rules）/清空（null 删字段）/
  无效参数（非 dict 非 null → err）
- F24-2 带回：activate/resume 返回补 request 字段（无则 None）
- F24-3 注入：有 request 尾部动态块注入【会话请求】、无 request 零注入
  （对照 project_root 同款断言 + 前缀稳定红线）
- F24-4 前端：node 实跑 reqSave 调 session.set_request 参数、reqClear 传 null、
  reqSyncFromSession 摘要回显；静态断言 sendPrompt 零改动
"""

import json
import re
import subprocess
import threading
from pathlib import Path

import pytest

from core.injector import PromptInjector

REPO = Path(__file__).resolve().parent.parent
INDEX = REPO / "apps" / "desktop" / "dist" / "index.html"


# ── 工具函数 ──────────────────────────────────────────────────────────

def _extract_func(src: str, fname: str) -> str:
    """按 { } 括号配对提取 function <fname> 的完整源码。"""
    m = re.search(r"(?:async\s+)?function\s+" + fname + r"\s*\(", src)
    assert m, f"未找到 function {fname}"
    open_i = src.index("{", m.start())
    depth = 0
    for i in range(open_i, len(src)):
        c = src[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return src[m.start():i + 1]
    raise AssertionError(f"function {fname} 括号不闭合")


def _run_node(js: str) -> str:
    r = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        raise AssertionError(f"node 执行失败: {r.stderr}")
    return r.stdout


class _FakeCtx:
    """最小 ctx：sessions + lock（对齐 DESK-P1 测试先例）。"""

    def __init__(self, sessions):
        self.sessions = sessions
        self.sessions_lock = threading.Lock()
        self.auto_mode = {}
        self.office_state = {}
        self.current_engines = {}
        self.current_engines_lock = threading.Lock()
        self.set_current_sid = lambda sid: None


class _FakeMgr:
    """最小 session mgr：load_session 读 dict（磁盘版会话）。"""

    def __init__(self, data):
        self._data = data
        self.session_dir = Path("/tmp/f24-test")

    def load_session(self, sid):
        d = self._data.get(sid)
        return dict(d) if d else None


# ═══ F24-1：session.set_request RPC ═══════════════════════════════════

class TestSetRequestRPC:

    def test_write_roles_rules(self):
        from bobo_tui_gateway.handlers.sessions import handle_session_set_request
        ctx = _FakeCtx({"s1": {"id": "s1", "title": "t", "messages": []}})
        r = handle_session_set_request(
            {"session_id": "s1", "request": {"roles": "代码审查员", "rules": "全程中文"}}, "r1", ctx)
        assert "error" not in r
        assert ctx.sessions["s1"]["request"] == {"roles": "代码审查员", "rules": "全程中文"}
        assert r["result"]["request"] == {"roles": "代码审查员", "rules": "全程中文"}

    def test_write_partial_roles_only(self):
        """只给 roles 不给 rules → rules 空串（不报错，其余键忽略）。"""
        from bobo_tui_gateway.handlers.sessions import handle_session_set_request
        ctx = _FakeCtx({"s1": {"id": "s1", "title": "t", "messages": []}})
        r = handle_session_set_request(
            {"session_id": "s1", "request": {"roles": "R1", "extra": "ignored"}}, "r1", ctx)
        assert "error" not in r
        assert ctx.sessions["s1"]["request"] == {"roles": "R1", "rules": ""}

    def test_clear_removes_field(self):
        """request=null → 删字段（清除后 activate 返回 None，前端面板空）。"""
        from bobo_tui_gateway.handlers.sessions import handle_session_set_request
        ctx = _FakeCtx({"s1": {"id": "s1", "title": "t", "messages": [],
                               "request": {"roles": "R", "rules": "X"}}})
        r = handle_session_set_request({"session_id": "s1", "request": None}, "r1", ctx)
        assert "error" not in r
        assert "request" not in ctx.sessions["s1"]

    def test_invalid_request_type(self):
        """request 非 dict 非 null → err（无效参数）。"""
        from bobo_tui_gateway.handlers.sessions import handle_session_set_request
        ctx = _FakeCtx({"s1": {"id": "s1", "title": "t", "messages": []}})
        r = handle_session_set_request({"session_id": "s1", "request": "bad"}, "r1", ctx)
        assert "error" in r
        assert "request" not in ctx.sessions["s1"]

    def test_missing_session(self):
        from bobo_tui_gateway.handlers.sessions import handle_session_set_request
        ctx = _FakeCtx({})
        r = handle_session_set_request({"session_id": "nope", "request": {"roles": "R"}}, "r1", ctx)
        assert "error" in r

    def test_registered(self):
        """RPC 已注册（reg_method 挂接）。"""
        src = (REPO / "bobo_tui_gateway" / "handlers" / "sessions.py").read_text(encoding="utf-8")
        assert 'reg_method("session.set_request")' in src
        assert "handle_session_set_request" in src


# ═══ F24-2：activate/resume 带回 request ══════════════════════════════

class TestBringBack:

    def test_activate_returns_request(self):
        from bobo_tui_gateway.handlers.sessions import handle_session_activate
        ctx = _FakeCtx({"s1": {"id": "s1", "title": "t", "messages": [],
                               "request": {"roles": "R", "rules": "X"}}})
        r = handle_session_activate({"session_id": "s1"}, "r1", ctx)
        assert "error" not in r
        assert r["result"]["request"] == {"roles": "R", "rules": "X"}

    def test_activate_returns_none_when_absent(self):
        from bobo_tui_gateway.handlers.sessions import handle_session_activate
        ctx = _FakeCtx({"s1": {"id": "s1", "title": "t", "messages": []}})
        r = handle_session_activate({"session_id": "s1"}, "r1", ctx)
        assert "error" not in r
        assert r["result"]["request"] is None

    def test_resume_returns_request(self, monkeypatch):
        """resume 从磁盘版带回 request（引擎空闲路径，重启保留语义）。"""
        import core.engine_adapter as ea
        from bobo_tui_gateway.handlers import sessions as sess_mod
        monkeypatch.setattr(ea, "is_running", lambda sid: False)
        monkeypatch.setattr(sess_mod, "_get_session_mgr", lambda: _FakeMgr({
            "s1": {"id": "s1", "title": "t",
                   "messages": [{"role": "user", "content": "hi"}],
                   "request": {"roles": "审查员", "rules": "中文"}},
        }))
        r = sess_mod.handle_session_resume({"session_id": "s1"}, "r1", _FakeCtx({}))
        assert "error" not in r
        assert r["result"]["request"] == {"roles": "审查员", "rules": "中文"}
        # 内存重建也应带 request（activate 读取/后续 save 不丢）
        assert r["result"]["session_id"] == "s1"

    def test_resume_none_when_absent(self, monkeypatch):
        import core.engine_adapter as ea
        from bobo_tui_gateway.handlers import sessions as sess_mod
        monkeypatch.setattr(ea, "is_running", lambda sid: False)
        monkeypatch.setattr(sess_mod, "_get_session_mgr", lambda: _FakeMgr({
            "s1": {"id": "s1", "title": "t", "messages": []},
        }))
        r = sess_mod.handle_session_resume({"session_id": "s1"}, "r1", _FakeCtx({}))
        assert "error" not in r
        assert r["result"]["request"] is None


# ═══ F24-3：injector 有/无 request 对照 project_root ═══════════════════

class MockEngine:
    """最小 MockEngine：injector 所需属性 + F24 request（对齐 DESK-P1）。"""

    def __init__(self, project_root=None, request=None):
        self.history = [{"role": "user", "content": "hello world"}]
        self.current_user_input = "测试"
        self._pending_diff = ""
        self._compressing = False
        self._just_compressed = False
        self.tracker = type("T", (), {"_change_log": [], "_read_files": {}})()
        self.proactive = type(
            "P", (), {"inject_context": lambda self, msgs: msgs}
        )()
        self.skill_loader = type(
            "S", (), {"load_standards": lambda self, _r=None: []}
        )()
        self.project_root = project_root
        self.request = request


def _build(engine):
    return PromptInjector(engine).build_messages(
        system_prompt="You are Bobo.",
        user_input="测试",
        tools_schema=[],
        extra_categories=set(),
        session_id="f24-test",
    )


class TestRequestInjection:

    def test_no_request_zero_injection(self):
        """无 request → 注入段零出现（缓存前缀稳定红线）。"""
        msgs = _build(MockEngine(request=None))
        joined = "\n".join(str(m.get("content", "")) for m in msgs)
        assert "会话请求" not in joined, "无 request 时一字节都不许多"

    def test_with_request_injected_in_tail(self):
        """有 request → 尾部动态块注入【会话请求】角色/规则分行。"""
        msgs = _build(MockEngine(request={"roles": "代码审查员", "rules": "全程中文"}))
        joined = "\n".join(str(m.get("content", "")) for m in msgs)
        assert "【会话请求】" in joined
        assert "角色：代码审查员" in joined
        assert "规则：全程中文" in joined

    def test_prefix_stable_with_request(self):
        """有 request vs 无 request：history 区逐字节不动（注入段只在尾部动态块）。"""
        msgs_no = _build(MockEngine(request=None))
        msgs_yes = _build(MockEngine(request={"roles": "R", "rules": "X"}))
        assert len(msgs_no) == len(msgs_yes)
        for i in range(len(msgs_no) - 1):
            assert msgs_no[i] == msgs_yes[i], f"history 区第 {i} 条被改动——前缀稳定红线"
        last_no = str(msgs_no[-1].get("content", ""))
        last_yes = str(msgs_yes[-1].get("content", ""))
        assert "会话请求" not in last_no
        assert "【会话请求】" in last_yes

    def test_roles_only_injects_roles_line(self):
        """只有 roles 无 rules → request 块只含角色行（不注入空规则行）。"""
        msgs = _build(MockEngine(request={"roles": "R1", "rules": ""}))
        joined = "\n".join(str(m.get("content", "")) for m in msgs)
        assert "角色：R1" in joined
        # 提取【会话请求】块（到下一个【或文本结束），块内不得出现"规则："
        m = re.search(r"【会话请求】\n(.*?)(?=\n【|\Z)", joined, re.S)
        assert m, "应存在【会话请求】块"
        assert "规则：" not in m.group(1), "roles-only 时 request 块不应含空规则行"


# ═══ F24-4：前端 Request 面板（node 实跑 + 静态）══════════════════════

class TestFrontend:

    def test_panel_structure(self):
        """面板元素齐全：request-pill / roles / rules / 保存 / 清除 / 摘要。"""
        html = INDEX.read_text(encoding="utf-8")
        for frag in ('id="request-pill"', 'id="request-panel"', 'id="req-roles"',
                     'id="req-rules"', 'id="req-save"', 'id="req-clear"',
                     'id="req-summary"', "Request ▾"):
            assert frag in html, f"前端面板缺 {frag}"

    def test_save_calls_set_request(self):
        """保存调 session.set_request（携带 session_id + request）。"""
        html = INDEX.read_text(encoding="utf-8")
        assert "call('session.set_request', { session_id: currentSessionId, request: { roles: roles, rules: rules } })" in html

    def test_clear_sends_null(self):
        """清除 → request: null（后端删字段）。"""
        html = INDEX.read_text(encoding="utf-8")
        assert "call('session.set_request', { session_id: currentSessionId, request: null })" in html

    def test_load_session_syncs_request(self):
        """切会话 loadSession 回显 resume 带回的 request。"""
        html = INDEX.read_text(encoding="utf-8")
        assert "reqSyncFromSession(result.request)" in html

    def test_send_prompt_untouched(self):
        """sendPrompt 零改动：不重复传 request（后端会话注入，前端不传）。"""
        html = INDEX.read_text(encoding="utf-8")
        sp = _extract_func(html, "sendPrompt")
        assert "session.set_request" not in sp, "sendPrompt 不应触碰 set_request"
        assert "request" not in sp, "sendPrompt 不应携带 request 参数（后端注入）"

    def test_node_save_and_clear(self):
        """node 实跑：reqSave 调 call 参数正确 + reqClear 传 null + 摘要同步。"""
        html = INDEX.read_text(encoding="utf-8")
        req_save = _extract_func(html, "reqSave")
        req_clear = _extract_func(html, "reqClear")
        out = _run_node(r"""
var _calls = [];
var _synced = [];
var _els = {};
function getEl(id) {
  if (!_els[id]) _els[id] = { value:'', textContent:'', style:{display:'none'}, addEventListener:function(){} };
  return _els[id];
}
var document = { getElementById: getEl, addEventListener: function(){} };
var currentSessionId = 's1';
var currentRequest = null;
function call(m, p) { _calls.push([m, p]); return Promise.resolve({ session_id: 's1', request: p.request }); }
function showToast(t, m) {}
function reqSyncFromSession(r) { _synced.push(r); }
function reqClosePanel() {}
""" + req_save + "\n" + req_clear + r"""
(async () => {
  getEl('req-roles').value = ' 代码审查员 ';
  getEl('req-rules').value = '全程中文';
  await reqSave();
  getEl('req-roles').value = 'x';
  getEl('req-rules').value = 'y';
  await reqClear();
  console.log('NODE_F24_4 ' + JSON.stringify({ calls: _calls, synced: _synced }));
})().catch(e => { console.error('ERR', e); process.exit(1); });
""")
        m = re.search(r"NODE_F24_4 (\{.*\})", out)
        st = json.loads(m.group(1))
        assert st["calls"][0][0] == "session.set_request"
        assert st["calls"][0][1]["session_id"] == "s1"
        # trim 生效：' 代码审查员 ' → '代码审查员'
        assert st["calls"][0][1]["request"] == {"roles": "代码审查员", "rules": "全程中文"}
        assert st["calls"][1][0] == "session.set_request"
        assert st["calls"][1][1]["request"] is None, "清除必须传 request: null"
        # 保存后摘要同步（synced 收到保存值），清除后收到 null
        assert st["synced"][0] == {"roles": "代码审查员", "rules": "全程中文"}
        assert st["synced"][1] is None

    def test_esc_closes_panel(self):
        """Esc 优先级链含 request-panel 关闭（命令面板→明细卡→Request→中断）。"""
        html = INDEX.read_text(encoding="utf-8")
        # 全局 Esc 链里必须存在 request-panel 分支（在 stopThinking 之前）
        assert "document.getElementById('request-panel')" in html
        i_req = html.index("document.getElementById('request-panel')")
        i_stop = html.index("stopThinking();")
        assert i_req < i_stop, "Request 面板 Esc 关闭必须先于 stopThinking（不误中断）"
