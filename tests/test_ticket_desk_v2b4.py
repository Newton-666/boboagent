"""TICKET-DESK-V2B4 回归测试 — 上下文药丸修复包。

覆盖：
- V2B4-1 kimi-k3 上下文窗口补登 1M（只加不改，k2.6 / k2.7-code-highspeed 既有条目不变）
- V2B4-2 context.stats 活引擎优先（双兜底）：活引擎有消息 → token_estimate>0；
  活引擎 None/空 → 回退 gateway messages（V2B 既有行为不破）；两路都空 → 0 不炸
- V2B4-3 药丸刷新时机：tool.complete 后轻量刷新（只读估算，无轮询）
- V2B4-4 工作实况折叠卡：buildWorktreeCard 检测 ── 工作区实况 / ── 实况对账 /
  工作区实况（收工对账 三个特征；抽离 → %%WORKTREE_CARD%% → md 还原；
  node 实跑渲染出折叠卡且默认收起（display:none）、等宽内容原样、展开切换逻辑
- CSS 锚点段 /* === V2B4 实况折叠卡 === */ 存在且取色只用色板（无新 #hex）
- 铁律 1 闸：TUI 零变化（ui-tui git diff 空）
- md5 闸门：真实库三文件零变动

注：GUI 渲染层采用静态断言 + node 实跑（与 V2B/V2B3 同款零漂移验证）。
"""

import hashlib
import re
import subprocess
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
GUI_FILE = ROOT / "apps" / "desktop" / "dist" / "index.html"
MISC_PY = ROOT / "bobo_tui_gateway" / "handlers" / "misc.py"
PROVIDER_PY = ROOT / "core" / "provider.py"
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


def _gui() -> str:
    return GUI_FILE.read_text(encoding="utf-8")


def _make_ctx():
    """构造最小 ctx 桩（与 V2B/V2B3 同款）。"""
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


# ── V2B4-1：kimi-k3 上下文窗口补登 1M ──────────────────────────────────

def test_v2b4_1_kimi_k3_context_limit():
    """kimi-k3 经 get_context_length / context.stats 返回 1M；既有 kimi 条目不变。"""
    from core.provider import get_context_length, PROVIDERS
    mc = PROVIDERS["moonshot"]["model_context"]
    assert mc["kimi-k3"] == 1000000, f"kimi-k3 必须补登 1M: {mc}"
    assert mc["kimi-k2.6"] == 262144 and mc["kimi-k2.7-code-highspeed"] == 262144, \
        f"既有 kimi 条目只加不改: {mc}"
    assert get_context_length("moonshot", "kimi-k3") == 1000000
    assert get_context_length("moonshot", "kimi-k2.6") == 262144
    # 后端 context.stats 链路同值（handle_context_stats 经 get_context_length）
    from bobo_tui_gateway.handlers import misc as misc_mod
    ctx = _make_ctx()
    ctx.sessions["v2b4_s_001"] = {"id": "v2b4_s_001", "messages": []}
    r = misc_mod.handle_context_stats({"session_id": "v2b4_s_001"}, "r1", ctx)
    assert r["result"]["context_limit"] == get_context_length(), \
        f"context_limit 应透传 get_context_length: {r['result']['context_limit']}"


# ── V2B4-2：context.stats 活引擎优先（双兜底）──────────────────────────

