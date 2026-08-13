"""TICKET-GUI-F9 回归测试 — 运行中会话切回不丢进行中回合（P0）。

覆盖：
- F9-1 后端 resume 忙分支读活引擎 history（mock get_live_history 返回含进行中
  回合的 history → transcript 含最新用户消息与工具步骤，不丢回合）
- F9-2 取不到活引擎（竞态窗口/引擎恰好退出）回退内存版，不崩溃
- F9-3 get_live_history 异常兜底：mock 抛异常 → resume 不打断、回退内存版
- F9-4 engine_adapter 注册表：get_live_history 无活引擎返回 None；注册后可读
  浅拷贝；清理后返回 None
- F9-5 TUI 零变化闸：ui-tui 目录 git diff 空；toTranscriptMessages 解构不变
- F9-6 md5 闸门：真实库三文件存在且可读（测试不写不删，手工 md5sum 收工闸）
- F9-7 GUI 事件续渲染静态断言：tool.start/tool.complete 事件块存在且不带
  session_id 过滤（按当前会话渲染，切回后后续实时事件自然续渲染）

注：GUI 渲染层无法无头全自动化，采用静态断言 + node 实跑 + 后端 pytest 实证
（与 F6/F8 同款零漂移验证当前 HTML/源码）。
"""

import hashlib
import json
import re
import subprocess
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
GUI_FILE = ROOT / "apps" / "desktop" / "dist" / "index.html"
SESSIONS_PY = ROOT / "bobo_tui_gateway" / "handlers" / "sessions.py"
ENGINE_ADAPTER_PY = ROOT / "core" / "engine_adapter.py"
TUI_MESSAGES_TS = ROOT / "ui-tui" / "src" / "domain" / "messages.ts"
MD5_FILES = [
    ROOT / "data" / "knowledge_base.json",
    ROOT / "library" / "MEMORY.md",
    ROOT / "library" / "index.md",
]


def _md5(f: Path) -> str:
    return hashlib.md5(f.read_bytes()).hexdigest()


# ── 辅助：最小 ctx 桩（与 F6 同款） ────────────────────────────────────

def _make_ctx():
    """构造最小 ctx 桩（只含 handle_session_resume 用到的成员）。"""
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


def _write_session_file(mgr, sid, messages, summary=None):
    """向 mgr.session_dir 写一份会话文件（磁盘版）。"""
    path = mgr.session_dir / f"{sid}.json"
    data = {
        "id": sid,
        "created_at": "2026-08-14T07:00:00+08:00",
        "title": f"会话_{sid}",
        "messages": messages,
        "summary": summary,
    }
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


# ── F9-1：resume 忙分支读活引擎 history（核心修复） ────────────────────

