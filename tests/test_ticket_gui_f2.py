"""TICKET-GUI-F2 回归测试 — 发送键语义 / AUTO 开关通道 / 工具长链 / 信息层级。

覆盖：
- F2-2 后端通道：slash.exec /auto 真实翻转会话级 AUTO MODE + session.auto_state 事件
  （GUI 输入框旁开关复用该通道，非仅 UI 变化）
- D-1d 断点②：edit_file 真实输出含 <<<INLINE_DIFF>>> 块，engine_adapter 解析出 diff
  （GUI 编辑卡默认展开的红绿高亮源）
- F2-1/F2-4/F2-3 GUI 静态防回归：dist/index.html 现行页面断言关键语义存在
- F1-1 防护不回归：IME 组词拦截三条件仍在

注：GUI 渲染层（React 源码 apps/desktop/src 仅留参考，dist 为现行页面，
见 commit 7f0a6b4 "R1 修正"）无法在无头环境全自动化，静态断言 + 后端通道
实证作为回归防线；交互验收（回车/Shift/IME 三路实证、聚合卡展开）实跑留证。
"""

import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
GUI_FILE = ROOT / "apps" / "desktop" / "dist" / "index.html"


# ── F2-2: AUTO 开关后端通道 ────────────────────────────────────────

class TestF22AutoToggleChannel:
    """F2-2: 输入框旁 AUTO 开关复用 slash.exec /auto —— 后端真实翻转 + 事件推送。"""

    def test_auto_flip_toggles_backend_state(self, monkeypatch):
        import bobo_tui_gateway.handlers.prompts as P

        captured = []
        monkeypatch.setattr(P, "emit", lambda event, sid, data: captured.append((event, sid, data)))

        class Ctx:
            pass

        ctx = Ctx()
        ctx.auto_mode = {}

        # 无参 = 翻转 on
        r1 = P.handle_slash_exec({"command": "auto", "session_id": "s1"}, "r1", ctx)
        assert ctx.auto_mode.get("s1") is True, f"翻转应置 True: {r1}"
        assert captured[-1][0] == "session.auto_state"
        assert captured[-1][2]["on"] is True

        # 再翻 = off
        r2 = P.handle_slash_exec({"command": "auto", "session_id": "s1"}, "r2", ctx)
        assert ctx.auto_mode.get("s1") is False, f"再翻应置 False: {r2}"
        assert captured[-1][2]["on"] is False

        # 显式 on
        r3 = P.handle_slash_exec({"command": "auto on", "session_id": "s1"}, "r3", ctx)
        assert ctx.auto_mode.get("s1") is True, f"显式 on 应置 True: {r3}"
        assert captured[-1][2]["on"] is True

        # 显式 off
        r4 = P.handle_slash_exec({"command": "auto off", "session_id": "s1"}, "r4", ctx)
        assert ctx.auto_mode.get("s1") is False, f"显式 off 应置 False: {r4}"
        assert captured[-1][2]["on"] is False

    def test_gui_listens_auto_state_for_badge_sync(self):
        """GUI 已监听 session.auto_state → setMode 联动状态条徽标与输入框旁开关。"""
        src = GUI_FILE.read_text(encoding="utf-8")
        assert "session.auto_state" in src
        assert "function setMode" in src
        # 开关与徽标同源联动
        assert "auto-toggle" in src
        assert "classList.toggle('on', mode === 'auto')" in src
        # 点击走 slash.exec /auto（复用后端通道，不发明新协议）
        assert "slash.exec" in src
        assert "command: 'auto'" in src

    def test_full_rpc_chain_auto_toggle_takes_effect(self):
        """实弹（完整 RPC 分发）：GUI 开关同通道 slash.exec /auto →
        后端 auto_mode 真实翻转（session.resume 回读验证，非仅 UI 变化）。"""
        from bobo_tui_gateway.server import dispatch

        r = dispatch({"id": "f2-1", "method": "session.create",
                      "params": {"title": "F2 实弹验证"}})
        assert r.get("result") and r["result"].get("session_id"), r
        sid = r["result"]["session_id"]

        # GUI 开关点击 → slash.exec /auto（无参=翻转）
        r2 = dispatch({"id": "f2-2", "method": "slash.exec",
                       "params": {"command": "auto", "session_id": sid}})
        assert "开启" in r2["result"]["output"], r2

        # 回读后端权威状态
        r3 = dispatch({"id": "f2-3", "method": "session.resume",
                       "params": {"session_id": sid}})
        assert r3["result"]["auto_state"] is True, r3

        # 再翻转 → off
        dispatch({"id": "f2-4", "method": "slash.exec",
                  "params": {"command": "auto", "session_id": sid}})
        r5 = dispatch({"id": "f2-5", "method": "session.resume",
                       "params": {"session_id": sid}})
        assert r5["result"]["auto_state"] is False, r5


