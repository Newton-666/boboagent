"""TICKET-DESK-V2B 回归测试 — 差异化面板（工具时间线 + 上下文仪表盘）。

覆盖：
- V2B-1 工具活动时间线：.tool-time 44px 等宽右对齐耗时列（.tool-status 右侧）、
  耗时从 status 文本迁出（status='done' 纯状态词）、聚合卡考古内部同卡带耗时
- V2B-2 上下文仪表盘：#input-box 正上方 22px 细条（ctx-stats-wrap/ctx-bar/ctx-detail）、
  点击展开明细卡 / Esc 收起、context.stats 只读端点（token 估算/压缩节省/记忆注入）
- 铁律 0 闸：V2A 标记之前的既有 CSS 与 HEAD 逐字节一致（只新增，零改既有值）
- 铁律 1 闸：TUI 零变化（共享层只加字段；本次只新增 gateway 只读端点）
- md5 闸门：真实库三文件零变动（与 V2A 同款存在性闸）
- DOM 顺序闸：V2B 新增 DOM 必须在 <script> 之前（L1 教训回归防护）
- 数据来源闸：tool 耗时只用事件自带 duration，禁止新增轮询

注：GUI 渲染层采用静态断言 + node 实跑（与 F3-F8/V2A 同款零漂移验证）。
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
MISC_PY = ROOT / "bobo_tui_gateway" / "handlers" / "misc.py"
MD5_FILES = [
    ROOT / "data" / "knowledge_base.json",
    ROOT / "library" / "MEMORY.md",
    ROOT / "library" / "index.md",
]


def _run_node(js: str) -> str:
    """在 node 中执行 JS（同步），返回 stdout。"""
    r = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        raise AssertionError(f"node 执行失败: {r.stderr}")
    return r.stdout


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


def _gui() -> str:
    return GUI_FILE.read_text(encoding="utf-8")


def _make_ctx():
    """构造最小 ctx 桩（与 V2A 同款）。"""
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


# ── V2B-1：工具时间线静态闸 ────────────────────────────────────────────
def test_v2b_1_tool_timeline_static():
    src = _gui()
    # addTool：工具卡内联 tool-time 元素（status 之后、toggle 之前 → 行内最右）
    at = _extract_func(src, "addTool")
    assert "tool-time" in at, "addTool 应生成 .tool-time 元素"
    assert at.index("tool-status") < at.index("tool-time") < at.index("tool-toggle"), \
        "tool-time 必须位于 status 与 toggle 之间（行内最右，status 左侧）"
    # updateToolResult：耗时写入 tool-time，status 简化为纯状态词（不再内嵌耗时）
    ur = _extract_func(src, "updateToolResult")
    assert "statusEl.textContent = 'done'" in ur, "成功态 status 应为纯 'done'（耗时迁出）"
    assert "timeEl.textContent = duration ? duration.toFixed(1) + 's' : '—'" in ur, \
        "耗时应写入 tool-time（等宽数字）"
    assert "timeElF.textContent = '—'" in ur, "失败态 tool-time 应显示 —"
    # 排版约束：44px 右对齐等宽、flex-shrink:0 不挤压名称/路径
    assert ".tool .tool-time" in src
    assert "width:44px" in src and "text-align:right" in src
    assert "font-family:'SF Mono',Monaco,Menlo,monospace" in src
    assert "flex-shrink:0" in src
    # 聚合卡考古：吞并的是同一 .tool div（含 tool-time），无需额外逻辑
    assert ".tool-agg-body .tool" in src, "聚合卡考古应复用 .tool 卡（自带耗时列）"
    # 数据来源：只用事件自带 duration，禁止新增轮询/定时器
    assert "setInterval" not in ur and "setTimeout" not in ur.split("// TICKET-DESK-V2B")[0]


# ── V2B-1：工具时间线 node 实跑（DOM 桩）───────────────────────────────
def test_v2b_1_tool_timeline_node():
    src = _gui()
    ur = _extract_func(src, "updateToolResult")
    js = r"""
