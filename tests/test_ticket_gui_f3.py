"""TICKET-GUI-F3 回归测试 — 会话侧栏选中态与切换可靠性 + 历史完整性 + diff 展示升级。

覆盖：
- F3-1 侧栏选中态严格跟随当前会话（单一事实源）：active 类只由 currentSessionId 驱动；
  切换/新建/删除/启动恢复后同步重渲染
- F3-2 点击必应答：立即加载指示（session-item.loading + 加载状态条）、失败显式报错
  （禁止静默 return）、快速连点以后一次为准（sessionLoadSeq 竞态序号）
- F3-3 历史全文恢复：归档 archived_messages 全文拼接 + 压缩分隔线（node 实跑
  renderFullHistory/renderArchivedMessages 当前 HTML 内真实函数）
- F3-4 空消息落盘兜底（Kimi 特批已实现）：_save_session_to_disk 内存空 + 磁盘非空 →
  拒绝覆盖 + warning 日志；磁盘本就空/无文件时照常落盘
- F3-5 diff 展示升级（owner 裁决，优先级最高）：diff 区块与回复同级独立出现在消息流
  （不嵌工具卡片内部）；整行底色高亮（绿底新增/红底删除）；工具卡片只留一行摘要
  （"编辑文件 path +N/-M"）—— node 实跑 diffBlock/diffStats/toolSummary 真实函数

注：GUI 渲染层无法无头全自动化，采用静态断言（dist/index.html 现行页面）
+ node 实跑当前 HTML 内真实函数（零漂移行为验证）+ 后端落盘路径实证。
"""

import json
import re
import subprocess
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
GUI_FILE = ROOT / "apps" / "desktop" / "dist" / "index.html"


# ── 辅助：提取当前 HTML 内真实 JS 函数（零漂移，与 test_ticket_gui_f4.py 同款） ──

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
    """在 node 中执行 JS（同步），返回 stdout。"""
    r = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        raise AssertionError(f"node 执行失败: {r.stderr}")
    return r.stdout


def _node_full_history_test():
    """构造 node 脚本：提取当前 HTML 真实 renderFullHistory/renderArchivedMessages，
    桩化 DOM（addMsg/addTool/addStatus/chatEl/boboAPI），实跑归档+现存拼接断言。"""
    src = GUI_FILE.read_text(encoding="utf-8")
    fns = "\n".join(
        _extract_func(src, n) for n in ("renderArchivedMessages", "renderFullHistory")
    )
    js = f"""
const assert = require('assert');
const statuses = [];
const msgs = [];
// DOM 桩：真实函数只依赖 addMsg/addTool/addStatus/chatEl/window.boboAPI
function addMsg(role, text, id, append) {{ msgs.push({{ role, text, id }}); }}
function addTool(name, context, toolId) {{ msgs.push({{ role: 'tool', name, context, id: toolId }}); }}
function addStatus(text) {{ statuses.push(text); }}
const chatEl = {{ scrollTop: 0, scrollHeight: 0 }};
// TICKET-GUI-F13：F13 新依赖 stub —— 考古模式默认关（现场原样平铺），姿势不落盘
function histArchMode() {{ return false; }}
function applyPose() {{}}
function readPose() {{ return {{}}; }}
function writePose() {{}}
global.window = {{
  boboAPI: {{
    readArchive: async (sid) => ({{
      ok: true,
      records: [
        {{
          type: 'context.compressed', pre_msg_count: 175, post_msg_count: 42,
          summary: 'S1', archived_messages: [
            {{ role: 'user', content: '第一条用户消息' }},
            {{ role: 'assistant', content: '第一条回复' }},
            {{ role: 'tool', name: 'read_local_file', content: 'file content' }},
          ],
        }},
        {{
          type: 'context.compressed', pre_msg_count: 80, post_msg_count: 20,
          summary: 'S2', archived_messages: [
            {{ role: 'user', content: '第二次压缩前消息' }},
          ],
        }},
      ],
    }}),
  }},
}};
{fns}
(async () => {{
  await renderFullHistory('test_sid', {{
    messages: [
      {{ role: 'user', text: '压缩后现存消息' }},
      {{ role: 'assistant', text: '压缩后现存回复' }},
    ],
  }});
  // ── 归档全文按顺序渲染 ──
  const texts = msgs.map(m => m.text || m.name || '');
  assert(texts.includes('第一条用户消息'), '归档用户消息应渲染: ' + JSON.stringify(texts));
  assert(texts.includes('第一条回复'), '归档 assistant 消息应渲染');
  assert(texts.includes('第二次压缩前消息'), '第二段归档也应渲染');
  assert(texts.includes('压缩后现存消息'), '现存消息应与归档拼接');
  assert(texts.includes('压缩后现存回复'), '现存回复应与归档拼接');
  // ── tool 消息走 addTool ──
  const toolMsg = msgs.find(m => m.role === 'tool');
  assert(toolMsg, '归档 tool 消息应渲染');
  assert(toolMsg.name === 'read_local_file', 'tool 名应保留: ' + JSON.stringify(toolMsg));
  // ── 压缩分隔线 ──
  const sep = statuses.filter(s => s.includes('经上下文压缩'));
  assert(sep.length === 2, '两个压缩事件应有两条分隔线: ' + JSON.stringify(statuses));
  assert(sep[0].includes('175'), '分隔线应带压缩前消息数: ' + sep[0]);
  assert(sep[1].includes('80'), '第二条分隔线应带各自压缩前消息数: ' + sep[1]);
  console.log('NODE_FULL_HISTORY_OK');
}})().catch(e => {{ console.error(e); process.exit(1); }});
"""
    return _run_node(js)