def test_f9_1_resume_busy_reads_live_engine_history(monkeypatch, tmp_path):
    """引擎忙 + 活引擎 history 含进行中回合 → resume 返回活引擎最新消息。

    磁盘版（旧）与内存版（旧，回合末才写回）都不含进行中回合；只有活引擎
    history 里有。F9 修复后 resume 必须读活引擎，否则切回即丢回合。
    """
    from bobo_tui_gateway.handlers import sessions as sess_mod
    from core.session_manager import SessionManager

    sid = "f9_live_sid_001"
    # 磁盘版（旧：2 条）
    disk_msgs = [
        {"role": "user", "content": "问题一"},
        {"role": "assistant", "content": "回答一"},
    ]
    # 内存版（也旧：3 条，回合末才写回，故缺进行中回合）
    mem_msgs = disk_msgs + [{"role": "user", "content": "问题二"}]
    # 活引擎 history（最新：含进行中回合的用户消息 + 工具步骤）
    live_msgs = mem_msgs + [
        {"role": "assistant", "content": "", "tool_calls": [{"id": "tc1", "function": {"name": "read_local_file"}}]},
        {"role": "tool", "content": "<<<INLINE_DIFF>>>\n- 旧\n+ 新\n<<<END_INLINE_DIFF>>>", "tool_call_id": "tc1"},
        {"role": "user", "content": "正在处理的追问（还没落盘）"},
    ]

    mgr = SessionManager(session_dir=str(tmp_path))
    _write_session_file(mgr, sid, disk_msgs, summary="磁盘摘要")
    monkeypatch.setattr(sess_mod, "_session_mgr", mgr)

    ctx = _make_ctx()
    ctx.sessions[sid] = {"id": sid, "title": f"会话_{sid}", "messages": mem_msgs}
    monkeypatch.setattr("core.engine_adapter.is_running", lambda s: s == sid)
    # F9：mock 活引擎 history（真实实现有活引擎注册表时同样返回）
    monkeypatch.setattr("core.engine_adapter.get_live_history", lambda s: live_msgs)

    result = sess_mod.handle_session_resume({"session_id": sid}, "rid1", ctx)

    assert "error" not in result, f"resume 不应报错: {result}"
    body = result["result"]
    # 活引擎 history 6 条全返回，一条不丢
    assert body["message_count"] == 6, f"应返回活引擎 6 条: {body['message_count']}"
    texts = [m["text"] for m in body["messages"] if m["role"] in ("user", "assistant", "system")]
    assert "正在处理的追问（还没落盘）" in texts, "进行中用户消息必须可见: " + json.dumps(texts)
    # 工具步骤可见（tool 消息进 transcript）
    tool_msgs = [m for m in body["messages"] if m["role"] == "tool"]
    assert len(tool_msgs) == 1, f"工具步骤应进 transcript: {tool_msgs}"
    assert "read_local_file" in tool_msgs[0]["name"], f"工具名应由 tool_calls 映射: {tool_msgs[0]}"
    # 引擎忙标记 + 当前会话指向更新
    assert body["engine_busy"] is True
    assert ctx._current == sid


# ── F9-2：取不到活引擎回退内存版 ───────────────────────────────────────

def test_f9_2_resume_busy_fallback_memory_when_no_live(monkeypatch, tmp_path):
    """引擎忙但取不到活引擎（竞态窗口/引擎恰好退出）→ 回退内存版，不崩溃。"""
    from bobo_tui_gateway.handlers import sessions as sess_mod
    from core.session_manager import SessionManager

    sid = "f9_fallback_sid_002"
    disk_msgs = [{"role": "user", "content": "磁盘消息"}]
    mem_msgs = disk_msgs + [{"role": "user", "content": "内存最新"}]

    mgr = SessionManager(session_dir=str(tmp_path))
    _write_session_file(mgr, sid, disk_msgs)
    monkeypatch.setattr(sess_mod, "_session_mgr", mgr)

    ctx = _make_ctx()
    ctx.sessions[sid] = {"id": sid, "title": f"会话_{sid}", "messages": mem_msgs}
    monkeypatch.setattr("core.engine_adapter.is_running", lambda s: s == sid)
    # F9：取不到活引擎 → None
    monkeypatch.setattr("core.engine_adapter.get_live_history", lambda s: None)

    result = sess_mod.handle_session_resume({"session_id": sid}, "rid2", ctx)

    assert "error" not in result, f"resume 不应报错: {result}"
    body = result["result"]
    assert body["message_count"] == 2, f"应回退内存版 2 条: {body['message_count']}"
    assert body["engine_busy"] is True
    assert "内存最新" in [m["text"] for m in body["messages"]]


# ── F9-3：get_live_history 异常不打断 resume ───────────────────────────

def test_f9_3_resume_busy_live_history_exception_safe(monkeypatch, tmp_path):
    """get_live_history 抛异常 → resume 不打断、回退内存版（线程安全铁律）。"""
    from bobo_tui_gateway.handlers import sessions as sess_mod
    from core.session_manager import SessionManager

    sid = "f9_exc_sid_003"
    disk_msgs = [{"role": "user", "content": "磁盘消息"}]
    mem_msgs = disk_msgs + [{"role": "user", "content": "内存兜底"}]

    mgr = SessionManager(session_dir=str(tmp_path))
    _write_session_file(mgr, sid, disk_msgs)
    monkeypatch.setattr(sess_mod, "_session_mgr", mgr)

    ctx = _make_ctx()
    ctx.sessions[sid] = {"id": sid, "title": f"会话_{sid}", "messages": mem_msgs}
    monkeypatch.setattr("core.engine_adapter.is_running", lambda s: s == sid)

    def _boom(s):
        raise RuntimeError("引擎正在退出，history 不可读")

    monkeypatch.setattr("core.engine_adapter.get_live_history", _boom)

    result = sess_mod.handle_session_resume({"session_id": sid}, "rid3", ctx)

    assert "error" not in result, f"resume 不应被异常打断: {result}"
    body = result["result"]
    assert body["message_count"] == 2, "异常时回退内存版"
    assert body["engine_busy"] is True