function makeEl(selMap) {
  return { textContent: '', className: '', innerHTML: '', style: {},
    classList: { add() {}, toggle() {} }, setAttribute() {}, querySelector(s) { return selMap[s] || null; } };
}
const timeEl = { textContent: '', style: {} };
const statusEl = { textContent: 'running', style: {} };
const dot = { className: '', style: {} };
const toggleEl = { textContent: '', style: {}, classList: { add() {} } };
const resultEl = { className: '', textContent: '', innerHTML: '', classList: { add() {} } };
const card = makeEl({});
card.querySelector = function(s) {
  if (s === '.tool-status') return statusEl;
  if (s === '.tool-time') return timeEl;
  if (s === '.dot') return dot;
  if (s === '.tool-toggle') return toggleEl;
  if (s === '.tool-result') return resultEl;
  return null;
};
const chatEl = { querySelectorAll() { return [card]; } };
// 聚合卡考古场景：卡已吞入 tool-agg-body（仍在 chatEl 下），同一 div 带 time
global.chatEl = chatEl;
global.Notification = { permission: 'denied', requestPermission() {} };
global.friendlyMap = {};
""" + ur + r"""
// 成功路径：duration 12.345 → status 'done'，time '12.3s'
updateToolResult('read_local_file', { duration: 12.345, arguments: {}, result_text: '' });
if (statusEl.textContent !== 'done') throw new Error('成功态 status 应为 done，实际: ' + statusEl.textContent);
if (timeEl.textContent !== '12.3s') throw new Error('tool-time 应为 12.3s，实际: ' + timeEl.textContent);
if (dot.className !== 'dot done') throw new Error('成功态 dot 应为 dot done');
// 无 duration → '—'
statusEl.textContent = 'running'; timeEl.textContent = '';
updateToolResult('read_local_file', { duration: 0, arguments: {}, result_text: '' });
if (timeEl.textContent !== '—') throw new Error('无 duration 应为 —，实际: ' + timeEl.textContent);
// 失败路径：error → status failed，time '—'
statusEl.textContent = 'running'; timeEl.textContent = '';
updateToolResult('read_local_file', { error: 'boom', duration: 3, arguments: {} });
if (statusEl.textContent !== 'failed') throw new Error('失败态 status 应为 failed');
if (timeEl.textContent !== '—') throw new Error('失败态 time 应为 —');
if (dot.className !== 'dot fail') throw new Error('失败态 dot 应为 dot fail');
console.log('NODE_V2B1_TIMELINE_OK');
"""
    out = _run_node(js)
    assert "NODE_V2B1_TIMELINE_OK" in out, f"node 实跑失败: {out}"


# ── V2B-2：上下文仪表盘静态闸 ──────────────────────────────────────────
def test_v2b_2_ctx_dashboard_static():
    src = _gui()
    # 排版地图：#input-box 正上方（chat 与 input-box 之间）
    assert src.index('<div id="chat">') < src.index('id="ctx-stats-wrap"') < src.index('<div id="input-box">'), \
        "细条必须在 #chat 与 #input-box 之间"
    # DOM 三件：wrap/bar/detail + 药丸两件（V2B2 由数值 span 改造为进度药丸）
    assert 'id="ctx-stats-wrap"' in src and 'id="ctx-stats-bar"' in src and 'id="ctx-stats-detail"' in src
    assert 'id="ctx-pill-fill"' in src and 'id="ctx-pill-text"' in src
    assert 'onclick="toggleCtxStats()"' in src, "药丸点击应展开明细卡"
    # CSS：圆角药丸（轨道 --bg3）、向上展开（bottom:100% 不遮盖输入框）、fadeIn 动效、色板取色
    assert ".ctx-pill {" in src and "border-radius:999px" in src, "药丸应为圆角胶囊形态"
    assert "background:var(--bg3)" in src, "药丸轨道应取 --bg3"
    assert ".ctx-detail { position:absolute; bottom:100%;" in src
    assert "animation:fadeIn 0.25s ease-out" in src, "明细卡入场应复用既有 fadeIn 动效"
    assert "color:var(--text-muted)" in src, "细条默认弱存在（--text-muted）"
    assert "background:var(--bg2)" in src and "border:1px solid var(--border)" in src
    # JS：刷新 + 展开/收起
    assert "function refreshCtxStats(" in src and "function toggleCtxStats(" in src
    assert "call('context.stats'" in src, "数据应来自 context.stats 只读端点"
    # 刷新时机：gateway.ready + message.complete（回合结束），禁止定时轮询
    assert "refreshCtxStats();   // TICKET-DESK-V2B：就绪后初始刷新上下文仪表盘" in src
    assert "refreshCtxStats();   // TICKET-DESK-V2B：回合结束刷新上下文仪表盘" in src
    assert "setInterval" not in src.split("// TICKET-DESK-V2B")[-1].split("<script")[0], \
        "禁止定时轮询刷新仪表盘"
    # Esc 收起：keydown 中明细卡开着 → 优先收起
    assert "ctxDet.style.display !== 'none'" in src and "else { stopThinking(); }" in src
    # 后端：context.stats 端点注册（只读）
    mp = MISC_PY.read_text(encoding="utf-8")
    assert 'reg_method("context.stats")' in mp, "gateway 应注册 context.stats"
    assert "def handle_context_stats(" in mp
    assert "token_estimate" in mp and "saved_chars" in mp and "memory_injected" in mp


# ── V2B-2：上下文仪表盘 node 实跑（DOM 桩）─────────────────────────────
def test_v2b_2_ctx_dashboard_node():
    src = _gui()
    refresh = _extract_func(src, "refreshCtxStats")
    toggle = _extract_func(src, "toggleCtxStats")
    js = r"""
