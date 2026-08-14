"""TICKET-GUI-F7 回归测试 — 手动命名优先级（自动命名不得覆盖用户命名）。

覆盖：
- F7-1 静态断言（GUI 闸门）：loadSession 自动命名带 !result.user_named 条件；
  updateSessionTitle 内部拒绝覆盖 user_named 为真的会话；startRename 手动改名
  成功后本地立即标 user_named=true（dist/index.html 现行页面）
- F7-2 node 实跑（GUI 行为）：提取真实 updateSessionTitle，桩化 sessions 数组，
  断言 user_named=true 时标题不被自动覆盖、未命名会话仍正常自动取名
- F7-3 后端 pytest 实证：
  * rename（GUI 手动改名）→ session.list / session.resume 返回 user_named=true，
    磁盘 JSON 持久化该标记（切走切回不丢）
  * title（TUI /title 手动路径）→ resume 返回 user_named=true（GUI 不覆盖）
  * 未命名会话（默认路径）→ resume/list 返回 user_named=false，自动命名保留
  * _save_session_to_disk 保留磁盘已有 user_named（防止无键覆盖）

注：GUI 渲染层无法无头全自动化，采用静态断言 + node 实跑 + 后端 RPC 实证
（与 F3/F4/F6 同款，零漂移验证当前 HTML/源码）。
"""

import json
import re
import subprocess
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
GUI_FILE = ROOT / "apps" / "desktop" / "dist" / "index.html"


# ── 辅助：提取当前 HTML 内真实 JS 函数（零漂移，与 F3/F4/F6 同款） ──────────

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


def _extract_event_block(src: str, event: str) -> str:
    """提取 on('<event>', function(...) { ... }) 的完整块（括号配对到闭合 );）。"""
    pat = re.compile(r"on\('" + re.escape(event) + r"',\s*function[^)]*\)\s*\{")
    m = pat.search(src)
    assert m, f"未找到 on('{event}') 事件块"
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
    raise AssertionError(f"on('{event}') 括号不闭合")


def _run_node(js: str) -> str:
    """在 node 中执行 JS（同步），返回 stdout。"""
    r = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        raise AssertionError(f"node 执行失败: {r.stderr}")
    return r.stdout


# ── F7-1：GUI 闸门静态断言 ─────────────────────────────────────────────

def test_f7_1_gui_gate_static_asserts():
    """自动命名路径必须有 user_named 闸门；手动改名路径必须本地标 true。"""
    src = GUI_FILE.read_text(encoding="utf-8")

    # 1) loadSession 自动命名：条件必须含 !result.user_named
    assert "!result.user_named" in src, \
        "loadSession 自动命名缺少 user_named 闸门（会覆盖手动命名）"
    # 且自动命名语句仍在（行为保留）
    assert "firstUserMsg.text.substring(0, 30)" in src, \
        "自动取名（首条用户消息前 30 字）行为被误删"

    # 2) updateSessionTitle 内部防御：user_named 为真则拒绝覆盖
    ut = _extract_func(src, "updateSessionTitle")
    assert "!s.user_named" in ut, \
        "updateSessionTitle 缺少 user_named 防御: " + ut[:200]

    # 3) startRename 手动改名成功后本地立即标 user_named=true
    sr = _extract_func(src, "startRename")
    assert "s.user_named = true" in sr, \
        "startRename 改名成功后应本地立即标 user_named=true: " + sr[:400]

    # 4) 铁律回归：不动 F3-5 diff 显示 / F6 thinking 分段（相关要素仍在）
    for keep in ("diffHighlight", "collapseThinkBox", "createThinkBox",
                 "toolSummary", "function renderFullHistory"):
        assert keep in src, f"回归破坏（要素缺失）: {keep}"


# ── F7-2：updateSessionTitle 闸门 node 实跑 ─────────────────────────────

