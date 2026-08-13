"""TICKET-GUI-F6 回归测试 — thinking 分段落地 + 历史恢复补全。

覆盖：
- F6-1 thinking 分段（缺陷 1）：tool.start 到达收束当前思考框为折叠段（复用
  collapseThinkBox，视觉样式不动），后续 message.delta 无打开框时另开新框；
  message.complete 在 thinkBoxEl 被收束置空后仍能收束 final 思考（静态断言
  dist/index.html 现行事件块）
- F6-2 空泡泡占位（缺陷 2a）：renderFullHistory 现存消息里空 assistant（纯工具
  回合）→ "（工具调用回合）"占位，与 renderArchivedMessages 一致（node 实跑
  当前 HTML 内真实函数）
- F6-3 压缩摘要分隔行（缺陷 2c）：resume 返回值带 summary → 历史顶部柔和分隔
  摘要行；无 summary 零变化（node 实跑）
- F6-4 时序竞争（缺陷 2b）：handle_session_resume 引擎忙 → 返回内存版最新消息
  且禁止磁盘版覆盖运行中会话；空闲 → 磁盘版覆盖内存（原行为）；transcript 的
  assistant 带 tool_calls 字段、返回 summary 字段（后端 pytest 实证）

注：GUI 渲染层无法无头全自动化，采用静态断言（dist/index.html 现行页面）
+ node 实跑当前 HTML 内真实函数（零漂移行为验证）+ 后端 RPC 实证（与 F3/F4 同款）。
"""

import json
import re
import subprocess
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
GUI_FILE = ROOT / "apps" / "desktop" / "dist" / "index.html"


# ── 辅助：提取当前 HTML 内真实 JS 函数（零漂移，与 F3/F4 同款） ──────────

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


# ── F6-1：thinking 分段（缺陷 1）—— 静态断言事件块 ──────────────────────

def test_f6_1_thinking_segmentation():
    """tool.start 收束思考框 / delta 无框开新框 / complete 兼容置空态。"""
    src = GUI_FILE.read_text(encoding="utf-8")

    # tool.start：必须收束当前思考框为折叠段并置空（复用 collapseThinkBox）
    ts = _extract_event_block(src, "tool.start")
    assert "collapseThinkBox(thinkBoxEl, thinkText)" in ts, \
        "tool.start 应把当前思考框收束为折叠段: " + ts[:300]
    assert "thinkBoxEl = null" in ts, \
        "tool.start 收束后应置空 thinkBoxEl（后续 delta 另开新框）: " + ts[:300]
    assert "thinkText = ''" in ts, \
        "tool.start 收束后应清空 thinkText: " + ts[:300]

    # message.delta：无打开思考框时另开新框承接后续思考
    md = _extract_event_block(src, "message.delta")
    assert "if (!thinkBoxEl)" in md and "createThinkBox()" in md, \
        "message.delta 应在无打开框时另开新框: " + md[:300]

    # message.complete：thinkBoxEl 可能已被 tool.start 置空 → 仍需收束 final 思考
    mc = _extract_event_block(src, "message.complete")
    assert "if (!thinkBoxEl) thinkBoxEl = createThinkBox();" in mc, \
        "message.complete 应在思考框被置空后另开新框收束 final 思考: " + mc[:300]

    # 铁律回归：diff 整行底色同级展示（F3-5）不得被动 —— 相关函数与样式仍在
    for keep in ("diffHighlight", "function diffBlock", ".diff-block .dl.add",
                 ".diff-block .dl.del", "toolSummary"):
        assert keep in src, f"F3-5 diff 展示要素缺失（回归破坏）: {keep}"


# ── F6-2 / F6-3：renderFullHistory 空占位 + 摘要分隔行（node 实跑） ───────