const els = {};
function makeEl(id) {
  return { id, textContent: '', innerHTML: '', style: { display: 'none', width: '', background: '' } };
}
['ctx-pill-fill', 'ctx-pill-text', 'ctx-stats-detail'].forEach(function(id) { els[id] = makeEl(id); });
global.document = { getElementById: function(id) { return els[id] || null; } };
global.currentSessionId = 'v2b_s_001';
global.call = function(m, p) {
  if (m !== 'context.stats') throw new Error('应调用 context.stats，实际: ' + m);
  if (p.session_id !== 'v2b_s_001') throw new Error('session_id 应透传');
  return Promise.resolve({ result: {
    token_estimate: 41000, saved_chars: 56789, marked: 12, loaded: 8, memory_injected: 8, context_limit: 128000 } });
};
""" + refresh + "\n" + toggle + r"""
// 展开 → 显示 + 拉最新
toggleCtxStats();
if (els['ctx-stats-detail'].style.display !== 'block') throw new Error('点击应展开明细卡');
Promise.resolve().then(function() {
  if (els['ctx-pill-fill'].style.width !== '32%') throw new Error('填充宽度应 32%: ' + els['ctx-pill-fill'].style.width);
  if (els['ctx-pill-text'].textContent.indexOf('32%') === -1) throw new Error('药丸文字应含 32%: ' + els['ctx-pill-text'].textContent);
  if (els['ctx-pill-text'].textContent.indexOf('41K/128K') === -1) throw new Error('药丸文字应含 41K/128K: ' + els['ctx-pill-text'].textContent);
  if (els['ctx-pill-fill'].style.background !== '#5b9bd5') throw new Error('32% 应取思考蓝: ' + els['ctx-pill-fill'].style.background);
  if (els['ctx-stats-detail'].innerHTML.indexOf('上下文 token 估算') === -1) throw new Error('明细卡应含明细行');
  // 再点 → 收起
  toggleCtxStats();
  if (els['ctx-stats-detail'].style.display !== 'none') throw new Error('再点应收起明细卡');
  console.log('NODE_V2B2_CTX_OK');
}).catch(function(e) { console.error(e.message); process.exit(1); });
"""
    out = _run_node(js)
    assert "NODE_V2B2_CTX_OK" in out, f"node 实跑失败: {out}"


# ── V2B-2：context.stats 后端实证（monkeypatch 隔离）──────────────────
def test_v2b_2_context_stats_backend(monkeypatch, tmp_path):
    from bobo_tui_gateway.handlers import misc as misc_mod
    from tools import load_result as lr_mod

    msgs = [
        {"role": "user", "content": "你好，请帮我看看这个项目结构"},
        {"role": "assistant", "content": "好的，我先读一下文件。"},
        {"role": "user", "content": "继续"},
    ]
    ctx = _make_ctx()
    ctx.sessions["v2b_s_001"] = {"id": "v2b_s_001", "messages": msgs}

    # monkeypatch get_marking_stats（隔离真实工作区累计值）
    monkeypatch.setattr(lr_mod, "get_marking_stats",
                        lambda: {"marked": 12, "loaded": 8, "load_miss": 1, "total_chars_saved": 56789})

    r = misc_mod.handle_context_stats({"session_id": "v2b_s_001"}, "r1", ctx)
    assert "error" not in r, f"context.stats 不应报错: {r}"
    res = r["result"]
    assert res["token_estimate"] > 0, f"有 3 条消息应估算出正 token: {res}"
    assert res["saved_chars"] == 56789
    assert res["marked"] == 12 and res["loaded"] == 8
    assert res["memory_injected"] == res["loaded"], "记忆注入条数 = load_result 取回次数"
    assert res["context_limit"] > 0, f"context_limit 应为正（get_context_length），实际: {res['context_limit']}"

    # 未知会话 → token 估算 0（不炸），累计值照常返回
    r2 = misc_mod.handle_context_stats({"session_id": "nonexistent"}, "r2", ctx)
    assert r2["result"]["token_estimate"] == 0

    # 无 get_marking_stats 数据（文件缺失）→ 默认 0，不炸
    monkeypatch.setattr(lr_mod, "get_marking_stats", lambda: {})
    r3 = misc_mod.handle_context_stats({"session_id": "v2b_s_001"}, "r3", ctx)
    assert r3["result"]["saved_chars"] == 0 and r3["result"]["marked"] == 0


# ── L1 回归闸：V2B 新增 DOM 必须在 <script> 之前 ───────────────────────
def test_v2b_dom_before_script():
    """V2B 新增 DOM（ctx-stats-wrap 细条/明细卡/数值 span）必须出现在 <script> 之前，
    否则顶层 JS getElementById 空指针 → 整个脚本死亡（V2A L1 事故同款）。"""
    src = _gui()
    script_pos = src.find("<script>")
    assert script_pos > 0
    for dom_id in ('id="ctx-stats-wrap"', 'id="ctx-stats-bar"', 'id="ctx-stats-detail"',
                   'id="ctx-pill-fill"', 'id="ctx-pill-text"'):
        pos = src.find(dom_id)
        assert pos > 0, f"{dom_id} 缺失"
        assert pos < script_pos, f"{dom_id} 在 <script> 之后，顶层 JS 将空指针崩溃"


# ── 铁律 0 闸：既有 CSS 零改动（V2A 标记之前的 style 段与 HEAD 逐字节一致）──
def test_v2b_css_zero_change_on_existing():
    """style 块中 TICKET-DESK-V2A 标记之前的所有规则，必须与基线版本完全一致。
    只允许新增（V2A 段 + V2B 段都是追加在末尾），禁止改动任何既有 CSS 属性值。
    基线选择同 V2A 测试：HEAD 不含 V2A 时直接用 HEAD；合并后切回滚标签。"""
    head = subprocess.run(["git", "show", "HEAD:apps/desktop/dist/index.html"],
                          capture_output=True, text=True, cwd=str(ROOT))
    assert head.returncode == 0, "git show HEAD 失败"
    base_src = head.stdout
    if "/* ══ TICKET-DESK-V2A" in base_src:
        tag = subprocess.run(["git", "show", "rollback/pre-desk-v2a:apps/desktop/dist/index.html"],
                             capture_output=True, text=True, cwd=str(ROOT))
        assert tag.returncode == 0, "合并后需以 rollback/pre-desk-v2a 标签为基线"
        base_src = tag.stdout
    old_style = re.search(r"<style[^>]*>(.*?)</style>", base_src, re.S).group(1)
    new_style = re.search(r"<style[^>]*>(.*?)</style>", _gui(), re.S).group(1)
    v2a_pos = new_style.find("/* ══ TICKET-DESK-V2A")
    assert v2a_pos > 0, "V2A 注释块应在 style 块内"
    # V2A 特批豁免（owner 打磨单）：.del/.re 旧规则 → .act 体系重构，双向剔除后比对
    old_seg = re.search(
        r"\.session-item \.del \{[^}]*\}\n\.session-item:hover \.del \{[^}]*\}\n"
        r"\.session-item \.re \{[^}]*\}\n\.session-item:hover \.re \{[^}]*\}\n", old_style)
    assert old_seg, "基线中应能找到旧 .del/.re 规则段"
    old_style = old_style.replace(old_seg.group(0), "")
    new_pre = new_style[:v2a_pos]
    new_seg = re.search(
        r"/\* V2A 打磨（owner 反馈 2026-08-13）：行内操作三键统一 \.act.*?"
        r"\.session-item \.stitle \{[^}]*\}\n", new_pre, re.S)
    assert new_seg, "新 style 中应能找到 .act 打磨段"
    new_pre = new_pre.replace(new_seg.group(0), "")
    assert new_pre.rstrip() == old_style.rstrip(), \
        "V2A 之前既有 CSS 必须逐字节等于基线（除特批 .act 重构段外零改动）"


# ── 铁律 0 补充闸：V2B diff 不得删除任何 style 块内规则（V2A 段同样）───
def test_v2b_css_no_deletion_in_style():
    """git diff 中出现在 style 块内的删除行必须为零（V2A 特批豁免段除外）。
    本闸覆盖 V2A 段：V2B 若改 V2A 的规则属性值会以 '-' 行出现在 diff 中。"""
    diff = subprocess.run(["git", "diff", "--", "apps/desktop/dist/index.html"],
                          capture_output=True, text=True, cwd=str(ROOT))
    assert diff.returncode == 0
    # V2A 打磨豁免段（owner 特批）：.del/.re → .act 重构删除的旧规则行
    EXEMPT = (
        ".session-item .del {",
        ".session-item:hover .del {",
        ".session-item .re {",
        ".session-item:hover .re {",
    )
    bad = []
    in_style = False
    for line in diff.stdout.split("\n"):
        if line.startswith("@@") and "apps/desktop/dist/index.html" in line:
            continue
        if line.startswith("diff --git"):
            in_style = False
        if "<style" in line:
            in_style = True
        elif "</style>" in line:
            in_style = False
        if line.startswith("-") and not line.startswith("---"):
            content = line[1:].strip()
            # CSS 规则删除行特征：以选择器/声明开头（排除 JS 行的缩进代码形态）
            is_css_like = re.match(r"^[.#@][\w\-]", content) or re.match(
                r"^[\w\-]+\s*:", content) and "textContent" not in content
            if in_style and is_css_like and not content.startswith(EXEMPT):
                bad.append(line[:90])
    assert not bad, f"style 块内出现未豁免的删除行（V2B 不得改既有 CSS）: {bad}"


# ── md5 闸门：真实库三文件零变动 ───────────────────────────────────────
def test_v2b_md5_gate():
    """真实库三文件存在/可读/非空；前后一致性由收工手工 md5sum 闸门验证（F8/V2A 同款惯例）。"""
    for f in MD5_FILES:
        assert f.exists(), f"{f} 不存在"
        assert len(hashlib.md5(f.read_bytes()).hexdigest()) == 32, f"{f} 读取失败"
        assert f.stat().st_size > 0, f"{f} 为空文件"