def test_f7_2_update_title_gate_node():
    """提取真实 updateSessionTitle，桩化 sessions 数组：
    - user_named=true → 自动命名调用被拒绝，标题保持手动值
    - 无 user_named（未命名会话）→ 自动命名照常生效"""
    src = GUI_FILE.read_text(encoding="utf-8")
    fn = _extract_func(src, "updateSessionTitle")
    js = f"""
const assert = require('assert');
const rendered = [];
let sessions = [];
function renderSessions() {{ rendered.push(sessions.map(s => s.title).join('|')); }}
// TICKET-GUI-F11：updateSessionTitle 现走 session.rename auto 通道，桩化 call
function call() {{}}
{fn}
// 场景 A：手动命名过（user_named=true）→ 自动命名不得覆盖
sessions = [{{ id: 's1', title: '我的手动命名', user_named: true }}];
updateSessionTitle('s1', '首条用户消息前三十个字内容abcdefghijklmnopq');
assert(sessions[0].title === '我的手动命名', 'user_named=true 不得被自动命名覆盖: ' + sessions[0].title);

// 场景 B：未命名会话（无 user_named 键）→ 自动取名保留
sessions = [{{ id: 's2', title: 'New Chat' }}];
updateSessionTitle('s2', '首条用户消息abcdefghijklmnopqrstuvwxyz123456789');
assert(sessions[0].title === '首条用户消息abcdefghijklmnopqrstuvwxyz123', '未命名会话应自动取名(前35字): ' + sessions[0].title);
assert(sessions[0].title.length <= 35, '自动取名仍截断 35: ' + sessions[0].title);

// 场景 C：手动命名会话再手动改名后 → user_named 仍为 true 且标题已更新（startRename save 路径语义）
sessions = [{{ id: 's3', title: '旧名', user_named: true }}];
sessions[0].title = '新手动名';
sessions[0].user_named = true;
updateSessionTitle('s3', '自动名不应生效abcdefghijklmnopqrstuv');
assert(sessions[0].title === '新手动名', '手动改名后自动命名仍不得覆盖: ' + sessions[0].title);

console.log('NODE_F7_TITLE_GATE_OK');
"""
    out = _run_node(js)
    assert "NODE_F7_TITLE_GATE_OK" in out, f"node 实跑失败: {out}"


# ── F7-3：后端持久化与 RPC 实证 ────────────────────────────────────────

def _make_ctx():
    """构造最小 ctx 桩（含 handle_session_* 用到的成员）。"""
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


def _write_session_file(mgr, sid, messages, title=None, user_named=False):
    """向 mgr.session_dir 写一份会话文件（磁盘版）。"""
    path = mgr.session_dir / f"{sid}.json"
    data = {
        "id": sid,
        "created_at": "2026-08-13T12:00:00+08:00",
        "title": title or f"会话_{sid}",
        "messages": messages,
        "summary": None,
        "user_named": user_named,
    }
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _read_disk(mgr, sid):
    path = mgr.session_dir / f"{sid}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_f7_3_rename_persists_and_list_resume_return(monkeypatch, tmp_path):
    """GUI 手动改名（session.rename）：磁盘持久化 user_named=true；
    session.list 与 session.resume 均返回该字段（切走切回不丢）。"""
    from bobo_tui_gateway.handlers import sessions as sess_mod
    from core.session_manager import SessionManager

    sid = "f7_rename_001"
    msgs = [{"role": "user", "content": "首条用户消息"}]
    mgr = SessionManager(session_dir=str(tmp_path))
    _write_session_file(mgr, sid, msgs, title="会话_f7_rename_001", user_named=False)
    monkeypatch.setattr(sess_mod, "_session_mgr", mgr)

    ctx = _make_ctx()
    ctx.sessions[sid] = {
        "id": sid, "title": "会话_f7_rename_001",
        "messages": msgs, "user_named": False,
    }

    # 1) 手动改名 → 后端内存标记 + 落盘
    r = sess_mod.handle_session_rename({"session_id": sid, "title": "我的自定义名"}, "r1", ctx)
    assert "error" not in r, f"rename 不应报错: {r}"
    assert ctx.sessions[sid]["user_named"] is True, "内存标记应置 true"
    disk = _read_disk(mgr, sid)
    assert disk.get("user_named") is True, f"磁盘应持久化 user_named=true: {disk}"
    assert disk["title"] == "我的自定义名", f"磁盘 title 应为手动值: {disk['title']}"

    # 2) session.list 返回 user_named=true
    lst = sess_mod.handle_session_list({}, "r2", ctx)
    item = next((s for s in lst["result"]["sessions"] if s["id"] == sid), None)
    assert item is not None, "list 应含该会话"
    assert item["user_named"] is True, f"list 应返回 user_named=true: {item}"

    # 3) session.resume 返回 user_named=true（模拟切回，磁盘版为准）
    monkeypatch.setattr("core.engine_adapter.is_running", lambda s: False)
    res = sess_mod.handle_session_resume({"session_id": sid}, "r3", ctx)
    body = res["result"]
    assert body["user_named"] is True, f"resume 应返回 user_named=true: {body}"
    assert body["messages"][0]["text"] == "首条用户消息"