# ── D-1d 断点②: edit_file diff 链路 ────────────────────────────────

class TestF24DiffChain:
    """D-1d 断点② 实证：真实 edit_file 发出 inline_diff，adapter 可解析。"""

    def test_edit_file_output_contains_inline_diff_block(self):
        from tools.edit_file import execute as edit_execute

        tmp = Path(tempfile.mkdtemp(prefix="f2_diff_"))
        target = tmp / "sample.txt"
        target.write_text("line1\nline2\nline3\n", encoding="utf-8")

        out = edit_execute(str(target), "line2", "line2-CHANGED")
        assert "<<<INLINE_DIFF>>>" in out, "edit_file 结果应含 INLINE_DIFF 块"
        assert "<<<END_INLINE_DIFF>>>" in out

        # 模拟 engine_adapter.py:106-110 的解析
        head, _, tail = out.partition("<<<INLINE_DIFF>>>")
        inline_diff, _, _ = tail.partition("<<<END_INLINE_DIFF>>>")
        inline_diff = inline_diff.strip()
        assert inline_diff, "diff 内容非空"
        assert "+line2-CHANGED" in inline_diff, f"diff 应含新增行: {inline_diff}"
        assert "-line2" in inline_diff, f"diff 应含删除行: {inline_diff}"

    def test_adapter_parses_inline_diff_from_tool_output(self):
        """engine_adapter 的 tool_result 分支把 INLINE_DIFF 块提取为 payload.inline_diff。"""
        src = (ROOT / "core" / "engine_adapter.py").read_text(encoding="utf-8")
        assert '"<<<INLINE_DIFF>>>" in tool_output' in src
        assert '"inline_diff": inline_diff' in src

    def test_engine_round_edit_file_diff_flow(self, monkeypatch):
        """引擎真实回合（真 execute_tool + mock LLM 驱动）：edit_file 执行 →
        tool_result 事件 result 含 INLINE_DIFF 块（GUI diff 默认展开的真实数据源）。"""
        import json

        import core.engine as engine_mod
        from core.tool_executor import execute_tool

        tmp = Path(tempfile.mkdtemp(prefix="f2_round_"))
        target = tmp / "notes.md"
        target.write_text("alpha\nbeta\ngamma\n", encoding="utf-8")

        events = []

        def cb(et, d):
            events.append((et, d))

        class FakeLLM:
            def __init__(self):
                self.n = 0

            def __call__(self, messages, stream_callback=None, retry_callback=None,
                         tools_override=None, **kw):
                self.n += 1
                if self.n == 1:
                    tc = [{"id": "t1", "type": "function", "function": {
                        "name": "edit_file",
                        "arguments": json.dumps({"file_path": str(target),
                                                  "old_string": "beta",
                                                  "new_string": "beta-UPDATED"})}}]
                    return {"choices": [{"message": {"content": None, "tool_calls": tc}}],
                            "usage": {}}
                return {"choices": [{"message": {"content": "完成"}}], "usage": {}}

        monkeypatch.setattr(engine_mod.Engine, "_build_system_prompt",
                            lambda self: "You are a helpful assistant.")
        engine = engine_mod.Engine(llm_caller=FakeLLM(), tool_executor=execute_tool,
                                   callback=cb, test_mode=True,
                                   auto_mode_getter=lambda: True)
        monkeypatch.setattr(engine.injector, "build_messages",
                            lambda system_prompt=None, user_input=None, tools_schema=None,
                                   extra_categories=None, session_id="":
                            [{"role": "system", "content": system_prompt}])
        monkeypatch.setattr(engine.proactive, "inject_context", lambda msgs: msgs)
        monkeypatch.setattr(engine.proactive, "mode", "off")
        monkeypatch.setattr(engine.skill_loader, "load_standards", lambda: [])
        engine.verifier.check_and_inject = lambda *a, **kw: False
        engine._worker_reminded = True
        monkeypatch.setattr(engine, "_check_guards", lambda: False)

        engine.run(user_input="把 beta 改成 beta-UPDATED")
        assert engine.state == engine.STATE_DONE, engine.state

        tool_calls = [d for (et, d) in events if et == "tool_call"]
        tool_results = [d for (et, d) in events if et == "tool_result"]
        assert any(d.get("name") == "edit_file" for d in tool_calls), events
        edit_results = [d for d in tool_results if "<<<INLINE_DIFF>>>" in d.get("result", "")]
        assert edit_results, "edit_file 的 tool_result 应含 INLINE_DIFF 块"
        assert "beta-UPDATED" in edit_results[0]["result"]
        # 文件真实被改
        assert "beta-UPDATED" in target.read_text(encoding="utf-8")

    def test_gui_edit_card_diff_default_open(self):
        """F2-4: GUI 编辑类工具卡（带 inline_diff）默认展开 —— diff 红绿高亮不点可见。"""
        src = GUI_FILE.read_text(encoding="utf-8")
        assert "if (inlineDiff) { resultEl.classList.add('open'); toggleEl.textContent = '▾'; }" in src
        # diffHighlight 红绿高亮函数仍在
        assert "diff-add" in src and "diff-del" in src and "diff-file" in src