def test_v2b4_2_context_stats_live_priority(monkeypatch):
    """活引擎有消息 → 用活引擎（gateway 空也 >0）；活引擎 None → 回退 gateway；两空 → 0 不炸。"""
    import core.engine_adapter as ea_mod
    from bobo_tui_gateway.handlers import misc as misc_mod
    from tools import load_result as lr_mod
    monkeypatch.setattr(lr_mod, "get_marking_stats", lambda: {"marked": 0, "loaded": 0, "total_chars_saved": 0})

    live_msgs = [
        {"role": "user", "content": "活引擎里的用户消息：请读取并分析这份报告" * 2},
        {"role": "assistant", "content": "正在读取……（活引擎进行中）" * 3},
    ]
    gw_msgs = [{"role": "user", "content": "gateway 里的旧消息（回合末才写回）"}]

    # 场景 A：活引擎有消息，gateway 那份为空（F9 后根因场景）→ 必须 >0
    monkeypatch.setattr(ea_mod, "get_live_history", lambda sid: list(live_msgs))
    ctx = _make_ctx()
    ctx.sessions["v2b4_s_001"] = {"id": "v2b4_s_001", "messages": []}
    r = misc_mod.handle_context_stats({"session_id": "v2b4_s_001"}, "rA", ctx)
    assert r["result"]["token_estimate"] > 0, f"活引擎有消息应估算出正 token: {r}"

    # 场景 B：活引擎取不到（竞态/引擎已退出）→ 双兜底回退 gateway messages
    monkeypatch.setattr(ea_mod, "get_live_history", lambda sid: None)
    ctx2 = _make_ctx()
    ctx2.sessions["v2b4_s_001"] = {"id": "v2b4_s_001", "messages": gw_msgs}
    rB = misc_mod.handle_context_stats({"session_id": "v2b4_s_001"}, "rB", ctx2)
    assert rB["result"]["token_estimate"] > 0, f"活引擎 None 应回退 gateway: {rB}"

    # 场景 C：活引擎与 gateway 都空 → 0 不炸
    monkeypatch.setattr(ea_mod, "get_live_history", lambda sid: None)
    ctx3 = _make_ctx()
    ctx3.sessions["v2b4_s_001"] = {"id": "v2b4_s_001", "messages": []}
    rC = misc_mod.handle_context_stats({"session_id": "v2b4_s_001"}, "rC", ctx3)
    assert rC["result"]["token_estimate"] == 0, f"两路皆空应为 0: {rC}"

    # 场景 D：活引擎抛异常 → 也不炸，回退 gateway
    def _boom(sid):
        raise RuntimeError("engine gone")
    monkeypatch.setattr(ea_mod, "get_live_history", _boom)
    ctx4 = _make_ctx()
    ctx4.sessions["v2b4_s_001"] = {"id": "v2b4_s_001", "messages": gw_msgs}
    rD = misc_mod.handle_context_stats({"session_id": "v2b4_s_001"}, "rD", ctx4)
    assert rD["result"]["token_estimate"] > 0, f"活引擎抛异常应回退 gateway: {rD}"


# ── V2B4-3：药丸刷新时机（tool.complete 后轻量刷新）────────────────────

def test_v2b4_3_tool_complete_refresh_static():
    src = _gui()
    tc = src[src.index("on('tool.complete'"):src.index("on('session.auto_state'")]
    assert "refreshCtxStats()" in tc, "tool.complete 处理器内必须轻量刷新药丸"
    assert "setInterval" not in tc and "setTimeout" not in tc, "不得引入轮询/延迟刷新"
    # 既有两个刷新时机保留（ready / 回合结束）
    assert src.count("refreshCtxStats()") >= 4, "ready + 回合结束 + tool.complete + 展开拉新 均应保留"


# ── V2B4-4：工作实况折叠卡（静态 + node 实跑）──────────────────────────

def test_v2b4_4_worktree_card_static():
    src = _gui()
    # buildWorktreeCard 存在且含三个检测特征
    bw = _extract_func(src, "buildWorktreeCard")
    for marker in ["── 工作区实况", "── 实况对账", "工作区实况（收工对账"]:
        assert marker in bw, f"检测特征缺失: {marker}"
    assert "next 同级分隔" not in bw  # 无意义占位，防笔误
    assert "/^─{2,}/.test(lines[j])" in bw, "区块结束应以下一个 ── 分隔线为界"
    assert "v2b4-wt-card" in bw and "v2b4-wt-body" in bw
    # 默认收起：pre 必须内联 display:none（否则首击无效——style.display='' 被误判展开）
    assert 'style="display:none"' in bw, "折叠卡体必须默认收起（内联 display:none）"
    # toggleWorktree：切换 display + 箭头
    tw = _extract_func(src, "toggleWorktree")
    assert "body.style.display" in tw and "arrow.textContent" in tw
    # md() 内抽离 + 还原（历史重放与流式同路径）
    md_fn = _extract_func(src, "md")
    assert "var worktreeCard = buildWorktreeCard(s);" in md_fn, "md 内必须抽离实况区块"
    assert "%%WORKTREE_CARD%%" in md_fn
    assert "if (worktreeCard) { s = s.replace(/%%WORKTREE_CARD%%/g, worktreeCard.card); }" in md_fn, \
        "md 尾部必须还原折叠卡"
    # CSS 锚点段：存在、含全部取色 token、无新 #hex
    css_start = src.index("/* === V2B4 实况折叠卡 ===")
    css_end = src.index("/* === end V2B4 ===")
    css = src[css_start:css_end]
    assert "var(--bg2)" in css and "var(--bg3)" in css and "var(--border)" in css, \
        "折叠卡必须用色板 token"
    assert "var(--hover)" in css and "var(--text-muted)" in css
    hex_colors = re.findall(r"#[0-9a-fA-F]{3,8}\b", css)
    allowed = {"#e8913a"}  # 品牌橙（GUI-DESIGN 色板语义色）
    assert set(hex_colors) <= allowed, f"V2B4 样式块不得新增色板外色值: {hex_colors}"