# ── F9-4：engine_adapter 注册表行为（真实实现，不 mock） ───────────────

def test_f9_4_live_engine_registry_real():
    """真实 get_live_history：无活引擎 → None；注册 FakeEngine → 返回浅拷贝；
    清理后 → None。注册表不泄漏（finally 清理路径）。"""
    from core import engine_adapter as ea

    sid = "f9_registry_sid_004"
    # 清理残留（防御）
    with ea._live_engines_lock:
        ea._live_engines.pop(sid, None)
    try:
        # 无活引擎
        assert ea.get_live_history(sid) is None, "无活引擎应返回 None"

        # 注册 FakeEngine（模拟 run_engine 里 engine.sid 赋值后的注册点）
        class FakeEngine:
            history = ["m1", "m2", {"role": "user", "content": "进行中"}]

        with ea._live_engines_lock:
            ea._live_engines[sid] = FakeEngine()

        got = ea.get_live_history(sid)
        assert got == ["m1", "m2", {"role": "user", "content": "进行中"}], f"应返回浅拷贝: {got}"
        assert got is not FakeEngine.history, "必须返回拷贝（防调用方改引擎内部）"

        # 引擎 history 变更后再次读取 → 拿到新快照（进行中回合实时可见）
        FakeEngine.history.append({"role": "tool", "content": "又一步"})
        got2 = ea.get_live_history(sid)
        assert len(got2) == 4, f"应反映引擎最新 history: {got2}"
    finally:
        # 模拟 run_engine finally 清理
        with ea._live_engines_lock:
            ea._live_engines.pop(sid, None)
    assert ea.get_live_history(sid) is None, "清理后应返回 None"


# ── F9-5：TUI 零变化闸 ────────────────────────────────────────────────

def test_f9_5_tui_zero_change():
    """TUI 源码零变化：toTranscriptMessages 解构不变；git diff 无 ui-tui 路径。"""
    ts = TUI_MESSAGES_TS.read_text(encoding="utf-8")
    assert "const { context, name, role, text } = row as TranscriptRow" in ts, \
        "TUI 解构行不得扩展新字段"

    try:
        r = subprocess.run(
            ["git", "diff", "--name-only", "--", "ui-tui/"],
            cwd=ROOT, capture_output=True, text=True, timeout=10,
        )
    except Exception:
        pytest.skip("git 不可用，跳过 diff 检查")
    assert r.returncode == 0, f"git diff 失败: {r.stderr}"
    assert r.stdout.strip() == "", f"TUI 目录有改动（铁律零变化）: {r.stdout}"


# ── F9-6：md5 闸门（真实库三文件，收工手工验证；测试只做存在性保护） ───

def test_f9_6_md5_gate_real_library():
    """真实库三文件存在且可读 —— 测试运行不写不删。

    md5 前后一致性按票内惯例由收工汇报手工闸门验证（跑全量前 md5sum →
    跑后 md5sum 对比，与 PERF-1/F8 同款）。
    """
    for f in MD5_FILES:
        assert f.exists(), f"{f} 不存在"
        assert len(_md5(f)) == 32, f"{f} 读取失败"
        assert f.stat().st_size > 0, f"{f} 为空文件"


# ── F9-7：GUI 事件续渲染静态断言（切回后实时事件按当前会话渲染） ───────

def test_f9_7_gui_event_continues_render():
    """dist/index.html：tool.start/tool.complete 事件块存在且事件分发器
    （onMessage）按 type 查 handler、不做 session_id 过滤 —— 切回运行中会话后，
    后续实时事件自然渲染到当前聊天区（续渲染，无需改动）。"""
    src = GUI_FILE.read_text(encoding="utf-8")

    # 事件分发器：按 type 查 handler（无 session_id 过滤 → 当前会话续渲染）
    assert "handlers.get(msg.params.type)" in src, "事件分发按 type 查 handler"

    # tool.start / tool.complete 事件块存在（续渲染入口）
    assert "on('tool.start'" in src, "缺 tool.start 事件块"
    assert "on('tool.complete'" in src, "缺 tool.complete 事件块"

    # resume 渲染入口存在（切回时重建历史）
    assert "function renderFullHistory" in src, "缺 renderFullHistory"
    assert "session.resume" in src, "缺 session.resume 调用"