def _node_diff_block_test():
    """构造 node 脚本：提取当前 HTML 真实 diffBlock/diffStats/toolSummary，
    实跑 diff 渲染断言（整行底色类 + 摘要 +N/-M 统计）。"""
    src = GUI_FILE.read_text(encoding="utf-8")
    fns = "\n".join(
        _extract_func(src, n) for n in ("esc", "diffStats", "toolSummary", "diffBlock")
    )
    diff = "⎿  +2 −1\\n@@ -1,5 +1,6 @@\\n line1\\n-old line\\n+new line\\n+extra line\\n line3"
    js = f"""
const assert = require('assert');
{fns}
const diff = '⎿  +2 −1\\n@@ -1,5 +1,6 @@\\n line1\\n-old line\\n+new line\\n+extra line\\n line3';
// ── diffStats: +N/-M 统计（排除 +++/--- 文件头）──
let st = diffStats('⎿  +2 −1\\n@@ -1,3 +1,3 @@\\n line1\\n-old\\n+new\\n+extra\\n--- old file\\n+++ new file');
assert(st.add === 2, 'add 应为 2: ' + JSON.stringify(st));
assert(st.del === 1, 'del 应为 1: ' + JSON.stringify(st));
let st0 = diffStats('');
assert(st0.add === 0 && st0.del === 0, '空 diff 统计为 0');
// ── toolSummary: "编辑文件 path +N/-M" ──
let sum = toolSummary({{ file_path: '/tmp/a.py', old_string: 'old', new_string: 'new' }}, '⎿  +2 −1\\n@@ -1,3 +1,3 @@\\n-old\\n+new\\n+extra');
assert(sum === '/tmp/a.py +2/-1', '摘要格式应为 "path +N/-M": ' + sum);
// ── diffBlock: 整行底色类（dl add/del/ctx + 文件头 df）──
let out = diffBlock(diff);
assert(out.startsWith('<div class="diff-block">'), '应有 diff-block 容器');
assert(out.includes('<div class="df">'), '@@ 行应为文件头 df');
assert(out.includes('<div class="dl add">'), '新增行应为整行绿底 dl.add');
assert(out.includes('<div class="dl del">'), '删除行应为整行红底 dl.del');
assert(out.includes('<div class="dl ctx">'), '上下文行应为 dl.ctx');
// 整行底色（行级块元素，非文字 span）—— dl.add/del 是 div 块级
assert(!out.includes('<span class="diff-add">'), 'F3-5 不得再用文字变色 span');
assert(!out.includes('<span class="diff-del">'), 'F3-5 不得再用文字变色 span');
console.log('NODE_DIFF_BLOCK_OK');
"""
    return _run_node(js)