def test_v2b4_5_worktree_card_node():
    src = _gui()
    bw = _extract_func(src, "buildWorktreeCard")
    esc = _extract_func(src, "esc")
    js = r"""
let results = [];
""" + esc + bw + r"""
// 场景 1：完整收工实况区块（标记 → 消息结尾）→ 折叠卡、默认收起、等宽内容原样
let t1 = '收到，施工完毕。\n\n── 工作区实况（收工对账，只读）──\ngit status --short: 3 项变更\n M apps/desktop/dist/index.html\n?? data/tickets/TICKET-1.md\n台账与汇报必须与以上实况一致。';
let c1 = buildWorktreeCard(t1);
if (!c1) throw new Error('场景1 应命中实况区块');
if (c1.head.indexOf('收到，施工完毕。') < 0) throw new Error('头部正文应保留: ' + c1.head);
if (c1.card.indexOf('v2b4-wt-card') < 0) throw new Error('应渲染折叠卡');
if (c1.card.indexOf('style="display:none"') < 0) throw new Error('默认收起: ' + c1.card.slice(0,80));
if (c1.card.indexOf('git status --short: 3 项变更') < 0) throw new Error('等宽内容原样: ' + c1.card);
results.push('T1_OK');
// 场景 2：── 实况对账 独立特征
let t2 = 'a\n── 实况对账 ──\nx=1\ny=2';
let c2 = buildWorktreeCard(t2);
if (!c2 || c2.card.indexOf('x=1') < 0) throw new Error('场景2 应命中');
results.push('T2_OK');
// 场景 3：工作区实况（收工对账 特征（无 ── 前缀）
let t3 = '正文\n工作区实况（收工对账，只读）──\nabc';
let c3 = buildWorktreeCard(t3);
if (!c3) throw new Error('场景3 应命中');
results.push('T3_OK');
// 场景 4：无特征 → null（普通消息零变化）
let t4 = '普通回复，无实况区块';
if (buildWorktreeCard(t4) !== null) throw new Error('场景4 应返回 null');
results.push('T4_OK');
// 场景 5：区块后还有下一个 ── 分隔线 → 截断到分隔线前
let t5 = 'h\n── 工作区实况 ──\nA: 1\n── 明细 ──\nB: 2';
let c5 = buildWorktreeCard(t5);
if (!c5) throw new Error('场景5 应命中');
if (c5.card.indexOf('A: 1') < 0) throw new Error('区块内容应保留: ' + c5.card);
if (c5.card.indexOf('B: 2') >= 0) throw new Error('不应吞掉下一分隔内容: ' + c5.card);
if (c5.head.indexOf('── 明细 ──') < 0) throw new Error('下一分隔应回到 head: ' + c5.head);
results.push('T5_OK');
console.log(results.join('|'));
"""
    out = _run_node(js)
    for tag in ["T1_OK", "T2_OK", "T3_OK", "T4_OK", "T5_OK"]:
        assert tag in out, f"node 实跑缺 {tag}: {out}"


# ── 铁律 1 闸：TUI 零变化 ───────────────────────────────────────────────

def test_v2b4_tui_zero_change():
    r = subprocess.run(
        ["git", "diff", "--stat", "--", "ui-tui/"],
        cwd=ROOT, capture_output=True, text=True, timeout=30,
    )
    assert r.stdout.strip() == "", f"TUI 必须零变化: {r.stdout}"


# ── md5 闸门：真实库三文件零变动 ────────────────────────────────────────

def test_v2b4_md5_gate():
    """真实库三文件存在且在 git 中零变更（md5 闸门 —— 三文件均为 gitignore 真实库）。"""
    for f in MD5_FILES:
        assert f.exists(), f"真实库文件缺失: {f}"
    r = subprocess.run(
        ["git", "status", "--short", "--",
         "data/knowledge_base.json", "library/MEMORY.md", "library/index.md"],
        cwd=ROOT, capture_output=True, text=True, timeout=30,
    )
    assert r.stdout.strip() == "", f"真实库三文件必须零变更: {r.stdout}"