def _node_full_history_f6_test():
    """提取真实 renderFullHistory，桩化 DOM，断言：
    - 现存空 assistant + tool_calls → （工具调用回合）占位
    - resume 带 summary → 摘要分隔行；无 summary → 零新增"""
    src = GUI_FILE.read_text(encoding="utf-8")
    fns = _extract_func(src, "renderFullHistory")
    js = f"""
const assert = require('assert');
const statuses = [];
const msgs = [];
function addMsg(role, text, id, append) {{ msgs.push({{ role, text, id }}); }}
function addTool(name, context, toolId) {{ msgs.push({{ role: 'tool', name, context, id: toolId }}); }}
function addStatus(text) {{ statuses.push(text); }}
const chatEl = {{ scrollTop: 0, scrollHeight: 0 }};
global.window = {{ boboAPI: null }};   // 无归档路径（focus 现存消息 + summary）
{fns}
(async () => {{
  // ── 场景 A：现存消息含纯工具回合（空 assistant + tool_calls）──
  await renderFullHistory('sid_a', {{
    messages: [
      {{ role: 'user', text: '用户消息' }},
      {{ role: 'assistant', text: '', tool_calls: [{{ id: 'c1' }}] }},
      {{ role: 'assistant', text: '正常回复' }},
    ],
  }});
  const textsA = msgs.map(m => m.text || '');
  assert(textsA.includes('（工具调用回合）'), '空 assistant 应占位: ' + JSON.stringify(textsA));
  assert(textsA.includes('正常回复'), '非空 assistant 应原样: ' + JSON.stringify(textsA));
  assert(!textsA.includes(''), '不应再出现空泡泡: ' + JSON.stringify(textsA));
  const statusA = statuses.filter(s => s.includes('摘要'));
  assert(statusA.length === 0, '场景 A 无 summary 不应出摘要行: ' + JSON.stringify(statuses));

  // ── 场景 B：resume 带 summary → 历史顶部摘要分隔行 ──
  msgs.length = 0; statuses.length = 0;
  await renderFullHistory('sid_b', {{
    summary: 'L2 极简摘要：完成了三件套修复',
    messages: [ {{ role: 'user', text: '压缩后第一条' }} ],
  }});
  const summaryLine = statuses.find(s => s.includes('此前对话摘要'));
  assert(summaryLine, '应渲染摘要分隔行: ' + JSON.stringify(statuses));
  assert(summaryLine.includes('L2 极简摘要'), '摘要行应带原文: ' + summaryLine);
  // 摘要行应出现在任何消息之前（历史顶部）
  const firstStatusIdx = statuses.indexOf(summaryLine);
  assert(firstStatusIdx === 0, '摘要行应在历史顶部（第一条状态）: ' + JSON.stringify(statuses));

  // ── 场景 C：空 assistant 无 tool_calls（未知空）→ 不允许崩溃，保持现状渲染 ──
  msgs.length = 0; statuses.length = 0;
  await renderFullHistory('sid_c', {{
    messages: [ {{ role: 'assistant', text: '' }} ],
  }});
  console.log('NODE_F6_FULL_HISTORY_OK');
}})().catch(e => {{ console.error(e); process.exit(1); }});
"""
    return _run_node(js)


def test_f6_2_and_f6_3_full_history_node():
    out = _node_full_history_f6_test()
    assert "NODE_F6_FULL_HISTORY_OK" in out, f"node 实跑失败: {out}"


# ── F6-4：handle_session_resume 时序竞争（后端 pytest 实证） ─────────────

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
        "created_at": "2026-08-13T12:00:00+08:00",
        "title": f"会话_{sid}",
        "messages": messages,
        "summary": summary,
    }
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_f6_4_resume_engine_busy_returns_memory(monkeypatch, tmp_path):
    """引擎忙：resume 返回内存版最新消息（含未落盘回合），禁止磁盘覆盖内存。"""
    from bobo_tui_gateway.handlers import sessions as sess_mod
    from core.session_manager import SessionManager

    sid = "busy_sid_001"
    # 磁盘版（落后：3 条，缺最新回合）
    disk_msgs = [
        {"role": "user", "content": "问题一"},
        {"role": "assistant", "content": "回答一"},
        {"role": "user", "content": "问题二"},
    ]
    # 内存版（最新：5 条，含未落盘的运行中回合）
    mem_msgs = disk_msgs + [
        {"role": "assistant", "content": "", "tool_calls": [{"id": "c1"}]},
        {"role": "user", "content": "引擎正在处理的追问"},
    ]

    mgr = SessionManager(session_dir=str(tmp_path))
    _write_session_file(mgr, sid, disk_msgs, summary="磁盘压缩摘要")
    monkeypatch.setattr(sess_mod, "_session_mgr", mgr)

    ctx = _make_ctx()
    ctx.sessions[sid] = {"id": sid, "title": f"会话_{sid}", "messages": mem_msgs}
    monkeypatch.setattr("core.engine_adapter.is_running", lambda s: s == sid)

    result = sess_mod.handle_session_resume({"session_id": sid}, "rid1", ctx)

    assert "error" not in result, f"resume 不应报错: {result}"
    body = result["result"]
    # 返回内存版（5 条，含最新追问）
    assert body["message_count"] == 5, f"引擎忙应返回内存版 5 条: {body['message_count']}"
    texts = [m["text"] for m in body["messages"]]
    assert "引擎正在处理的追问" in texts, "内存版最新回合必须可见: " + json.dumps(texts)
    # 禁止磁盘版覆盖内存
    assert ctx.sessions[sid]["messages"] is mem_msgs, "引擎忙时不得用磁盘版覆盖内存"
    assert len(ctx.sessions[sid]["messages"]) == 5, "内存会话不得被截断"
    # 摘要字段带回（GUI 渲染分隔摘要行）
    assert body["summary"] == "磁盘压缩摘要", f"summary 应带回: {body.get('summary')}"
    assert body["engine_busy"] is True
    # 空 assistant 的 tool_calls 字段透传（GUI 占位判断依据）
    tc_msgs = [m for m in body["messages"] if m["role"] == "assistant" and m["tool_calls"]]
    assert len(tc_msgs) == 1, "空 assistant 应带 tool_calls 字段: " + json.dumps(body["messages"])
    assert ctx._current == sid, "切回会话时当前会话指向应更新"