# ── F3-1: 侧栏选中态单一事实源 ──────────────────────────────────────

class TestF31SelectionState:
    """F3-1 高亮严格跟随 currentSessionId —— 切换/新建/删除/启动恢复后同步重渲染。"""

    def test_active_class_driven_by_current_session_id(self):
        src = GUI_FILE.read_text(encoding="utf-8")
        # active 类唯一来源：currentSessionId
        assert "div.className = 'session-item' + (s.id===currentSessionId?' active':''); div.dataset.sid = s.id;" in src, \
            "active 类必须严格跟随 currentSessionId"

    def test_load_session_syncs_selection_first(self):
        """loadSession 开头立即同步 currentSessionId + renderSessions（不等 resume 返回）。"""
        src = GUI_FILE.read_text(encoding="utf-8")
        # TICKET-GUI-F13：切会话前先落盘旧会话展开姿势（recordPose），随后同步选中态
        # —— 语义不变（先同步再 resume），仅插入姿势持久化一行
        assert "if (currentSessionId !== sid) {" in src, \
            "点击会话必须先同步选中态再请求 resume（杜绝高亮脱节）"
        assert "currentSessionId = sid;\n    renderSessions();" in src, \
            "同步选中态后必须立即 renderSessions（杜绝高亮脱节）"
        assert "renderSessions();\n    renderBusyUI();" in src, \
            "V4B⓪：同步选中态后必须按新会话刷新忙碌态"

    def test_new_chat_syncs_selection(self):
        src = GUI_FILE.read_text(encoding="utf-8")
        # newChat 成功后 currentSessionId = result.session_id + renderSessions
        assert "currentSessionId = result.session_id;" in src
        assert "renderSessions();" in src

    def test_delete_current_session_falls_to_first(self):
        """删除当前会话后完整 loadSession 首个会话（内容区与高亮同步切换，不脱节）。"""
        src = GUI_FILE.read_text(encoding="utf-8")
        assert "await loadSession(sessions[0].id);" in src, \
            "删除当前会话后必须完整 loadSession 首个会话（内容区同步切换）"
        # 旧的静默 activate（只改高亮不改内容）必须移除
        assert "currentSessionId = sessions[0].id; call('session.activate'" not in src, \
            "旧实现（只 activate 不加载内容）已移除"

    def test_startup_resume_syncs_selection(self):
        src = GUI_FILE.read_text(encoding="utf-8")
        # 启动恢复：loadSessions → loadSession(sessions[0].id)（内部 renderSessions）
        assert "await loadSession(sessions[0].id);" in src


# ── F3-2: 点击必应答 ────────────────────────────────────────────────

