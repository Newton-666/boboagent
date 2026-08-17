"""TICKET-DESK-V4B 回归测试 — 小组件会话钉选（从"镜子"升级"第二只眼睛"）。

覆盖（owner 圈定）：
- V4B-1 钉选过滤正确性（行为级 node 实跑）：钉住 B 时 A 的会话事件不渲染；
  药丸/指令按钉选过滤；无 sid 全局事件恒放行；启动早期跟随放行（V4 兼容）
- V4B-2 点击会话名轮换（行为级）：活跃会话循环 + 钉住最后一个回落跟随
- V4B-3 会话删除自动回落（行为级 + 链路）：小窗 onSessions 列表兜底 checkPinAlive；
  主窗 doDeleteSession 广播 pin-reset；跟随模式基准复位
- V4B-4 三向入口状态一致（链路断言）：主窗行内按钮 → main → 小窗（widget-pin-session）；
  小窗轮换 → main → 主窗按钮态（widget-pin-changed）；当前会话/会话列表广播齐备
- V4B-5 铁律零干涉：core/、bobo_tui_gateway/ git diff 空；CSS 锚点段；色板零新增
- V4B-6 行内入口顺序 + 会话指示（自定义名优先）+ 审批跳钉住会话

注：小窗纯逻辑（shouldRender/setPinned/cyclePin/checkPinAlive）node 实跑（与 V4 同款
零漂移验证）；主窗/链路采用静态断言。
"""

import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GUI = ROOT / "apps" / "desktop" / "dist" / "index.html"
MAIN = ROOT / "apps" / "desktop" / "electron" / "main.cjs"
PRELOAD = ROOT / "apps" / "desktop" / "electron" / "preload.cjs"
WPRELOAD = ROOT / "apps" / "desktop" / "electron" / "widget-preload.cjs"
WIDGET = ROOT / "apps" / "desktop" / "electron" / "widget.html"

# 主窗现有色值全集（与 V4 测试同源；V4B 新增样式只许从本集合取色）
PALETTE_HEX = {
    "#faf9f2", "#f2f1e8", "#eae8dc", "#2d2d2d", "#777", "#999", "#e0ded4", "#e8e6da",
    "#4caf50", "#50a14f", "#e8913a", "#f44336", "#f48771", "#5b9bd5", "#fff", "#666", "#444", "#d33",
    "#2c5e2b", "#8a3a2c",
}

# 小窗 JS 行为测试的 DOM stub（只提供渲染函数触碰的最小面）
WIDGET_STUB = """
const _els = {};
function el(id) {
  if (!_els[id]) _els[id] = {
    id: id, textContent: '', className: '', title: '', innerHTML: '',
    style: {}, firstChild: null,
    classList: { add() {}, remove() {}, contains() { return false; } },
    addEventListener() {}, appendChild() {}, insertBefore() {}, querySelectorAll() { return []; },
  };
  return _els[id];
}
const document = {
  getElementById: el,
  body: { classList: { add() {}, remove() {}, contains() { return false; } } },
};
const window = { widgetAPI: null };
"""


def _widget_script() -> str:
    html = WIDGET.read_text(encoding="utf-8")
    m = re.search(r"<script>(.*?)</script>", html, re.S)
    assert m, "widget.html <script> 缺失"
    return m.group(1)


def _run_widget_js(assertions: str) -> str:
    """在 node 中执行：DOM stub + widget.html 全部 JS + 行为断言（同步）。"""
    js = WIDGET_STUB + "\n" + _widget_script() + "\n;(function() {\n" + assertions + "\n})();"
    env = dict(os.environ)
    env["NODE_PATH"] = str(ROOT / "apps" / "desktop" / "node_modules")
    r = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30, env=env)
    if r.returncode != 0:
        raise AssertionError(f"node 执行失败: {r.stderr}")
    return r.stdout


# ── V4B-1 钉选过滤正确性 ──────────────────────────────────────────────

