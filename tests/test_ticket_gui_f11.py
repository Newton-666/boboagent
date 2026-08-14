"""TICKET-GUI-F11 回归测试 — 自动命名持久化（重启不丢，用户命名优先，TUI 同步）。

根因：自动命名只更新前端/内存（updateSessionTitle 本地改 sessions 数组），
未走 handle_session_rename 落盘通道（该通道会置 user_named=true，破坏 F7 语义）。

修法：handle_session_rename 加 auto 参数 —— auto=true 落盘标题但不置 user_named；
前端自动命名改调 session.rename { auto:true }。

覆盖（票验收）：
- F11-1 后端 pytest：
  ① auto 命名落盘重启后仍在（磁盘 title 持久化，不置 user_named）
  ② auto 不置 user_named（resume/list 返回 false，后续可再自动更新）
  ③ auto 不覆盖 user_named 会话（返回 ok 但 title 不动）
  ④ 手动 rename（无 auto）仍置 user_named=true（F7 语义不破）
- F11-2 node 实跑：提取真实 updateSessionTitle，桩化 sessions+call，
  断言自动命名调用 session.rename 且带 auto:true
- F11-3 静态断言：sessions.py handle_session_rename 含 auto 参数与防线
"""

import json
import re
import subprocess
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
GUI_FILE = ROOT / "apps" / "desktop" / "dist" / "index.html"
SESS_FILE = ROOT / "bobo_tui_gateway" / "handlers" / "sessions.py"


def _extract_func(src: str, fname: str) -> str:
    """按 { } 括号配对提取 function <fname> 的完整源码（含 async 前缀）。"""
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


# ── F11-1：后端持久化与 auto 语义 ─────────────────────────────────────

def _make_ctx():
    class FakeCtx:
        def __init__(self):
            self.sessions_lock = threading.Lock()
            self.sessions = {}
            self.auto_mode = {}
            self.office_state = {}
            self._current = None

        def set_current_sid(self, sid):
            self._current = sid

    return FakeCtx()


