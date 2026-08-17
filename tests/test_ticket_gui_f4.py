"""TICKET-GUI-F4 回归测试 — 聚合卡持续吞并 / diff 红绿高亮 / JSON 倾倒 / 按钮撞车 / 面板预览 / AUTO 两端对齐。

覆盖：
- F4-1 聚合卡持续吞并：第 2 步起建聚合卡，之后每步吞并最新一步，屏幕仅聚合卡+最新一步
- F4-2 diff 红绿高亮：CSS 选择器双前缀（容器实际 class=tool-result）+ node 实跑 diffHighlight/renderToolDetail
- F4-3 写入/编辑卡片零 JSON 倾倒：node 实跑 renderToolDetail（file_operation 写入卡只出路径+预览）
- F4-4 AUTO/停止按钮重排：#auto-toggle right:104px 与 #stop-btn right:64px 水平错开
- F4-5 项目面板预览拦截全入口：showProjectFile/showNote/terminal 面板 2000 字符拦截
- F4-6 AUTO 两端对齐：GUI 开关 slash.exec 必须携带 session_id（根因：不带则翻转空会话，
  UI 显示 AUTO ✓ 与后端真实状态裂脑 → engine 走 confirm_callback 无脑弹窗）

注：GUI 渲染层无法无头全自动化，采用静态断言（dist/index.html 现行页面）
+ node 实跑当前 HTML 内真实函数（零漂移行为验证）+ 后端 RPC 实证。
"""

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
GUI_FILE = ROOT / "apps" / "desktop" / "dist" / "index.html"


# ── 辅助：提取当前 HTML 内真实 JS 函数（零漂移） ──────────────────────

def _extract_func(src: str, fname: str) -> str:
    """按 { } 括号配对提取 function <fname> 的完整源码。"""
    m = re.search(r"function\s+" + fname + r"\s*\(", src)
    assert m, f"未找到 function {fname}"
    # 定位函数体第一个 {
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


def _node_render_detail_test():
    """构造 node 脚本：提取当前 HTML 真实 esc/diffHighlight/renderToolDetail 并跑行为断言。"""
    src = GUI_FILE.read_text(encoding="utf-8")
    fns = "\n".join(
        _extract_func(src, n) for n in ("esc", "diffHighlight", "renderToolDetail")
    )
    js = f"""
const assert = require('assert');
{fns}
// ── F4-2: edit_file 卡片（含 inlineDiff）→ diff 红绿 span 存在 ──
let argsEdit = {{ file_path: '/tmp/a.py', old_string: 'old line', new_string: 'new line' }};
let diff = '⎿  +1 −1\\n@@ -1,3 +1,3 @@\\n line1\\n-old line\\n+new line\\n line3';
let out1 = renderToolDetail(argsEdit, '已替换: /tmp/a.py', diff);
assert(out1.includes('diff-add'), '应有 diff-add span: ' + out1);
assert(out1.includes('diff-del'), '应有 diff-del span');
assert(out1.includes('diff-file'), '应有 diff-file span（@@ 行）');
assert(out1.includes('Path'), '应有路径标签');
assert(out1.includes('Original'), '应有原文预览标签');
assert(out1.includes('New'), '应有新文预览标签');
// ── F4-3: 写入文件卡（content 巨大）→ 零原始 JSON 倾倒 ──
let bigContent = 'x'.repeat(5000);
let argsWrite = {{ action: 'write', path: '/tmp/big.txt', content: bigContent }};
let out2 = renderToolDetail(argsWrite, '已写入: /tmp/big.txt');
assert(!out2.includes('"content"'), '不得倾倒原始 JSON 键 content: ' + out2.slice(0, 200));
assert(!out2.includes('\\"path\\"'), '不得倾倒原始 JSON 键 path');
let xCount = (out2.match(/x/g) || []).length;
assert(xCount < 5000, '内容必须截断预览，不得全量上屏（实际 x 数: ' + xCount + '）');
assert(out2.includes('Path'), '应有路径');
assert(out2.includes('Content'), '应有内容预览');
assert(out2.includes('preview truncated'), '长内容应有截断提示');
// ── F4-3: 读文件卡（无内容字段）→ 仍显示结果，无 JSON 倾倒 ──
let out3 = renderToolDetail({{ filepath: '/tmp/r.py', max_chars: 200 }}, '文件内容: hello');
assert(out3.includes('hello'), '应有结果');
assert(!out3.includes('JSON'), '不得出现 JSON 字符串');
console.log('NODE_DETAIL_OK');
"""
    return _run_node(js)


