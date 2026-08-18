"""票 GUI-F25 专项测试 — Request 保存失败修复（前端错误吞掉 + 后端会话池兜底）。

覆盖（票验收专项五项）：
- F25-1 errMsg 三形态（node 实跑）：{code,message} 本体（connect() resolve 的实际
  形态）→ message；{error:{code,message}} 完整响应 → error.message；字符串直用；
  空/超时 {} → 'unknown'
- F25-2 池内正常：session.set_request 直接写字段（回归，Bug B 修复不破坏池内路径）
- F25-3 池外磁盘有 → 磁盘兜底加载并入池 + 写入成功（Bug B 主修复点）
- F25-4 池外磁盘无 → err "会话不存在"（且不入池）
- F25-5 前端对后端 err 显示真实消息：reqSave 收到 {code,message} 本体
  → toast 'Save failed: <真实消息>'（不再 'unknown'，Bug A 主修复点）
"""

import json
import re
import subprocess
import threading
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
INDEX = REPO / "apps" / "desktop" / "dist" / "index.html"


# ── 工具函数（对齐 F24 先例）─────────────────────────────────────────

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
        self.session_dir = Path("/tmp/f25-test")

    def load_session(self, sid):
        d = self._data.get(sid)
        return dict(d) if d else None


# ═══ F25-1：errMsg 三形态（node 实跑）════════════════════════════════

class TestErrMsg:

    def test_err_body_form(self):
        """{code,message} 本体（connect() 实际 resolve(msg.error) 的形态）→ message。"""
        html = INDEX.read_text(encoding="utf-8")
        fn = _extract_func(html, "errMsg")
        out = _run_node(fn + r"""
console.log('F25_1 ' + JSON.stringify([
  errMsg({ code: -32000, message: '会话不存在' }),
  errMsg({ error: { code: -32000, message: '会话不存在' } }),
  errMsg('plain string err'),
  errMsg({}),
  errMsg(null),
  errMsg({ code: -32000 }),
]));
""")
        got = json.loads(re.search(r"F25_1 (\[.*\])", out).group(1))
        assert got[0] == "会话不存在", "err 本体必须取 message（Bug A 主修复点）"
        assert got[1] == "会话不存在", "完整响应形态也兼容"
        assert got[2] == "plain string err", "字符串形态直用"
        assert got[3] == "unknown", "超时 resolve({}) → unknown（不误报成功）"
        assert got[4] == "unknown"
        assert got[5] == "unknown", "{code} 无 message → unknown（不误报）"

    def test_errmsg_present_and_first(self):
        """errMsg 函数已定义，且 reqSave/reqClear/loadSession 错误分支均调用它。"""
        html = INDEX.read_text(encoding="utf-8")
        assert "function errMsg(res)" in html
        # 旧式直查（res.error && res.error.message) || 'unknown'）必须清零——
        # 全部收敛到 errMsg（唯一合法引用在 errMsg 内部）
        bad_calls = re.findall(r"error\.message\)\s*\|\|\s*'unknown'", html)
        assert not bad_calls, f"旧式错误直查应清零，实际 {len(bad_calls)} 处"
        assert "Save failed: ' + errMsg(res)" in html
        assert "Clear failed: ' + errMsg(res)" in html


# ═══ F25-2：池内正常（回归）══════════════════════════════════════════

class TestPoolHit:

    def test_in_pool_write(self):
        """池内会话 → 直接写入（不触磁盘兜底，回归 F24 语义）。"""
        from bobo_tui_gateway.handlers.sessions import handle_session_set_request
        ctx = _FakeCtx({"s1": {"id": "s1", "title": "t", "messages": []}})
        r = handle_session_set_request(
            {"session_id": "s1", "request": {"roles": "R", "rules": "X"}}, "r1", ctx)
        assert "error" not in r
        assert ctx.sessions["s1"]["request"] == {"roles": "R", "rules": "X"}

    def test_in_pool_clear(self):
        """池内会话 Clear(null) → 删字段。"""
        from bobo_tui_gateway.handlers.sessions import handle_session_set_request
        ctx = _FakeCtx({"s1": {"id": "s1", "title": "t", "messages": [],
                               "request": {"roles": "R", "rules": "X"}}})
        r = handle_session_set_request({"session_id": "s1", "request": None}, "r1", ctx)
        assert "error" not in r
        assert "request" not in ctx.sessions["s1"]