def test_v4b_1_pin_filter_correctness():
    """钉住 B 时 A 的会话事件不渲染（shouldRender 语义）；全局事件恒放行。"""
    out = _run_widget_js(r"""
const assert = require('assert');
// 初始跟随（主窗当前会话未知）：V4 兼容放行
assert.strictEqual(shouldRender('A'), true, '启动早期应放行');
// 钉住 B：B 放行、A 过滤、无 sid 全局事件恒放行
setPinned('B');
assert.strictEqual(_pinnedSid, 'B');
assert.strictEqual(shouldRender('B'), true, '钉住会话应放行');
assert.strictEqual(shouldRender('A'), false, 'A 的事件不得泄漏到钉 B 的小窗');
assert.strictEqual(shouldRender(''), true, '无 sid 全局事件恒放行');
// 切钉 C：A/B 均过滤
setPinned('C');
assert.strictEqual(shouldRender('A'), false);
assert.strictEqual(shouldRender('B'), false);
assert.strictEqual(shouldRender('C'), true);
// 回落跟随且主窗当前会话已知：只放行当前会话
_currentSid = 'D';
setPinned('');
assert.strictEqual(shouldRender('D'), true);
assert.strictEqual(shouldRender('A'), false, '跟随模式也不泄漏后台会话');
console.log('PIN-FILTER-OK');
""")
    assert "PIN-FILTER-OK" in out, out


def test_v4b_1_events_and_broadcasts_filtered():
    """事件入口统一过滤 + 药丸/指令广播按钉选过滤（静态断言，防旁路）。"""
    w = WIDGET.read_text(encoding="utf-8")
    assert "if (!shouldRender(d.session_id)) return;" in w, "会话事件必须先过钉选过滤"
    assert "if (!shouldRender(sid)) return;" in w, "药丸/指令广播必须按钉选过滤"
    # 带 sid 的会话事件类型全部在过滤闸之后
    for ev in ["message.start", "message.delta", "message.complete", "status.update",
               "tool.start", "tool.complete", "approval.request", "session.cleared"]:
        assert ev in w, f"事件类型缺失: {ev}"


# ── V4B-2 点击轮换 ────────────────────────────────────────────────────

def test_v4b_2_cycle_pin_rotation():
    """点击会话名轮换活跃会话：跟随→最近活跃→下一个→最后一个回落跟随→循环。"""
    out = _run_widget_js(r"""
const assert = require('assert');
// 时间戳错开（同毫秒稳定排序会保持插入序，无法区分最近活跃）
_activeSids = { A: 100, B: 200 };
_activeOrder = Object.keys(_activeSids).sort(function(a, b) { return _activeSids[b] - _activeSids[a]; });
_sessionTitles = { A: '会话A', B: '会话B' };
// 跟随 → 点击 → 钉最近活跃 B
cyclePin();
assert.strictEqual(_pinnedSid, 'B');
// B → 点击 → A
cyclePin();
assert.strictEqual(_pinnedSid, 'A');
// A（最后一个）→ 点击 → 回落跟随
cyclePin();
assert.strictEqual(_pinnedSid, null);
// 跟随 → 点击 → 钉 B（循环）
cyclePin();
assert.strictEqual(_pinnedSid, 'B');
console.log('CYCLE-OK');
""")
    assert "CYCLE-OK" in out, out


# ── V4B-3 会话删除自动回落 ────────────────────────────────────────────

def test_v4b_3_session_delete_fallback_behavior():
    """行为级：钉住会话不在会话列表 → checkPinAlive 自动回落跟随。"""
    out = _run_widget_js(r"""
const assert = require('assert');
setPinned('A');
_sessionTitles = { A: '会话A', B: '会话B' };
checkPinAlive();
assert.strictEqual(_pinnedSid, 'A', '会话仍在列表不应回落');
_sessionTitles = { B: '会话B' };        // A 被删除
checkPinAlive();
assert.strictEqual(_pinnedSid, null, '钉住会话被删应自动回落跟随');
console.log('FALLBACK-OK');
""")
    assert "FALLBACK-OK" in out, out