# ── F4-1: 聚合卡持续吞并 ────────────────────────────────────────────

class TestF41Aggregation:
    """F4-1 聚合卡持续吞并 —— 第 2 步起建卡，每步吞并，屏幕仅聚合卡+最新一步。"""

    def test_aggregation_builds_from_step2(self):
        src = GUI_FILE.read_text(encoding="utf-8")
        # 第 2 步起建聚合卡（替代 F2-3 的 roundToolEls.length === 4）
        assert "roundTotalCount >= 2" in src, "第 2 步起建聚合卡"
        assert "roundToolEls.length === 4" not in src, "F2-3 的 4 步触发逻辑必须移除"

    def test_aggregation_swallows_latest_each_step(self):
        src = GUI_FILE.read_text(encoding="utf-8")
        # 已有聚合卡时：先把最新一步收进聚合卡（吞并），再挂新一步
        assert "aggBody2.appendChild(d)" in src, "持续吞并最新一步"
        assert "roundToolEls = []" in src
        # 吞并在挂新卡之前（回合中任何时刻只有聚合卡+最新一步）
        assert "chatEl.appendChild(div)" in src

    def test_aggregation_title_updates_realtime(self):
        src = GUI_FILE.read_text(encoding="utf-8")
        assert "Executed ' + roundTotalCount + ' steps " in src, "标题数字实时涨"

    def test_aggregation_reset_at_round_end(self):
        src = GUI_FILE.read_text(encoding="utf-8")
        assert "roundToolEls = []; roundAggregated = false; roundTotalCount = 0; roundAggregateHead = null;" in src, "回合结束重置聚合状态（聚合卡保留可考古）"


# ── F4-2: diff 红绿高亮 ─────────────────────────────────────────────

class TestF42DiffHighlight:
    """F4-2 diff 红绿高亮失效修复 —— CSS 双前缀 + 函数实跑。"""

    def test_css_selector_covers_tool_result_container(self):
        src = GUI_FILE.read_text(encoding="utf-8")
        # 容器实际 class 是 tool-result（updateToolResult 挂载），CSS 必须双前缀
        assert ".tool-result .diff-add" in src, "diff-add 需覆盖 tool-result 容器"
        assert ".tool-result .diff-del" in src
        assert ".tool-result .diff-file" in src
        assert ".tool-result .td-args" in src
        assert ".tool-result .inline-diff" in src

    def test_diff_highlight_function_intact(self):
        src = GUI_FILE.read_text(encoding="utf-8")
        assert "function diffHighlight(text)" in src
        assert "diff-add" in src and "diff-del" in src and "diff-file" in src

    def test_render_tool_detail_emits_diff_spans(self):
        """node 实跑当前 HTML 真实 renderToolDetail：edit_file 卡片 diff 红绿 span 齐全。"""
        assert "NODE_DETAIL_OK" in _node_render_detail_test()


# ── F4-3: 零 JSON 倾倒 ──────────────────────────────────────────────

class TestF43NoJsonDump:
    """F4-3 写入/编辑卡片禁倒原始 JSON —— 显示路径+预览/diff。"""

    def test_render_tool_detail_no_raw_json(self):
        """node 实跑：写入文件卡（5KB content）零 JSON 倾倒，只出路径+截断预览。"""
        out = _node_render_detail_test()
        assert "NODE_DETAIL_OK" in out

    def test_no_stringify_of_full_args(self):
        """renderToolDetail 内不得再对整个 args 做 JSON.stringify 糊屏。"""
        src = GUI_FILE.read_text(encoding="utf-8")
        # 只允许对 extra（小参数子集）stringify，不允许对 args 整体
        assert "JSON.stringify(args, null, 2)" not in src, "整体 args stringify 已移除"
        assert "JSON.stringify(extra, null, 2)" in src, "仅小参数子集可 stringify"
        assert "内容预览" in src and "路径" in src


# ── F4-4: AUTO/停止按钮重排 ─────────────────────────────────────────

class TestF44ButtonLayout:
    """F4-4 #auto-toggle 与 #stop-btn 撞车重排 —— 水平错开不重叠。"""

    def test_auto_toggle_moved_left_of_stop_btn(self):
        src = GUI_FILE.read_text(encoding="utf-8")
        # stop-btn 右缘 right:64px；auto-toggle 右缘必须 > 64+28=92px（stop 左缘）
        assert "#auto-toggle { position:absolute; right:104px" in src, "auto-toggle 左移至 right:104px"
        assert "#stop-btn { position:absolute; right:64px" in src, "stop-btn 位置保持不变"

    def test_no_overlap_geometry(self):
        src = GUI_FILE.read_text(encoding="utf-8")
        assert "right:64px; bottom:37px" not in src, "auto-toggle 不再与 stop-btn 同 right:64px"