def test_f7_3_title_tui_sets_user_named(monkeypatch, tmp_path):
    """TUI /title（session.title 手动路径）：同样置 user_named=true 并落盘。"""
    from bobo_tui_gateway.handlers import sessions as sess_mod
    from core.session_manager import SessionManager

    sid = "f7_title_002"
    msgs = [{"role": "user", "content": "用户说了一句很长的话用来自动取名"}]
    mgr = SessionManager(session_dir=str(tmp_path))
    _write_session_file(mgr, sid, msgs, title="会话_f7_title_002", user_named=False)
    monkeypatch.setattr(sess_mod, "_session_mgr", mgr)

    ctx = _make_ctx()
    ctx.sessions[sid] = {"id": sid, "title": "会话_f7_title_002", "messages": msgs}

    r = sess_mod.handle_session_title({"session_id": sid, "title": "/title 设定的名字"}, "t1", ctx)
    assert "error" not in r, f"title 不应报错: {r}"
    assert ctx.sessions[sid]["user_named"] is True
    disk = _read_disk(mgr, sid)
    assert disk.get("user_named") is True, "TUI /title 路径也应持久化 user_named"
    assert disk["title"] == "/title 设定的名字"

    # resume 返回 user_named=true → GUI 自动命名跳过（验收 3）
    monkeypatch.setattr("core.engine_adapter.is_running", lambda s: False)
    res = sess_mod.handle_session_resume({"session_id": sid}, "t2", ctx)
    assert res["result"]["user_named"] is True


def test_f7_3_unamed_session_keeps_auto_title(monkeypatch, tmp_path):
    """未命名会话（无 user_named 标记 / 默认路径）：resume 与 list 返回 false，
    自动命名行为保留（验收 2）。"""
    from bobo_tui_gateway.handlers import sessions as sess_mod
    from core.session_manager import SessionManager

    sid = "f7_auto_003"
    msgs = [{"role": "user", "content": "这条消息将用于自动取名"}]
    mgr = SessionManager(session_dir=str(tmp_path))
    # 老会话磁盘无 user_named 键（历史数据兼容）
    path = mgr.session_dir / f"{sid}.json"
    path.write_text(json.dumps({
        "id": sid, "created_at": "2026-08-13T12:00:00+08:00",
        "title": "New Chat", "messages": msgs, "summary": None,
    }, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(sess_mod, "_session_mgr", mgr)

    ctx = _make_ctx()
    ctx.sessions[sid] = {"id": sid, "title": "New Chat", "messages": msgs}

    # resume：无标记 → user_named=false（GUI 自动取名可执行）
    monkeypatch.setattr("core.engine_adapter.is_running", lambda s: False)
    res = sess_mod.handle_session_resume({"session_id": sid}, "a1", ctx)
    assert res["result"]["user_named"] is False, "未命名会话 resume 应为 false"

    # list：同样 false
    lst = sess_mod.handle_session_list({}, "a2", ctx)
    item = next((s for s in lst["result"]["sessions"] if s["id"] == sid), None)
    assert item["user_named"] is False

    # 未命名会话落盘不产生 user_named=true（默认路径不写标记）
    _save_result = sess_mod._save_session_to_disk(sid, ctx)
    assert _read_disk(mgr, sid).get("user_named") is False


def test_f7_3_save_keeps_existing_marker(monkeypatch, tmp_path):
    """_save_session_to_disk 保留磁盘已有 user_named=true（内存无键时不得覆盖）。"""
    from bobo_tui_gateway.handlers import sessions as sess_mod
    from core.session_manager import SessionManager

    sid = "f7_keep_004"
    msgs = [{"role": "user", "content": "历史消息"}]
    mgr = SessionManager(session_dir=str(tmp_path))
    _write_session_file(mgr, sid, msgs, title="我的手动名", user_named=True)
    monkeypatch.setattr(sess_mod, "_session_mgr", mgr)

    ctx = _make_ctx()
    # 内存版模拟 resume 重建后的形态：无 user_named 键（防御场景）
    ctx.sessions[sid] = {"id": sid, "title": "我的手动名", "messages": msgs}

    sess_mod._save_session_to_disk(sid, ctx)
    disk = _read_disk(mgr, sid)
    assert disk.get("user_named") is True, \
        "磁盘已有 user_named=true 不得被无键内存覆盖: " + json.dumps(disk)
    assert disk["title"] == "我的手动名"