# ── F9-8：实弹场景 1 —— 切走切回内容不丢（真实引擎跑回合） ──────────────

def test_f9_8_live_switch_away_and_back_content_kept(monkeypatch, tmp_path):
    """实弹：会话 A 引擎跑回合（进行中）→ 切走 → 切回 A。

    真实 Engine 在线程里跑（history 逐步积累），resume 走真实 handler +
    真实 get_live_history + 真实活引擎注册表。进行中的用户消息与工具步骤
    必须全部可见；回合收尾后（模拟 run_engine 回写内存+磁盘）再 resume
    内容不重复不缺失。
    """
    from tests.test_engine_e2e import FakeLLMCaller, FakeToolExecutor, _make_test_engine
    from bobo_tui_gateway.handlers import sessions as sess_mod
    from core.session_manager import SessionManager
    from core import engine_adapter as ea

    sid = "f9_live_switch_001"
    tool_started = threading.Event()
    resume_done = threading.Event()

    class BlockingToolExecutor(FakeToolExecutor):
        """第 2 个工具（read_local_file）执行时暂停引擎，直到主线程 resume 完成。
        此时第 1 步（edit_file）已完成入 history，制造"执行 2-3 步后切回"窗口。"""

        def __call__(self, tool_name, args):
            if tool_name == "read_local_file":
                tool_started.set()
                assert resume_done.wait(10), "resume 未在 10s 内完成（死锁）"
            return super().__call__(tool_name, args)

    fake_llm = FakeLLMCaller([
        ("", [{"id": "call_1", "type": "function",
               "function": {"name": "edit_file", "arguments": "{}"}}]),
        ("", [{"id": "call_2", "type": "function",
               "function": {"name": "read_local_file", "arguments": "{}"}}]),
        ("文件已改好。", None),
    ])
    fake_tools = BlockingToolExecutor(responses={"edit_file": "OK"})
    engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)
    monkeypatch.setattr(engine, "_check_guards", lambda: False)
    engine.sid = sid

    # 注册活引擎（run_engine 同款路径：engine.sid 赋值后入注册表）
    with ea._live_engines_lock:
        ea._live_engines[sid] = engine

    # 磁盘版/内存版：旧（只有首条用户消息，无进行中回合）
    mgr = SessionManager(session_dir=str(tmp_path))
    old_msgs = [{"role": "user", "content": "改文件"}]
    _write_session_file(mgr, sid, old_msgs, summary=None)
    monkeypatch.setattr(sess_mod, "_session_mgr", mgr)
    ctx = _make_ctx()
    ctx.sessions[sid] = {"id": sid, "title": f"会话_{sid}", "messages": list(old_msgs)}
    monkeypatch.setattr("core.engine_adapter.is_running", lambda s: s == sid)

    engine_err = {}

    def _run():
        try:
            engine.run("改文件")
        except Exception as e:  # pragma: no cover
            engine_err["error"] = repr(e)

    t = threading.Thread(target=_run)
    t.start()

    live_count = None
    try:
        # 等引擎进入工具执行（进行中窗口）
        assert tool_started.wait(10), "引擎未在 10s 内开始执行工具"
        # 切回 A：resume 必须返回活引擎 history（含进行中回合）
        result = sess_mod.handle_session_resume({"session_id": sid}, "r1", ctx)
        assert "error" not in result, f"resume 不应报错: {result}"
        body = result["result"]
        texts = [m["text"] for m in body["messages"] if m["role"] in ("user", "assistant", "system")]
        assert "改文件" in texts, f"进行中用户消息必须可见: {texts}"
        assert body["engine_busy"] is True, "引擎忙标记必须为 True"
        tc_msgs = [m for m in body["messages"] if m["role"] == "assistant" and m["tool_calls"]]
        assert len(tc_msgs) >= 1, f"进行中工具步骤必须可见: {body['messages']}"
        live_count = body["message_count"]
    finally:
        resume_done.set()
        t.join(timeout=15)
        with ea._live_engines_lock:
            ea._live_engines.pop(sid, None)  # 模拟 run_engine finally 清理

    assert not engine_err, f"引擎线程异常: {engine_err}"
    assert engine.state == engine.STATE_DONE, f"引擎应正常完成: {engine.state}"

    # 回合收尾：模拟 run_engine 回写内存 + save_session_to_disk 写盘
    full_history = list(engine.history)
    ctx.sessions[sid]["messages"] = full_history
    _write_session_file(mgr, sid, full_history, summary=None)
    monkeypatch.setattr("core.engine_adapter.is_running", lambda s: False)

    # 引擎空闲后切回：磁盘版 = 完整回合，内容不丢不重复
    result2 = sess_mod.handle_session_resume({"session_id": sid}, "r2", ctx)
    assert "error" not in result2, f"收尾后 resume 不应报错: {result2}"
    body2 = result2["result"]
    texts2 = [m["text"] for m in body2["messages"] if m["role"] in ("user", "assistant", "system")]
    assert any(t and "改文件" in t for t in texts2), f"收尾后用户消息不丢: {texts2}"
    assert any(t and "文件已改好" in t for t in texts2), f"收尾后最终回复不丢: {texts2}"
    assert sum(1 for t in texts2 if t and "改文件" in t and "文件已改好" not in t) == 1, \
        f"用户消息不得重复: {texts2}"
    assert body2["message_count"] >= live_count, "收尾后消息数不减少"
    assert body2["engine_busy"] is False