def _read_disk(mgr, sid):
    path = mgr.session_dir / f"{sid}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_f11_1_auto_rename_persists_without_user_named(monkeypatch, tmp_path):
    """① auto=true：标题落盘（重启后仍在），但不置 user_named（②）。"""
    from bobo_tui_gateway.handlers import sessions as sess_mod
    from core.session_manager import SessionManager

    sid = "f11_auto_001"
    msgs = [{"role": "user", "content": "首条用户消息用来自动取名"}]
    mgr = SessionManager(session_dir=str(tmp_path))
    path = mgr.session_dir / f"{sid}.json"
    path.write_text(json.dumps({
        "id": sid, "created_at": "2026-08-13T12:00:00+08:00",
        "title": "New Chat", "messages": msgs, "summary": None,
    }, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(sess_mod, "_session_mgr", mgr)

    ctx = _make_ctx()
    ctx.sessions[sid] = {"id": sid, "title": "New Chat", "messages": msgs}

    # 前端自动命名 → session.rename { auto: true }
    r = sess_mod.handle_session_rename(
        {"session_id": sid, "title": "自动起的会话名", "auto": True}, "r1", ctx)
    assert "error" not in r, f"auto rename 不应报错: {r}"
    assert r["result"].get("ok") is True

    # 内存：title 更新，user_named 不置真
    assert ctx.sessions[sid]["title"] == "自动起的会话名"
    assert ctx.sessions[sid].get("user_named", False) is False, \
        "auto 命名不得置 user_named=true"

    # 磁盘：title 持久化（重启后仍在），user_named 仍 false（②）
    disk = _read_disk(mgr, sid)
    assert disk["title"] == "自动起的会话名", f"auto 标题应落盘: {disk}"
    assert disk.get("user_named", False) is False, f"磁盘不得置 user_named: {disk}"

    # 模拟重启：resume 从磁盘重建（resume 无顶层 title，title 走 list/磁盘）
    monkeypatch.setattr("core.engine_adapter.is_running", lambda s: False)
    res = sess_mod.handle_session_resume({"session_id": sid}, "r2", ctx)
    body = res["result"]
    assert body["session_id"] == sid
    assert body["user_named"] is False, f"重启后仍非用户命名: {body}"
    # 磁盘仍是 auto 标题（重启后标题不丢的核心证据）
    assert _read_disk(mgr, sid)["title"] == "自动起的会话名"

    # list 同样 false → GUI 后续自动命名仍可更新；list 带标题
    lst = sess_mod.handle_session_list({}, "r3", ctx)
    item = next((s for s in lst["result"]["sessions"] if s["id"] == sid), None)
    assert item is not None
    assert item["user_named"] is False
    assert item["title"] == "自动起的会话名"


def test_f11_1_auto_never_overwrites_user_named(monkeypatch, tmp_path):
    """③ auto=true 且会话已 user_named=true → 拒绝覆盖（ok 但 title 不动）。"""
    from bobo_tui_gateway.handlers import sessions as sess_mod
    from core.session_manager import SessionManager

    sid = "f11_auto_002"
    msgs = [{"role": "user", "content": "用户消息"}]
    mgr = SessionManager(session_dir=str(tmp_path))
    path = mgr.session_dir / f"{sid}.json"
    path.write_text(json.dumps({
        "id": sid, "created_at": "2026-08-13T12:00:00+08:00",
        "title": "我的手动命名", "messages": msgs, "summary": None,
        "user_named": True,
    }, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(sess_mod, "_session_mgr", mgr)

    ctx = _make_ctx()
    ctx.sessions[sid] = {"id": sid, "title": "我的手动命名", "messages": msgs, "user_named": True}

    r = sess_mod.handle_session_rename(
        {"session_id": sid, "title": "自动想覆盖的名", "auto": True}, "r1", ctx)
    assert "error" not in r
    assert r["result"].get("skipped") is True, "应返回 skipped 标记"
    assert ctx.sessions[sid]["title"] == "我的手动命名", \
        "auto 不得覆盖用户命名: " + ctx.sessions[sid]["title"]
    disk = _read_disk(mgr, sid)
    assert disk["title"] == "我的手动命名", f"磁盘 title 不得被覆盖: {disk}"
    assert disk.get("user_named") is True


def test_f11_1_manual_rename_unchanged_f7(monkeypatch, tmp_path):
    """④ 手动 rename（无 auto / auto=false）：F7 语义不破 —— 置 user_named=true 落盘。"""
    from bobo_tui_gateway.handlers import sessions as sess_mod
    from core.session_manager import SessionManager

    sid = "f11_manual_003"
    msgs = [{"role": "user", "content": "用户消息"}]
    mgr = SessionManager(session_dir=str(tmp_path))
    path = mgr.session_dir / f"{sid}.json"
    path.write_text(json.dumps({
        "id": sid, "created_at": "2026-08-13T12:00:00+08:00",
        "title": "New Chat", "messages": msgs, "summary": None,
    }, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(sess_mod, "_session_mgr", mgr)

    ctx = _make_ctx()
    ctx.sessions[sid] = {"id": sid, "title": "New Chat", "messages": msgs}

    # 显式 auto=false（前端手动改名 save() 不传 auto → False）
    r = sess_mod.handle_session_rename(
        {"session_id": sid, "title": "手动改的名", "auto": False}, "r1", ctx)
    assert "error" not in r
    assert ctx.sessions[sid]["user_named"] is True, "手动路径仍置 user_named"
    assert _read_disk(mgr, sid)["user_named"] is True

    # 不传 auto（默认 False，历史调用兼容）
    r2 = sess_mod.handle_session_rename(
        {"session_id": sid, "title": "再改一次"}, "r2", ctx)
    assert "error" not in r2
    assert ctx.sessions[sid]["user_named"] is True


# ── F11-2：前端 updateSessionTitle 走 auto 通道（node 实跑） ──────────

def test_f11_2_frontend_auto_channel_node():
    """提取真实 updateSessionTitle，桩化 sessions + call：
    - 未命名会话 → 调用 session.rename 且带 auto:true（持久化通道）
    - user_named=true → 不调用 rename（本地防御 + 后端双保险）"""
    src = GUI_FILE.read_text(encoding="utf-8")
    fn = _extract_func(src, "updateSessionTitle")
    js = f"""
const assert = require('assert');
let calls = [];
let rendered = [];
let sessions = [];
function renderSessions() {{ rendered.push(sessions.map(s => s.title).join('|')); }}
function call(method, params) {{ calls.push({{ method, params }}); }}
{fn}

// 场景 A：未命名会话 → auto 通道落盘
sessions = [{{ id: 's1', title: 'New Chat' }}];
updateSessionTitle('s1', '首条用户消息abcdefghijklmnopqrstuvwxyz');
assert(sessions[0].title === '首条用户消息abcdefghijklmnopqrstuvwxyz', '自动取名应生效: ' + sessions[0].title);
assert(calls.length === 1, '应恰好一次 rename 调用, got ' + calls.length);
assert(calls[0].method === 'session.rename', '应走 session.rename: ' + calls[0].method);
assert(calls[0].params.auto === true, '应带 auto:true: ' + JSON.stringify(calls[0].params));
assert(calls[0].params.session_id === 's1');
assert(calls[0].params.title === sessions[0].title);

// 场景 B：user_named=true → 不调用 rename（自动命名被拒）
calls = [];
sessions = [{{ id: 's2', title: '我的手动命名', user_named: true }}];
updateSessionTitle('s2', '自动名abcdefghijklmnopqrstuvwxyz');
assert(sessions[0].title === '我的手动命名', '不得覆盖用户命名');
assert(calls.length === 0, 'user_named 会话不得发 rename: ' + calls.length);

// 场景 C：标题截断 35 字符后再落盘
calls = [];
sessions = [{{ id: 's3', title: 'New Chat' }}];
updateSessionTitle('s3', '这是一条非常长的用户消息用来测试自动命名截断逻辑是否正常工作的内容');
assert(sessions[0].title.length <= 35, '截断 35: ' + sessions[0].title);
assert(calls.length === 1 && calls[0].params.title.length <= 35, '落盘标题同样截断');

console.log('NODE_F11_AUTO_CHANNEL_OK');
"""
    out = _run_node(js)
    assert "NODE_F11_AUTO_CHANNEL_OK" in out, f"node 实跑失败: {out}"


# ── F11-3：后端源码静态断言 ───────────────────────────────────────────

def test_f11_3_backend_auto_param_static():
    """sessions.py handle_session_rename 含 auto 参数与 user_named 防线。"""
    src = SESS_FILE.read_text(encoding="utf-8")
    m = re.search(r"def handle_session_rename\(.*?(?=\ndef |\Z)", src, re.S)
    assert m, "未找到 handle_session_rename"
    body = m.group(0)
    assert "auto = bool(params.get(\"auto\", False))" in body, \
        "缺 auto 参数解析"
    assert "auto and session.get(\"user_named\", False)" in body, \
        "缺 user_named 防线（auto 不覆盖用户命名）"
    assert "if not auto:" in body, "缺手动路径分支（auto=false 仍置 user_named）"
    assert "_save_session_to_disk(sid, ctx)" in body, "auto 路径必须落盘"