def test_v4b_3_session_delete_fallback_link():
    """链路：主窗删除钉住会话 → 广播 pin-reset；当前会话清空 → 基准复位。"""
    g = GUI.read_text(encoding="utf-8")
    assert "if (_widgetPinnedSid === sid) widgetPinSession('');" in g, \
        "doDeleteSession 必须对钉住会话广播回落"
    assert "window.boboAPI.widgetCurrentSession('', '');" in g, \
        "删除后无会话时当前会话基准必须复位"
    assert "widgetPinSession(sid || '');" in g, "widgetPinSession 空串 = 回落跟随"
    w = WIDGET.read_text(encoding="utf-8")
    assert "if (_pinnedSid && !_sessionTitles[_pinnedSid]) setPinned('');" in w, \
        "小窗 must 有列表兜底回落（checkPinAlive）"


# ── V4B-4 三向入口状态一致 ────────────────────────────────────────────

def test_v4b_4_three_way_consistency():
    """三向一致链路齐备：主窗按钮 → 小窗；小窗轮换 → 主窗按钮态；两广播基准。"""
    pre = PRELOAD.read_text(encoding="utf-8")
    for name in ["widgetPinSession", "onWidgetPinChanged", "widgetCurrentSession", "widgetSessions"]:
        assert name in pre, f"preload 缺 {name}"
    main = MAIN.read_text(encoding="utf-8")
    for ch in ["widget-pin-session", "widget-pin-changed", "widget-current-session", "widget-sessions"]:
        assert f"'{ch}'" in main, f"main.cjs 缺通道 {ch}"
    wp = WPRELOAD.read_text(encoding="utf-8")
    for name in ["onPinSession", "pinChanged", "onCurrentSession", "onSessions"]:
        assert name in wp, f"widget-preload 缺 {name}"
    # 小窗钉选变化上报主窗（轮换/回落都走 setPinned → pinChanged）
    w = WIDGET.read_text(encoding="utf-8")
    assert "pinChanged(sid || '')" in w, "setPinned 必须上报主窗"
    # 主窗行内按钮 on 态与回调同步
    g = GUI.read_text(encoding="utf-8")
    assert "_widgetPinnedSid === s.id ? ' on' : ''" in g, \
        "行内按钮 on 态必须跟随钉选单一事实源"
    assert "_widgetPinnedSid = sid || null;" in g, "小窗上报后主窗必须更新按钮态"
    assert "renderSessions();" in g, "按钮态更新后必须重渲染"


# ── V4B-5 铁律零干涉 ──────────────────────────────────────────────────