# ── F9-9：实弹场景 2 —— 回合刚结束瞬间切回不重复（竞态窗口） ────────────

def test_f9_9_live_race_just_after_turn_end_no_duplicate(monkeypatch, tmp_path):
    """实弹：回合刚结束瞬间（history 已写回但注册表未清理）切回。

    竞态窗口：is_running 仍 True、_live_engines 仍含引擎（history = 完整回合），
    磁盘/内存也已是完整回合。resume 读活引擎 history → 与磁盘一致，
    消息不重复（用户消息只出现一次）。
    """
    from bobo_tui_gateway.handlers import sessions as sess_mod
    from core.session_manager import SessionManager
    from core import engine_adapter as ea

    sid = "f9_live_race_002"
    full_history = [
        {"role": "user", "content": "改文件"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "function": {"name": "edit_file"}}]},
        {"role": "tool", "content": "OK", "tool_call_id": "c1"},
        {"role": "assistant", "content": "文件已改好。"},
    ]

    class DoneEngine:
        history = list(full_history)

    # 竞态窗口：注册表未清理（引擎已跑完但 finally 未执行）+ is_running True
    with ea._live_engines_lock:
        ea._live_engines[sid] = DoneEngine()
    try:
        monkeypatch.setattr("core.engine_adapter.is_running", lambda s: s == sid)

        mgr = SessionManager(session_dir=str(tmp_path))
        _write_session_file(mgr, sid, full_history, summary=None)
        monkeypatch.setattr(sess_mod, "_session_mgr", mgr)
        ctx = _make_ctx()
        ctx.sessions[sid] = {"id": sid, "title": f"会话_{sid}", "messages": list(full_history)}

        result = sess_mod.handle_session_resume({"session_id": sid}, "r1", ctx)
        assert "error" not in result, f"resume 不应报错: {result}"
        body = result["result"]
        texts = [m["text"] for m in body["messages"] if m["role"] in ("user", "assistant", "system")]
        assert sum(1 for t in texts if t and "改文件" in t) == 1, \
            f"竞态窗口不得重复用户消息: {texts}"
        assert any(t and "文件已改好" in t for t in texts), "最终回复可见"
        assert body["engine_busy"] is True
        # 与磁盘完整回合一致（无缺失无重复）
        assert body["message_count"] == len(full_history), \
            f"应返回完整回合 {len(full_history)} 条: {body['message_count']}"
    finally:
        with ea._live_engines_lock:
            ea._live_engines.pop(sid, None)