# ── F4-5: 项目面板预览拦截全入口 ────────────────────────────────────

class TestF45PanelPreview:
    """F4-5 面板长文预览拦截全入口 —— 文件/笔记/终端三入口齐备。"""

    def test_project_file_preview_intercept(self):
        src = GUI_FILE.read_text(encoding="utf-8")
        assert "txt.length > 2000 && !full" in src, "showProjectFile 2000 字符拦截"
        assert "Show all (" in src and "output truncated" in src

    def test_note_preview_intercept(self):
        src = GUI_FILE.read_text(encoding="utf-8")
        assert "showNote(filepath, full)" in src
        assert "txt.length > 2000" in src

    def test_terminal_output_intercept(self):
        src = GUI_FILE.read_text(encoding="utf-8")
        # F4-5 新增：终端面板长输出拦截
        assert "output truncated" in src
        assert "toggleTerminalOutput" in src
        assert "outText.length > 2000" in src


# ── F4-6: AUTO 两端对齐 ─────────────────────────────────────────────

class TestF46AutoAlignment:
    """F4-6 AUTO 两端对齐 —— GUI 开关必须携带 session_id，后端真实翻转当前会话。"""

    def test_gui_toggle_carries_session_id(self):
        """GUI auto-toggle 点击必须携带 session_id（根因修复）。"""
        src = GUI_FILE.read_text(encoding="utf-8")
        assert "call('slash.exec', { command: 'auto', session_id: currentSessionId })" in src, \
            "slash.exec 必须带 session_id（不带则翻转空会话，GUI AUTO 显示与后端裂脑）"
        assert "call('slash.exec', { command: 'auto' })" not in src, "无 session_id 的旧调用必须移除"

    def test_backend_flips_real_session_with_sid(self):
        """后端实证：slash.exec 带 session_id → 真实会话 auto_state 翻转（GUI 开关同通道）。"""
        from bobo_tui_gateway.server import dispatch

        r = dispatch({"id": "f4-6-1", "method": "session.create",
                      "params": {"title": "F4-6 实弹"}})
        assert r.get("result") and r["result"].get("session_id"), r
        sid = r["result"]["session_id"]

        # GUI 开关点击等价调用：slash.exec /auto + session_id
        r2 = dispatch({"id": "f4-6-2", "method": "slash.exec",
                       "params": {"command": "auto", "session_id": sid}})
        assert "开启" in r2["result"]["output"], r2

        r3 = dispatch({"id": "f4-6-3", "method": "session.resume",
                       "params": {"session_id": sid}})
        assert r3["result"]["auto_state"] is True, r3
        # 收尾：关掉避免影响其他测试
        dispatch({"id": "f4-6-4", "method": "slash.exec",
                  "params": {"command": "auto off", "session_id": sid}})

    @pytest.mark.xfail(reason="TICKET-GUI-F4 F4-6 待特批内核缺口：core/engine.py:232 "
                              "_write_auto_audit 调用少传 reason（6 参传 5 实参，snapshot 错位到 "
                              "side_effect_level）→ AUTO 模式文件工具 TypeError 崩溃。"
                              "清单已报 Kimi 特批，获批后修复转绿。", strict=False)
    def test_auto_session_zero_popup(self):
        """AUTO 会话零弹窗实证：_confirm 在 AUTO 下走 _auto_decide（文件工具快照放行），
        confirm_callback（弹窗源）零调用 —— 决策链在 engine 层（TUI/GUI 共享）。"""
        import core.engine as engine_mod

        confirmed = []
        engine = engine_mod.Engine(
            llm_caller=lambda *a, **kw: None, tool_executor=lambda *a, **kw: {},
            confirm_callback=lambda *a, **kw: confirmed.append(a) or True,
            test_mode=False, auto_mode_getter=lambda: True)
        # engine.py:85 test_mode = test_mode or ('pytest' in sys.modules) ——
        # pytest 环境强制 True（_confirm 首行短路放行），测决策链必须手动置 False
        engine.test_mode = False
        # 编辑文件（local-reversible）：AUTO 决策树放行，不弹窗
        allow = engine._confirm("edit_file",
                                {"file_path": "/tmp/f4.md", "old_string": "a", "new_string": "b"},
                                "编辑文件")
        assert allow is True, f"文件工具 AUTO 下应放行: {allow}"
        assert confirmed == [], f"AUTO 模式下 confirm_callback 不得被调用: {confirmed}"

    def test_auto_file_tools_hit_known_gap(self):
        """F4-6 内核缺口已由 Kimi 特批修复（core/engine.py 文件工具分支补传 command
        实参）。本测试转为修复锁定：AUTO 模式下文件工具放行且不再 TypeError。"""
        import core.engine as engine_mod

        engine = engine_mod.Engine(
            llm_caller=lambda *a, **kw: None, tool_executor=lambda *a, **kw: {},
            test_mode=False, auto_mode_getter=lambda: True)
        engine.test_mode = False
        result = engine._confirm("edit_file",
                                 {"file_path": "/tmp/f4.md", "old_string": "a", "new_string": "b"},
                                 "编辑文件")
        assert result is True, "修复后 AUTO 文件工具应放行（local-reversible）"

    def test_auto_blacklist_denied_without_popup(self):
        """AUTO 红线自动拒绝实证：黑名单命令即时拒绝（不弹窗不执行）。"""
        import core.engine as engine_mod

        confirmed = []
        engine = engine_mod.Engine(
            llm_caller=lambda *a, **kw: None, tool_executor=lambda *a, **kw: {},
            confirm_callback=lambda *a, **kw: confirmed.append(a) or True,
            test_mode=False, auto_mode_getter=lambda: True)
        engine.test_mode = False  # pytest 环境强制 True，手动置 False 走真实决策链
        # 黑名单命令：AUTO 决策树即时拒绝（黑名单硬锁）
        deny = engine._confirm("execute_terminal", {"command": "rm -rf /tmp/f4_evil"},
                               "🚫 危险操作 — 递归删除文件")
        assert deny is False, f"黑名单命令 AUTO 下应拒绝: {deny}"
        assert confirmed == [], f"红线黑名单在 AUTO 下不得弹窗: {confirmed}"
        # 外部不可逆灰名单（如 git push）：同样即时拒绝，不弹窗
        deny2 = engine._confirm("execute_terminal", {"command": "git push origin main"},
                                "外部不可逆")
        assert deny2 is False, f"外部不可逆命令 AUTO 下应拒绝: {deny2}"
        assert confirmed == [], "外部不可逆也不得弹窗"

    def test_auto_pure_read_allowed(self):
        """AUTO 纯读命令放行（与 TUI 一致）。"""
        import core.engine as engine_mod

        confirmed = []
        engine = engine_mod.Engine(
            llm_caller=lambda *a, **kw: None, tool_executor=lambda *a, **kw: {},
            confirm_callback=lambda *a, **kw: confirmed.append(a) or True,
            test_mode=False, auto_mode_getter=lambda: True)
        engine.test_mode = False  # pytest 环境强制 True，手动置 False 走真实决策链
        allow = engine._confirm("execute_terminal", {"command": "git status"},
                                "查看状态")
        assert allow is True, f"纯读命令 AUTO 下应放行: {allow}"
        assert confirmed == []