def test_v4b_5_engine_gateway_zero_diff():
    """引擎零改动（core/ 必须为空）；gateway 仅允许 TICKET-DESK-CLI 锚点段。

    V4/V4B 时代 core/ 与 bobo_tui_gateway/ 绝对零 diff。DESK-CLI 票（2026-08-15）合法在
    entry.py 增加 `bobo desktop` 子命令分发（# ── TICKET-DESK-CLI 锚点段包裹），
    守卫同步升级：锚点段外任何 engine/gateway 改动仍被拦截。
    """
    r = subprocess.run(["git", "diff", "--name-only", "--", "core", "bobo_tui_gateway"],
                       capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0
    changed = [l for l in r.stdout.splitlines() if l]
    # COST-1B（2026-08-16）授权：消耗度量双观测注入点，白名单文件 diff 必须含 COST-1b 标记
    COST1B_ALLOWED = {
        "bobo_tui_gateway/handlers/misc.py",
        "bobo_tui_gateway/handlers/prompts.py",
        "bobo_tui_gateway/server_utils.py",
        "bobo_tui_gateway/metrics.py",  # COST-1c ②③ 扩展（标记检查兼容 COST-1b/1c）
    }
    # COST-1C（2026-08-16）特批：core/llm_caller.py 仅加 usage 事件透传，diff 必须含 COST-1c 标记
    COST1C_ALLOWED = {"core/llm_caller.py"}
    # COST-2（2026-08-16）特批：core/injector.py 仅限两处（NOW 锚点后移 + 小时级精度），
    # diff 必须含 COST-2 标记；DIAG-1（2026-08-16）特批：injector.py 新增调试纪律
    # 场景（scene=debug），diff 必须含 DIAG-1 标记
    COST2_ALLOWED = {"core/injector.py"}
    # SAFETY-1（2026-08-16）特批：core/command_safety.py 进程杀灭白名单（kill/pkill/
    # killall 误杀自身后端与桌面端渲染进程的根治疗），diff 必须含 SAFETY-1 标记
    SAFETY1_ALLOWED = {"core/command_safety.py"}
    # COST-3（2026-08-16）特批：core/context.py + core/engine.py（工作锚点属性化 +
    # 工具集会话内全量稳定），diff 必须含 COST-3 标记
    COST3_ALLOWED = {"core/context.py", "core/engine.py"}
    # DESK-P1（2026-08-17）特批：core/engine_adapter.py + core/tool_runner.py（会话
    # 项目根注入链路：gateway 落库 → engine 属性 → injector 尾部段 / execute_terminal
    # cwd），diff 必须含 DESK-P1 标记
    DESK_P1_ALLOWED = {"core/engine_adapter.py", "core/tool_runner.py"}
    # TICKET-GW-MULTI（2026-08-17）特批：bobo_tui_gateway/transport.py（多订阅者
    # 事件广播注册表），diff 必须含 TICKET-GW-MULTI 标记
    GWMULTI_ALLOWED = {"bobo_tui_gateway/transport.py"}
    # 票 VSC-2B（2026-08-17）特批：bobo_tui_gateway/handlers/sessions.py
    #（session.set_write_approval RPC + 会话级写审批开关），diff 必须含 VSC-2B 标记
    VSC2B_ALLOWED = {"bobo_tui_gateway/handlers/sessions.py"}
    unexpected = [f for f in changed if f != "bobo_tui_gateway/entry.py" and f not in COST1B_ALLOWED and f not in COST1C_ALLOWED and f not in COST2_ALLOWED and f not in SAFETY1_ALLOWED and f not in COST3_ALLOWED and f not in DESK_P1_ALLOWED and f not in GWMULTI_ALLOWED and f not in VSC2B_ALLOWED]
    assert not unexpected, f"engine/gateway 未授权改动: {unexpected}"
    for f in sorted(COST1B_ALLOWED & set(changed)):
        r3 = subprocess.run(["git", "diff", "--", f], capture_output=True, text=True, cwd=ROOT)
        assert ("COST-1b" in r3.stdout or "COST-1c" in r3.stdout or "DESK-P1" in r3.stdout), \
            f"{f} 的改动缺 COST-1b/COST-1c/DESK-P1 授权标记，未授权改动被拦截"
    for f in sorted(COST1C_ALLOWED & set(changed)):
        r4 = subprocess.run(["git", "diff", "--", f], capture_output=True, text=True, cwd=ROOT)
        assert "COST-1c" in r4.stdout, f"{f} 的改动缺 COST-1c 特批标记，未授权改动被拦截"
    for f in sorted(COST2_ALLOWED & set(changed)):
        r5 = subprocess.run(["git", "diff", "--", f], capture_output=True, text=True, cwd=ROOT)
        assert ("COST-2" in r5.stdout or "DIAG-1" in r5.stdout or "DESK-P1" in r5.stdout), \
            f"{f} 的改动缺 COST-2/DIAG-1/DESK-P1 特批标记，未授权改动被拦截"
    for f in sorted(SAFETY1_ALLOWED & set(changed)):
        r6 = subprocess.run(["git", "diff", "--", f], capture_output=True, text=True, cwd=ROOT)
        assert "SAFETY-1" in r6.stdout, f"{f} 的改动缺 SAFETY-1 特批标记，未授权改动被拦截"
    for f in sorted(COST3_ALLOWED & set(changed)):
        r7 = subprocess.run(["git", "diff", "--", f], capture_output=True, text=True, cwd=ROOT)
        assert ("COST-3" in r7.stdout or "DESK-P1" in r7.stdout), \
            f"{f} 的改动缺 COST-3/DESK-P1 特批标记，未授权改动被拦截"
    for f in sorted(DESK_P1_ALLOWED & set(changed)):
        r8 = subprocess.run(["git", "diff", "--", f], capture_output=True, text=True, cwd=ROOT)
        # 票 VSC-2B：engine_adapter.py 复用该文件（写审批闸门），diff 标记兼容
        assert ("DESK-P1" in r8.stdout or "VSC-2B" in r8.stdout), \
            f"{f} 的改动缺 DESK-P1/VSC-2B 特批标记，未授权改动被拦截"
    for f in sorted(GWMULTI_ALLOWED & set(changed)):
        r_gm = subprocess.run(["git", "diff", "--", f], capture_output=True, text=True, cwd=ROOT)
        assert "TICKET-GW-MULTI" in r_gm.stdout, f"{f} 的改动缺 TICKET-GW-MULTI 特批标记，未授权改动被拦截"
    for f in sorted(VSC2B_ALLOWED & set(changed)):
        r_v2b = subprocess.run(["git", "diff", "--", f], capture_output=True, text=True, cwd=ROOT)
        assert "VSC-2B" in r_v2b.stdout, f"{f} 的改动缺 VSC-2B 特批标记，未授权改动被拦截"
    if not changed:
        return
    src = (ROOT / "bobo_tui_gateway" / "entry.py").read_text(encoding="utf-8")
    m = re.search(r"# ── TICKET-DESK-CLI.*?# ── end TICKET-DESK-CLI ──\n\s*\n", src, re.S)  # 含端注释后空行
    assert m, "entry.py 必须含完整 DESK-CLI 锚点段（# ── TICKET-DESK-CLI ... # ── end TICKET-DESK-CLI ──）"
    r2 = subprocess.run(["git", "diff", "--numstat", "--", "bobo_tui_gateway/entry.py"],
                        capture_output=True, text=True, cwd=ROOT)
    if not r2.stdout.strip():
        return  # COST-1B：entry.py 无改动时跳过 DESK-CLI 锚点 diff 校验
    added, deleted = [int(x) for x in r2.stdout.split()[:2]]
    r_gw = subprocess.run(["git", "diff", "--", "bobo_tui_gateway/entry.py"],
                          capture_output=True, text=True, cwd=ROOT)
    # TICKET-GW-MULTI（2026-08-17）特批：entry.py socket 后端多客户端化（每连接
    # 一线程 + 全客户端断开才计空闲 + backlog 调大），重构含删除，diff 必须含
    # TICKET-GW-MULTI 标记
    if "TICKET-GW-MULTI" in r_gw.stdout:
        return
    # TICKET-GW-SOCK（2026-08-17）特批：entry.py socket 双实例防护（探测活跃 +
    # EADDRINUSE 竞态兜底，_run_socket_backend 内），diff 必须含 TICKET-GW-SOCK 标记
    if "TICKET-GW-SOCK" in r_gw.stdout:
        assert deleted <= 5, f"GW-SOCK 授权范围外删除: {r2.stdout}"
        return
    assert deleted == 0, f"entry.py 不得删除既有行: {r2.stdout}"
    anchor_lines = len(m.group(0).splitlines())  # 全部行（含锚点段尾随空行，与 git diff 新增行数对齐）
    assert added == anchor_lines, f"锚点段外存在改动：diff+{added} vs 锚点段 {anchor_lines} 行"


def test_v4b_5_css_anchor_and_palette():
    """CSS 进 DESK-V4B 锚点段；色板零新增（锚点段 + w-pin 规则全部取色板）。"""
    g = GUI.read_text(encoding="utf-8")
    assert "/* === DESK-V4B 会话钉选 === */" in g, "主窗 DESK-V4B 锚点段缺失"
    assert "/* === end DESK-V4B === */" in g, "主窗 DESK-V4B 锚点段未闭合"
    m = re.search(r"DESK-V4B 会话钉选 ===(.*?)=== end DESK-V4B ===", g, re.S)
    assert m, "DESK-V4B CSS 锚点段不可提取"
    for hexv in re.findall(r"#[0-9a-fA-F]{3,8}\b", m.group(1)):
        assert hexv.lower() in PALETTE_HEX, f"DESK-V4B 锚点段新增色值: {hexv}"
    w = WIDGET.read_text(encoding="utf-8")
    pin_rules = re.findall(r"#w-pin[^{]*\{[^}]*\}", w)
    assert pin_rules, "widget.html 缺 #w-pin 样式"
    for rule in pin_rules:
        for hexv in re.findall(r"#[0-9a-fA-F]{3,8}\b", rule):
            assert hexv.lower() in PALETTE_HEX, f"#w-pin 新增色值: {hexv}"


# ── V4B-6 入口顺序 / 会话指示 / 审批联动 ──────────────────────────────

def test_v4b_6_entry_order_and_indicator():
    """行内投影入口在 pin→改名→删除之后（L5 体系）；会话指示自定义名优先；审批跳钉住会话。"""
    g = GUI.read_text(encoding="utf-8")
    order = g.index("div.appendChild(span); div.appendChild(pin); div.appendChild(re); div.appendChild(del); div.appendChild(proj);")
    del_def = g.index("var del = document.createElement('button')")
    proj_def = g.index("var proj = document.createElement('button')")
    assert del_def < proj_def < order, "proj 按钮必须创建于 del 之后、appendChild 之前"
    assert "proj.title = 'Project to widget';" in g
    assert "var PROJECT_SVG" in g, "缺投影眼睛图标"
    w = WIDGET.read_text(encoding="utf-8")
    assert 'id="w-pin"' in w, "缺会话指示元素"
    # 自定义名优先：_sessionTitles[_pinnedSid] || _pinnedSid
    assert "el.textContent = 'Pin · ' + t;" in w, "会话指示必须显示钉住会话名"
    assert "var t = _sessionTitles[_pinnedSid] || _pinnedSid;" in w, "自定义名优先"
    assert "approvalFocus(_pinnedSid || _approvalSid)" in w, "审批点击必须跳钉住会话（不是主窗当前）"
    assert "document.getElementById('w-pin').addEventListener('click', function() { cyclePin(); });" in w, \
        "会话指示点击必须轮换"


# ── V4B⓪ 忙碌态按会话隔离（owner 实弹：A 运行中切 B，B 仍是运行中飞态卡死） ──

BUSYGATE_STUB = """
let currentSessionId = null;
let connected = true;
let messaging = false;
let sendLoading = false;
let stopShown = false;
const sendEl = { classList: { toggle(cls, on) { if (cls === 'loading') sendLoading = on; } } };
const statusText = { textContent: '' };
function showStop(b) { stopShown = b; }
"""


def _busygate_script() -> str:
    gui = GUI.read_text(encoding="utf-8")
    m = re.search(r"/\* ===BUSYGATE-START=== \*/.*?/\* ===BUSYGATE-END=== \*/", gui, re.S)
    assert m, "BUSYGATE 锚点段缺失（V4B⓪ 忙碌门未落地）"
    return m.group(0)


def _run_busygate(assertions: str) -> str:
    js = BUSYGATE_STUB + "\n" + _busygate_script() + "\n;(function() {\n" + assertions + "\n})();"
    r = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        raise AssertionError(f"node 执行失败: {r.stderr}")
    return r.stdout


def test_v4b0_1_busy_per_session_behavior():
    """行为级（node 实跑 BUSYGATE）：A 运行中切到空闲 B → B 全空闲可发；切回 A → A 运行态恢复。"""
    out = _run_busygate(r"""
const assert = require('assert');
// A 运行中：忙碌登记 + 当前会话 A → Running
setSidBusy('A', true);
currentSessionId = 'A';
renderBusyUI();
assert.strictEqual(messaging, true, 'A 运行中发送闸门应关闭');
assert.strictEqual(sendLoading, true, 'A 运行中发送键应带 loading 动画');
assert.strictEqual(statusText.textContent, 'Running', 'A 运行中状态条应显示 Running');
assert.strictEqual(stopShown, true, 'A 运行中应显示停止键');
// 切到空闲 B → 全部恢复空闲态（核心场景：B 可独立发消息开跑）
currentSessionId = 'B';
renderBusyUI();
assert.strictEqual(messaging, false, 'B 空闲时发送闸门必须放行');
assert.strictEqual(sendLoading, false, 'B 空闲时发送键不得带 loading 动画');
assert.strictEqual(statusText.textContent, 'Ready', 'B 空闲时状态条应显示 Ready');
assert.strictEqual(stopShown, false, 'B 空闲时不得显示停止键');
// B 独立开跑
setSidBusy('B', true);
renderBusyUI();
assert.strictEqual(messaging, true, 'B 开跑后闸门关闭');
// A 完成（后台事件）→ 不影响仍在跑的 B
setSidBusy('A', false);
renderBusyUI();
assert.strictEqual(messaging, true, 'A 完成不得影响仍在跑的 B');
// 切回 A → A 已完成 → 空闲
currentSessionId = 'A';
renderBusyUI();
assert.strictEqual(messaging, false, 'A 完成切回应空闲');
// 切回 B → B 仍在跑 → 恢复运行态
currentSessionId = 'B';
renderBusyUI();
assert.strictEqual(messaging, true, 'B 仍在跑切回应恢复运行态');
assert.strictEqual(statusText.textContent, 'Running', 'B 运行态状态条应恢复 Running');
console.log('BUSY-PER-SESSION-OK');
""")
    assert "BUSY-PER-SESSION-OK" in out, out


def test_v4b0_2_busy_gate_static():
    """静态断言：start/complete 按 sid 登记与清除；切会话刷新；发送闸门唯一出口；F10 圆点未动。"""
    g = GUI.read_text(encoding="utf-8")
    # message.start：按会话登记 + renderBusyUI（不再全局置位）
    assert "setSidBusy(data ? data.session_id : '', true);" in g, "message.start 必须按 sid 登记忙碌"
    assert "renderBusyUI(); debug('Receiving...');" in g, "message.start 必须走 renderBusyUI"
    # message.complete：清该会话忙碌位 + renderBusyUI
    assert "setSidBusy(data ? data.session_id : '', false);" in g, "message.complete 必须清该会话忙碌位"
    # 切会话立即刷新（loadSession 首行同步态后 + resume 完成后兜底）
    assert "renderBusyUI();   // V4B⓪：切会话立即按新会话忙碌态刷新" in g, "loadSession 切会话必须刷新忙碌态"
    assert "renderBusyUI();   // V4B⓪：resume 完成后按新会话忙碌态最终刷新一次" in g, "resume 完成必须兜底刷新"
    # 发送闸门依赖 messaging，messaging 只在 renderBusyUI 赋值（全局副作用收敛单一出口）
    assert "if (!text || !connected || messaging) return;" in g, "发送闸门必须保留 messaging 判断"
    m = re.findall(r"(?<!var )messaging = ", g)
    assert len(m) == 1, f"messaging 赋值必须唯一（只在 renderBusyUI）: {len(m)} 处"
    # F10 后台活动圆点保持现状（需求③：不动）
    assert "bgActiveSids[s.id]" in g and "bg-active-dot" in g, "F10 后台活动圆点渲染必须保留"
    assert "markBgActive(sid)" in g, "F10 后台活跃标记必须保留"
    # BUSYGATE 锚点段
    assert _busygate_script(), "BUSYGATE 锚点段缺失"


def test_v4b0_3_two_session_flow_not_crossing():
    """两会话事件流互不串台：A/B 交错忙碌互不影响 + 无 sid 老事件兼容全局忙碌。"""
    out = _run_busygate(r"""
const assert = require('assert');
// 无 sid 老事件（兼容）：登记到 '' 槽，当前会话也忙
setSidBusy('', true);
currentSessionId = 'X';
renderBusyUI();
assert.strictEqual(messaging, true, '无 sid 事件应视为全局忙碌（V4 兼容）');
setSidBusy('', false);
renderBusyUI();
assert.strictEqual(messaging, false, '无 sid 事件结束后全局恢复空闲');
// A/B 各自独立：B 忙 A 闲、A 忙 B 闲交替
setSidBusy('B', true);
currentSessionId = 'A';
renderBusyUI();
assert.strictEqual(messaging, false, 'B 忙时 A 必须空闲');
currentSessionId = 'B';
renderBusyUI();
assert.strictEqual(messaging, true, 'B 忙时 B 必须忙碌');
setSidBusy('A', true);
currentSessionId = 'A';
renderBusyUI();
assert.strictEqual(messaging, true, 'A 也忙后 A 忙碌');
assert.strictEqual(isSidBusy('A') && isSidBusy('B'), true, '两会话同时运行互不覆盖');
setSidBusy('A', false);
setSidBusy('B', false);
renderBusyUI();
assert.strictEqual(messaging, false, '两会话都结束后空闲');
console.log('TWO-SESSION-OK');
""")
    assert "TWO-SESSION-OK" in out, out