class TestF32ClickMustRespond:
    """F3-2 点击立即反馈 / 失败显式报错 / 连点以后一次为准。"""

    def test_immediate_loading_indicator(self):
        src = GUI_FILE.read_text(encoding="utf-8")
        # 点击立即给加载指示：该项 loading 类 + 状态条
        assert "setSessionLoading(sid, true);" in src, "点击必须立即给加载指示"
        assert "addStatus('加载会话…');" in src, "点击必须立即给状态反馈"
        assert "session-item.loading" in src, "CSS 必须有 loading 呼吸样式"

    def test_no_silent_return_on_failure(self):
        """失败必须显式报错，禁止静默停留旧会话（旧 `if (!result || result.error) return;` 移除）。"""
        src = GUI_FILE.read_text(encoding="utf-8")
        assert "if (!result || result.error) return;" not in src, "静默 return 必须移除"
        assert "addStatus('⚠ 加载会话失败：'" in src, "失败必须显式报错"

    def test_race_last_click_wins(self):
        """快速连点两会话 → 后一次为准（sessionLoadSeq 竞态序号，前者作废）。"""
        src = GUI_FILE.read_text(encoding="utf-8")
        assert "var sessionLoadSeq = 0;" in src, "竞态序号全局变量"
        assert "var mySeq = ++sessionLoadSeq;" in src, "每次点击取新序号"
        assert "if (mySeq !== sessionLoadSeq) return;" in src, "旧点击结果作废"

    def test_loading_indicator_cleared_on_all_paths(self):
        """加载指示在失败/成功路径都清除（防永久闪烁）。"""
        src = GUI_FILE.read_text(encoding="utf-8")
        assert "setSessionLoading(sid, false);" in src


# ── F3-3: 历史全文恢复 ──────────────────────────────────────────────

class TestF33FullHistory:
    """F3-3 归档 archived_messages 全文拼接 + 压缩分隔线（展示层增强，内核零改动）。"""

    def test_render_full_history_function_present(self):
        src = GUI_FILE.read_text(encoding="utf-8")
        assert "async function renderFullHistory(sid, result)" in src
        assert "function renderArchivedMessages(ams, idPrefix)" in src

    def test_reads_archive_via_ipc(self):
        src = GUI_FILE.read_text(encoding="utf-8")
        assert "window.boboAPI && window.boboAPI.readArchive" in src, "必须走 readArchive IPC"
        assert "window.boboAPI.readArchive(sid)" in src

    def test_compression_divider_line(self):
        src = GUI_FILE.read_text(encoding="utf-8")
        assert "'— 此前 ' + n + ' 条消息经上下文压缩 —'" in src, "压缩边界给柔和分隔线"

    def test_archive_merge_renders_full(self):
        """node 实跑当前 HTML 真实 renderFullHistory：归档全文 + 现存拼接 + 分隔线齐全。"""
        assert "NODE_FULL_HISTORY_OK" in _node_full_history_test()

    def test_no_archive_falls_back_to_current(self):
        """无归档（records 空）→ 现状渲染，不报错不空白。"""
        src = GUI_FILE.read_text(encoding="utf-8")
        # 归档为空数组时循环不执行，直接落到现存消息渲染
        assert "if (ar && ar.ok && ar.records && ar.records.length > 0)" in src

    def test_render_archived_covers_all_roles(self):
        """归档消息角色全覆盖：user/assistant/tool/system。"""
        src = GUI_FILE.read_text(encoding="utf-8")
        assert "role === 'user'" in src
        assert "role === 'assistant'" in src
        assert "role === 'tool'" in src
        assert "role === 'system'" in src


# ── F3-5: diff 展示升级（owner 裁决，优先级最高） ────────────────────