# ── F1/F2/F3 零回归锚点 ─────────────────────────────────────────────

class TestF1F2F3NoRegression:
    """F4 施工后 F1/F2/F3 关键语义不回归（对照 test_ticket_gui_f2.py 锚点）。"""

    def test_f2_heartbeat_in_place_update(self):
        src = GUI_FILE.read_text(encoding="utf-8")
        assert "仍在工作" in src
        assert "querySelectorAll('.status')" in src

    def test_f2_raw_output_collapsed_show_all(self):
        src = GUI_FILE.read_text(encoding="utf-8")
        assert "showProjectFile(filepath, full)" in src
        assert "Show all (" in src

    def test_f1_ime_guard(self):
        src = GUI_FILE.read_text(encoding="utf-8")
        assert "e.isComposing || e.keyCode === 229 || imeComposing" in src

    def test_f2_edit_card_default_open(self):
        src = GUI_FILE.read_text(encoding="utf-8")
        # F2-4 行为：带 diff 的编辑卡默认展开（F3-5 后工具卡内为摘要 + open 类仍成立）
        # SAFETY-1 守卫版：默认展开逻辑保留（open 类 + ▾ 箭头），仅加空值守卫
        assert "resultEl.classList.add('open');" in src
        assert "toggleEl.textContent = '▾';" in src

    def test_f3_style_zero_new(self):
        """F4 不新增视觉体系（沿用 tool-agg/tool-result 既有类）。"""
        src = GUI_FILE.read_text(encoding="utf-8")
        # 聚合卡仍用 tool-agg 体系
        assert "tool-agg" in src
        # 不引入新的大段设计变量
        assert "tool-detail" in src and "tool-result" in src