# ═══ F25-3：池外磁盘有 → 兜底成功（Bug B 主修复点）═══════════════════

class TestPoolMissDiskHit:

    def test_loads_from_disk_into_pool(self, monkeypatch):
        """池外但磁盘有 → load_session 兜底 + 入池 + 写入 request。"""
        from bobo_tui_gateway.handlers import sessions as sess_mod
        monkeypatch.setattr(sess_mod, "_get_session_mgr", lambda: _FakeMgr({
            "s1": {"id": "s1", "title": "历史会话",
                   "created_at": "2026-08-01T10:00:00+00:00",
                   "messages": [{"role": "user", "content": "hi"}],
                   "user_named": True,
                   "request": {"roles": "旧角色", "rules": "旧规则"}},
        }))
        ctx = _FakeCtx({})  # 池空（模拟后端重启未 resume）
        r = sess_mod.handle_session_set_request(
            {"session_id": "s1", "request": {"roles": "新角色", "rules": "新规则"}}, "r1", ctx)
        assert "error" not in r, f"池外磁盘有应兜底成功: {r}"
        assert ctx.sessions["s1"]["request"] == {"roles": "新角色", "rules": "新规则"}
        # 入池结构对齐 resume：messages / user_named / created_at 均带回
        assert ctx.sessions["s1"]["messages"] == [{"role": "user", "content": "hi"}]
        assert ctx.sessions["s1"]["user_named"] is True
        assert ctx.sessions["s1"]["created_at"] > 0, "created_at 应转为 timestamp"

    def test_clear_on_pool_miss(self, monkeypatch):
        """池外磁盘有 request → Clear(null) 兜底加载后删除字段。"""
        from bobo_tui_gateway.handlers import sessions as sess_mod
        monkeypatch.setattr(sess_mod, "_get_session_mgr", lambda: _FakeMgr({
            "s1": {"id": "s1", "title": "t", "created_at": "",
                   "messages": [], "request": {"roles": "旧", "rules": "旧"}},
        }))
        ctx = _FakeCtx({})
        r = sess_mod.handle_session_set_request(
            {"session_id": "s1", "request": None}, "r1", ctx)
        assert "error" not in r
        assert "request" not in ctx.sessions["s1"], "Clear 应删除字段"

    def test_disk_request_overwritten(self, monkeypatch):
        """磁盘已有 request 旧值 → 新 Save 覆盖（不清除语义不破坏）。"""
        from bobo_tui_gateway.handlers import sessions as sess_mod
        monkeypatch.setattr(sess_mod, "_get_session_mgr", lambda: _FakeMgr({
            "s1": {"id": "s1", "title": "t", "created_at": "",
                   "messages": [], "request": {"roles": "旧", "rules": "旧"}},
        }))
        ctx = _FakeCtx({})
        r = sess_mod.handle_session_set_request(
            {"session_id": "s1", "request": {"roles": "新", "rules": ""}}, "r1", ctx)
        assert "error" not in r
        assert ctx.sessions["s1"]["request"] == {"roles": "新", "rules": ""}


# ═══ F25-4：池外磁盘无 → err ═════════════════════════════════════════