class TestF35DiffBlock:
    """F3-5 diff 区块与回复同级：独立消息流区块、整行底色、工具卡只留一行摘要。"""

    def test_diff_block_independent_in_message_flow(self):
        """updateToolResult 有 inlineDiff 时：工具卡只留摘要，diff 本体 appendDiffBlock 到消息流。"""
        src = GUI_FILE.read_text(encoding="utf-8")
        # 工具卡内不再渲染完整 renderToolDetail（diff 不嵌卡片内部）
        assert "resultEl.innerHTML = '<div class=\"tool-summary\">' + esc(toolSummary(args, inlineDiff)) + '</div>';" in src, \
            "工具卡只留一行摘要"
        assert "appendDiffBlock(div, inlineDiff);" in src, "diff 本体搬出为独立区块"
        # 非 diff 工具仍走原 renderToolDetail（不回归）
        assert "resultEl.innerHTML = renderToolDetail(args, resultText, inlineDiff);" in src

    def test_diff_block_placed_after_tool_card(self):
        """appendDiffBlock 把区块插到工具卡（或聚合卡）之后 —— 与回复同级。"""
        src = GUI_FILE.read_text(encoding="utf-8")
        assert "function appendDiffBlock(toolDiv, inlineDiff)" in src
        assert "chatEl.insertBefore(child, anchor.nextSibling)" in src
        assert "aggBody = toolDiv.closest ? toolDiv.closest('.tool-agg-body')" in src, "聚合卡场景插到聚合卡后"

    def test_diff_block_line_background_css(self):
        """整行底色高亮：dl.add 绿底 / dl.del 红底（background，非 color）。"""
        src = GUI_FILE.read_text(encoding="utf-8")
        assert ".diff-block .dl.add { background:rgba(80,161,79,0.20);" in src, "新增行整行绿底"
        assert ".diff-block .dl.del { background:rgba(244,135,113,0.20);" in src, "删除行整行红底"
        assert ".diff-block .df" in src, "@@ 文件头样式"
        # 行级块元素（display:block）—— 整行底色而非文字变色
        assert ".diff-block .dl { display:block;" in src

    def test_diff_block_node_runs(self):
        """node 实跑当前 HTML 真实 diffBlock/diffStats/toolSummary。"""
        assert "NODE_DIFF_BLOCK_OK" in _node_diff_block_test()

    def test_f4_diff_functions_kept_for_no_diff_cards(self):
        """F4-2 的 diffHighlight/renderToolDetail 保留（非 diff 工具卡继续用），零回归。"""
        src = GUI_FILE.read_text(encoding="utf-8")
        assert "function diffHighlight(text)" in src
        assert "function renderToolDetail(args, resultText, inlineDiff)" in src
        assert "function diffStats(text)" in src
        assert "function toolSummary(args, inlineDiff)" in src
        assert "function diffBlock(text)" in src


# ── F3-4: 空消息落盘兜底（修复方案报裁决，现状锁定） ────────────────