# ── F2-1: 发送键语义 + F1-1 防护不回归 ──────────────────────────────

class TestF21SendSemantics:
    """F2-1 回车发送 / Shift+回车换行 / IME 组词上屏不发送；F1-1 防护不回归。"""

    def test_enter_sends_shift_enter_newline(self):
        src = GUI_FILE.read_text(encoding="utf-8")
        assert "if (e.key === 'Enter') {" in src
        assert "if (e.shiftKey) return;" in src, "Shift+回车=换行（不拦截）"
        assert "e.preventDefault(); sendEl.click();" in src, "回车=发送"
        assert "if (e.metaKey || e.ctrlKey) { e.preventDefault(); sendEl.click(); return; }" in src, "⌘/Ctrl+回车兼容别名保留"

    def test_f1_ime_guard_not_regressed(self):
        """F1-1 防护三条件必须全在（isComposing / keyCode 229 / imeComposing）。"""
        src = GUI_FILE.read_text(encoding="utf-8")
        assert "e.isComposing || e.keyCode === 229 || imeComposing" in src
        assert "compositionstart" in src and "compositionend" in src
        assert "imeComposing" in src


# ── F2-4: 心跳单条原地更新 + 原始输出收起 ───────────────────────────

class TestF24Hierarchy:
    """F2-4 信息层级：心跳单条更新、原始输出收起、思考折叠保持。"""

    def test_heartbeat_updates_in_place(self):
        src = GUI_FILE.read_text(encoding="utf-8")
        assert "querySelectorAll('.status')" in src
        assert "仍在工作" in src
        # 遍历找最后一条 heartbeat 原地替换（不再只看 lastElementChild）
        assert "for (var hi = sts.length - 1" in src

    def test_heartbeat_history_not_restored(self):
        src = GUI_FILE.read_text(encoding="utf-8")
        assert "m.text.indexOf('仍在工作') === 0) return;" in src, "历史心跳残留不恢复"

    def test_raw_output_collapsed_with_show_all(self):
        src = GUI_FILE.read_text(encoding="utf-8")
        assert "showProjectFile(filepath, full)" in src
        assert "显示全部" in src
        assert "原始输出过长已收起" in src

    def test_thinking_still_collapsed_f1_2(self):
        """F1-2 思考折叠语义保持（默认收起只留摘要行）。"""
        src = GUI_FILE.read_text(encoding="utf-8")
        assert "collapseThinkBox" in src
        assert "think-box.collapsed" in src


# ── F2-3: 工具长链聚合 ──────────────────────────────────────────────

class TestF23Aggregation:
    """F2-3 工具长链 >3 步聚合卡。"""

    def test_aggregation_logic_present(self):
        src = GUI_FILE.read_text(encoding="utf-8")
        assert "roundToolEls" in src
        assert "roundAggregated" in src
        assert "已执行 " in src
        assert "tool-agg-body" in src
        assert "roundToolEls.length === 4" in src, "第 4 步触发聚合（前 3 步收进聚合卡）"
        # 回合结束重置
        assert "roundToolEls = []; roundAggregated = false;" in src