class TestPoolMissDiskMiss:

    def test_err_session_not_found(self, monkeypatch):
        """池外且磁盘无 → err "会话不存在"，且不入池（不制造幽灵会话）。"""
        from bobo_tui_gateway.handlers import sessions as sess_mod
        monkeypatch.setattr(sess_mod, "_get_session_mgr", lambda: _FakeMgr({}))
        ctx = _FakeCtx({})
        r = sess_mod.handle_session_set_request(
            {"session_id": "nope", "request": {"roles": "R"}}, "r1", ctx)
        assert "error" in r
        assert "会话不存在" in r["error"]["message"]
        assert "nope" not in ctx.sessions, "磁盘无不得入池"


# ═══ F25-5：前端对后端 err 显示真实消息（Bug A 主修复点）════════════

class TestFrontendRealError:

    def test_save_shows_real_message(self):
        """reqSave 收到 {code,message} 本体 → toast 'Save failed: 真实消息'（非 unknown）。"""
        html = INDEX.read_text(encoding="utf-8")
        err_fn = _extract_func(html, "errMsg")
        req_save = _extract_func(html, "reqSave")
        out = _run_node(err_fn + r"""
var _toasts = [];
var _els = {};
function getEl(id) {
  if (!_els[id]) _els[id] = { value:'', textContent:'', style:{display:'none'}, addEventListener:function(){} };
  return _els[id];
}
var document = { getElementById: getEl, addEventListener: function(){} };
var currentSessionId = 's1';
var currentRequest = null;
function call(m, p) { return Promise.resolve({ code: -32000, message: '会话不存在' }); }
function showToast(t, m) { _toasts.push([t, m]); }
function reqSyncFromSession(r) {}
function reqClosePanel() {}
""" + req_save + r"""
(async () => {
  await reqSave();
  console.log('F25_5 ' + JSON.stringify(_toasts));
})().catch(e => { console.error('ERR', e); process.exit(1); });
""")
        toasts = json.loads(re.search(r"F25_5 (\[.*\])", out).group(1))
        assert len(toasts) == 1
        assert toasts[0][0] == "fail"
        assert "unknown" not in toasts[0][1], "真实错误不得被吞成 unknown（Bug A）"
        assert "会话不存在" in toasts[0][1], "必须显示后端真实消息"

    def test_clear_shows_real_message(self):
        """reqClear 收到 {code,message} 本体 → toast 'Clear failed: 真实消息'。"""
        html = INDEX.read_text(encoding="utf-8")
        err_fn = _extract_func(html, "errMsg")
        req_clear = _extract_func(html, "reqClear")
        out = _run_node(err_fn + r"""
var _toasts = [];
var _els = {};
function getEl(id) {
  if (!_els[id]) _els[id] = { value:'', textContent:'', style:{display:'none'}, addEventListener:function(){} };
  return _els[id];
}
var document = { getElementById: getEl, addEventListener: function(){} };
var currentSessionId = 's1';
var currentRequest = null;
function call(m, p) { return Promise.resolve({ code: -32000, message: '磁盘无此会话' }); }
function showToast(t, m) { _toasts.push([t, m]); }
function reqSyncFromSession(r) {}
function reqClosePanel() {}
""" + req_clear + r"""
(async () => {
  await reqClear();
  console.log('F25_6 ' + JSON.stringify(_toasts));
})().catch(e => { console.error('ERR', e); process.exit(1); });
""")
        toasts = json.loads(re.search(r"F25_6 (\[.*\])", out).group(1))
        assert len(toasts) == 1
        assert toasts[0][0] == "fail"
        assert "unknown" not in toasts[0][1]
        assert "磁盘无此会话" in toasts[0][1]

    def test_load_session_uses_errmsg(self):
        """loadSession 错误分支改用 errMsg：真实 err 显示真实消息，unknown 回退 unresponsive。"""
        html = INDEX.read_text(encoding="utf-8")
        ls = _extract_func(html, "loadSession")
        assert "errMsg(result)" in ls, "loadSession 错误分支应走 errMsg"
        assert "Backend unresponsive (timeout or disconnected)" in ls, "超时语义保留"