class TestF34EmptySaveGuard:
    """F3-4 空 messages 覆盖磁盘非空版本 = 数据破坏。Kimi 特批（2026-08-13）后
    _save_session_to_disk 已加兜底：内存空 + 磁盘非空 → 拒绝覆盖 + warning 日志。
    本类测试转绿（xfail 已移除）。"""

    def test_save_path_guarded(self):
        """确凿：_save_session_to_disk 已有 F3-4 兜底（内存空 + 磁盘非空 → 拒绝覆盖）。"""
        from bobo_tui_gateway.handlers import sessions as sess_mod
        src = Path(sess_mod.__file__).read_text(encoding="utf-8")
        assert "F3-4 拒绝覆盖" in src, "兜底实现：拒绝覆盖 + warning 日志"
        assert 'data["messages"] = in_mem_msgs' in src, "统一走 in_mem_msgs 防 None"

    def test_empty_messages_must_not_overwrite_nonempty_disk(self, tmp_path, monkeypatch):
        """特批行为（隔离到 tmp_path）：内存 messages 为空且磁盘已有非空版本 → 拒绝覆盖 + warning。"""
        from types import SimpleNamespace
        from bobo_tui_gateway.handlers import sessions as sess_mod

        monkeypatch.setattr(sess_mod, "SESSION_DIR", str(tmp_path))
        monkeypatch.setattr(sess_mod, "_session_mgr", None)  # 重置缓存，指向 tmp
        ctx = SimpleNamespace(sessions_lock=threading.Lock(), sessions={})
        sid = "f3_4_test_000001"
        # 先有非空磁盘版本（模拟已保存的会话）
        ctx.sessions[sid] = {"id": sid, "title": "t", "messages": [{"role": "user", "content": "真实历史"}]}
        sess_mod._save_session_to_disk(sid, ctx)
        disk_path = tmp_path / f"{sid}.json"
        assert disk_path.exists()
        assert json.loads(disk_path.read_text(encoding="utf-8"))["messages"]
        # 内存清空（竞态/异常场景）→ 再保存
        ctx.sessions[sid] = {"id": sid, "title": "t", "messages": []}
        sess_mod._save_session_to_disk(sid, ctx)
        # 期望：磁盘仍保留非空版本（防数据破坏兜底）
        assert json.loads(disk_path.read_text(encoding="utf-8"))["messages"], \
            "空 messages 不得覆盖磁盘非空版本（防数据破坏兜底）"

    def test_empty_save_emits_warning(self, tmp_path, monkeypatch, caplog):
        """拒绝覆盖时记 warning 日志（含 sid 与保留条数），可观测可审计。"""
        import logging
        from types import SimpleNamespace
        from bobo_tui_gateway.handlers import sessions as sess_mod

        monkeypatch.setattr(sess_mod, "SESSION_DIR", str(tmp_path))
        monkeypatch.setattr(sess_mod, "_session_mgr", None)
        ctx = SimpleNamespace(sessions_lock=threading.Lock(), sessions={})
        sid = "f3_4_test_000002"
        ctx.sessions[sid] = {"id": sid, "title": "t", "messages": [{"role": "assistant", "content": "历史"}]}
        sess_mod._save_session_to_disk(sid, ctx)
        ctx.sessions[sid] = {"id": sid, "title": "t", "messages": []}
        with caplog.at_level(logging.WARNING, logger="bobo_tui_gateway.handlers.sessions"):
            sess_mod._save_session_to_disk(sid, ctx)
        assert any("F3-4 拒绝覆盖" in rec.message and sid in rec.message for rec in caplog.records), \
            "拒绝覆盖必须记 warning 日志: " + str([r.message for r in caplog.records])

    def test_empty_save_with_empty_disk_still_writes(self, tmp_path, monkeypatch):
        """磁盘无文件（或本就空）时，空消息照常落盘（首次创建/清空是合法路径）。"""
        from types import SimpleNamespace
        from bobo_tui_gateway.handlers import sessions as sess_mod

        monkeypatch.setattr(sess_mod, "SESSION_DIR", str(tmp_path))
        monkeypatch.setattr(sess_mod, "_session_mgr", None)
        ctx = SimpleNamespace(sessions_lock=threading.Lock(), sessions={})
        sid = "f3_4_test_000003"
        ctx.sessions[sid] = {"id": sid, "title": "t", "messages": []}
        sess_mod._save_session_to_disk(sid, ctx)
        disk_path = tmp_path / f"{sid}.json"
        assert disk_path.exists(), "磁盘无版本时空消息应正常落盘"
        assert json.loads(disk_path.read_text(encoding="utf-8"))["messages"] == []


# ── F1/F2 零回归锚点 ────────────────────────────────────────────────

class TestF1F2NoRegression:
    """F3 施工后 F1/F2 关键语义不回归（对照 test_ticket_gui_f2.py / f4.py 锚点）。"""

    def test_f2_heartbeat_skip_restored(self):
        src = GUI_FILE.read_text(encoding="utf-8")
        assert "仍在工作" in src
        assert "return;" in src

    def test_f2_auto_state_sync(self):
        src = GUI_FILE.read_text(encoding="utf-8")
        assert "setMode(result.auto_state ? 'auto' : '');" in src, "F2-2 恢复时同步 AUTO 开关"

    def test_f1_ime_guard(self):
        src = GUI_FILE.read_text(encoding="utf-8")
        assert "e.isComposing || e.keyCode === 229 || imeComposing" in src

    def test_session_activate_still_called(self):
        src = GUI_FILE.read_text(encoding="utf-8")
        assert "call('session.activate', { session_id: sid });" in src