def test_f6_4_resume_idle_overwrites_disk(monkeypatch, tmp_path):
    """引擎空闲：磁盘版覆盖内存（原行为），返回磁盘 transcript。"""
    from bobo_tui_gateway.handlers import sessions as sess_mod
    from core.session_manager import SessionManager

    sid = "idle_sid_002"
    disk_msgs = [
        {"role": "user", "content": "问题A"},
        {"role": "assistant", "content": "回答A"},
        {"role": "user", "content": "问题B"},
    ]
    mgr = SessionManager(session_dir=str(tmp_path))
    _write_session_file(mgr, sid, disk_msgs, summary=None)
    monkeypatch.setattr(sess_mod, "_session_mgr", mgr)

    ctx = _make_ctx()
    # 内存里残留一个更旧的版本（模拟不同步）
    ctx.sessions[sid] = {"id": sid, "title": f"会话_{sid}", "messages": []}
    monkeypatch.setattr("core.engine_adapter.is_running", lambda s: False)

    result = sess_mod.handle_session_resume({"session_id": sid}, "rid2", ctx)

    body = result["result"]
    assert body["message_count"] == 3, f"空闲应返回磁盘版 3 条: {body['message_count']}"
    assert len(ctx.sessions[sid]["messages"]) == 3, "空闲时磁盘版应覆盖内存"
    assert body["summary"] == "", "无 summary 应返回空串（前端零变化）"
    assert body["engine_busy"] is False
    # transcript 结构与 GUI 契约一致：assistant 恒带 tool_calls 字段
    for m in body["messages"]:
        if m["role"] == "assistant":
            assert "tool_calls" in m, "assistant 必须带 tool_calls 字段（GUI 占位依据）"
    # 非 assistant 消息不带多余字段（GUI 兼容）
    for m in body["messages"]:
        assert m["role"] in ("user", "assistant", "system"), f"意外 role: {m}"


def test_f6_4_resume_busy_no_mem_session_fallback(monkeypatch, tmp_path):
    """引擎忙但内存无该会话（边缘）：回退磁盘版，不崩溃。"""
    from bobo_tui_gateway.handlers import sessions as sess_mod
    from core.session_manager import SessionManager

    sid = "edge_sid_003"
    disk_msgs = [{"role": "user", "content": "磁盘消息"}]
    mgr = SessionManager(session_dir=str(tmp_path))
    _write_session_file(mgr, sid, disk_msgs)
    monkeypatch.setattr(sess_mod, "_session_mgr", mgr)

    ctx = _make_ctx()
    monkeypatch.setattr("core.engine_adapter.is_running", lambda s: True)

    result = sess_mod.handle_session_resume({"session_id": sid}, "rid3", ctx)

    assert "error" not in result, f"resume 不应报错: {result}"
    body = result["result"]
    assert body["message_count"] == 1, "无内存版时回退磁盘版"
    assert body["engine_busy"] is True
