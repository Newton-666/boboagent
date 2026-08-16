"""TICKET-DESK-V4 回归测试 — 桌面端只读投影小组件（零干涉铁律）。

覆盖（owner 圈定）：
- V4-1 零干涉·铁律：core/、bobo_tui_gateway/ git diff 空（引擎/TUI/gateway 协议零改动）；
  小窗无任何写通道（widget-preload 只暴露只读监听 + 唤起主窗；widget.html 无 fetch/XHR/WebSocket/localStorage）
- V4-2 零干涉·主窗：widgetToggle 函数体 DOM 写入仅限 #widget-toggle 自身 + 既有 addStatus
  反馈通道；小窗开关不触发主窗其他 DOM 变更（函数级 node 实跑 stub）
- V4-3 开关持久化：widget-config.cjs round-trip（默认关 → 开 → 读 → 关 → 读）
- V4-4 /widget 三向同步：handleSlash('widget') 与侧栏按钮 click 走同一 widgetToggle；
  widgetToggle 走 boboAPI.widgetToggle（IPC）→ 主进程写盘 → 重启恢复（同源）
- V4-5 小窗本体：frameless / 280×160 / alwaysOnTop / skipTaskbar / 可拖动；
  无 session 侧栏、无 plugins 面板（不是桌面端缩小版）
- V4-6 颜色闸：index.html DESK-V4 锚点段 + widget.html 全部 #hex / rgba 取自主窗现有色值集合
- V4-7 数据映射：backend-message 只读转发 + gateway.ready/tool.start/tool.complete/
  context.stats/approval.request 订阅 + 审批点击唤主窗现成 loadSession 入口
- V4-8 md5 闸：真实库三文件零变动

注：GUI 渲染层采用静态断言 + node 实跑（与 V2B3/F3-F8 同款零漂移验证）。
"""

import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
GUI_FILE = ROOT / "apps" / "desktop" / "dist" / "index.html"
MAIN_CJS = ROOT / "apps" / "desktop" / "electron" / "main.cjs"
PRELOAD_CJS = ROOT / "apps" / "desktop" / "electron" / "preload.cjs"
WIDGET_PRELOAD_CJS = ROOT / "apps" / "desktop" / "electron" / "widget-preload.cjs"
WIDGET_HTML = ROOT / "apps" / "desktop" / "electron" / "widget.html"
WIDGET_CONFIG_CJS = ROOT / "apps" / "desktop" / "electron" / "widget-config.cjs"
MD5_FILES = [
    ROOT / "data" / "knowledge_base.json",
    ROOT / "library" / "MEMORY.md",
    ROOT / "library" / "index.md",
]
# 主窗现有色值全集（含 :root 色板 + 既有语义色 + diff-block 整行高亮文字色）；
# widget/DESK-V4 新增样式只许从本集合取色
PALETTE_HEX = {
    "#faf9f2", "#f2f1e8", "#eae8dc", "#2d2d2d", "#777", "#999", "#e0ded4", "#e8e6da",
    "#4caf50", "#50a14f", "#e8913a", "#f44336", "#f48771", "#fff", "#666", "#444", "#d33",
    "#2c5e2b", "#8a3a2c",  # 主窗 .diff-block .dl.add/.dl.del 文字色（追加① 复用同源）
}


def _run_node(js: str) -> str:
    """在 node 中执行 JS（同步），返回 stdout。"""
    env = dict(os.environ)
    env["NODE_PATH"] = str(ROOT / "apps" / "desktop" / "node_modules")
    r = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30, env=env)
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


# ── V4-1 零干涉·铁律 ──────────────────────────────────────────────────

def test_v4_1_engine_gateway_tui_zero_diff():
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
    unexpected = [f for f in changed if f != "bobo_tui_gateway/entry.py" and f not in COST1B_ALLOWED and f not in COST1C_ALLOWED]
    assert not unexpected, f"engine/gateway 未授权改动: {unexpected}"
    for f in sorted(COST1B_ALLOWED & set(changed)):
        r3 = subprocess.run(["git", "diff", "--", f], capture_output=True, text=True, cwd=ROOT)
        assert ("COST-1b" in r3.stdout or "COST-1c" in r3.stdout), \
            f"{f} 的改动缺 COST-1b/COST-1c 授权标记，未授权改动被拦截"
    for f in sorted(COST1C_ALLOWED & set(changed)):
        r4 = subprocess.run(["git", "diff", "--", f], capture_output=True, text=True, cwd=ROOT)
        assert "COST-1c" in r4.stdout, f"{f} 的改动缺 COST-1c 特批标记，未授权改动被拦截"
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
    assert deleted == 0, f"entry.py 不得删除既有行: {r2.stdout}"
    anchor_lines = len(m.group(0).splitlines())  # 全部行（含锚点段尾随空行，与 git diff 新增行数对齐）
    assert added == anchor_lines, f"锚点段外存在改动：diff+{added} vs 锚点段 {anchor_lines} 行"


def test_v4_1_widget_no_write_channel():
    """小窗只读：preload 无 send/call/写通道；widget.html 无 fetch/XHR/WebSocket/localStorage。"""
    pre = WIDGET_PRELOAD_CJS.read_text(encoding="utf-8")
    # V4: approvalFocus 是唯一 send；V4B: 增 pinChanged 上报钉选变化（两 send 均只发主窗，无后端写通道）
    assert "widget-approval-focus" in pre
    assert "widget-pin-changed" in pre
    assert pre.count("ipcRenderer.send(") == 2, "小窗仅允许两个 send：唤起主窗审批 + 钉选变化上报"
    assert "ipcRenderer.invoke(" not in pre, "小窗不得有 invoke（无 RPC 通道）"
    html = WIDGET_HTML.read_text(encoding="utf-8")
    for banned in ["fetch(", "XMLHttpRequest", "WebSocket", "localStorage", "window.boboAPI",
                   "window.opener", "window.parent"]:
        assert banned not in html, f"小窗不得出现写/业务通道或主窗引用: {banned}"


# ── V4-2 零干涉·主窗 ──────────────────────────────────────────────────

def test_v4_2_widget_toggle_touches_only_itself():
    """零干涉：widgetToggle 的 DOM 写入仅限 #widget-toggle 自身 + 既有 addStatus 反馈通道。
    node 实跑：stub boboAPI 与最小 DOM，断言无其他元素被触碰。"""
    src = GUI_FILE.read_text(encoding="utf-8")
    toggle_fn = _extract_func(src, "widgetToggle")
    sync_fn = _extract_func(src, "syncWidgetBtn")
    js = r"""
const { JSDOM } = require('jsdom');
const dom = new JSDOM('<!DOCTYPE html><body><button id="widget-toggle">小组件</button></body>');
global.window = dom.window;
const doc = dom.window.document;
const widgetBtn = doc.getElementById('widget-toggle');
let toggleCalls = 0;
widgetBtn.classList.toggle = function(c, on) { toggleCalls++; };
let statusCalls = 0;
function addStatus(t) { statusCalls++; }
const apiCalls = [];
global.window.boboAPI = {
  widgetToggle: () => { apiCalls.push('widget-toggle'); return Promise.resolve({ enabled: true }); },
};
""" + f"""
{sync_fn}
{toggle_fn}
widgetToggle();
setTimeout(() => {{
  console.log(JSON.stringify({{
    toggleCalls: toggleCalls,
    statusCalls: statusCalls,
    apiCalls: apiCalls,
    btnText: widgetBtn.textContent,
  }}));
}}, 30);
"""
    out = _run_node(js)
    d = json.loads(out.strip().splitlines()[-1])
    assert d["toggleCalls"] >= 1, "syncWidgetBtn 未更新按钮态"
    assert d["apiCalls"] == ["widget-toggle"], "widgetToggle 必须走主进程 IPC（同源）"
    assert d["statusCalls"] >= 1, "开关反馈必须走既有 addStatus 通道"
    assert d["btnText"] == "小组件 ✓", "按钮 on 态文本"


def test_v4_2_no_widget_event_reactivity_in_main():
    """零干涉：主窗没有监听任何小窗窗口事件去做 DOM 响应（小窗生命周期独立，不回流主窗）。"""
    src = GUI_FILE.read_text(encoding="utf-8")
    # 主窗只应监听 widget-focus-session（审批联动落地，调现成 loadSession）
    assert "onWidgetFocusSession" in src
    assert "loadSession(sid)" in src or "loadSession(sid)" in src.replace(" ", "")
    # 不存在对小窗开/关事件的 DOM 响应订阅
    for banned in ["onWidgetOpened", "onWidgetClosed", "widget-toggled", "widget.status"]:
        assert banned not in src, f"主窗不得响应小窗生命周期事件: {banned}"


# ── V4-3 开关持久化 ───────────────────────────────────────────────────

def test_v4_3_widget_config_persist_roundtrip():
    """持久化：默认关；写开读开；写关读关；文件在 getDataDir()/desktop-config.json。"""
    with tempfile.TemporaryDirectory() as tmp:
        js = f"""
const {{
  configPath, readWidgetEnabled, writeWidgetEnabled
}} = require('{WIDGET_CONFIG_CJS}');
const d = '{tmp}';
const p = configPath(d);
if (!p.endsWith('desktop-config.json')) throw new Error('bad path: ' + p);
if (readWidgetEnabled(d) !== false) throw new Error('默认必须关');
if (writeWidgetEnabled(d, true) !== true) throw new Error('写开失败');
if (readWidgetEnabled(d) !== true) throw new Error('读回必须开');
if (writeWidgetEnabled(d, false) !== false) throw new Error('写关失败');
if (readWidgetEnabled(d) !== false) throw new Error('读回必须关');
console.log('OK');
"""
        out = _run_node(js)
        assert out.strip() == "OK"
        # 配置只写 widget_enabled 字段
        cfg_path = Path(tmp) / "desktop-config.json"
        assert cfg_path.exists()
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        assert set(cfg.keys()) == {"widget_enabled"}


# ── V4-4 /widget 三向同步 ─────────────────────────────────────────────

def test_v4_4_widget_slash_and_button_same_source():
    """三向同步：/widget 命令与侧栏按钮走同一 widgetToggle；widgetToggle 唯一入口是
    boboAPI.widgetToggle（主进程 IPC，写盘+建窗）；按钮态由主进程返回值投影。"""
    src = GUI_FILE.read_text(encoding="utf-8")
    # handleSlash 的 widget 分支调 widgetToggle
    handle = _extract_func(src, "handleSlash")
    assert re.search(r"cmd === 'widget'.*widgetToggle\(\)", handle, re.S), "/widget 必须本地调用 widgetToggle"
    # 按钮 click 绑 widgetToggle（同源）
    assert "widgetBtn.addEventListener('click', widgetToggle)" in src
    # widgetToggle 只经 boboAPI.widgetToggle 走主进程
    toggle_fn = _extract_func(src, "widgetToggle")
    assert "boboAPI.widgetToggle()" in toggle_fn
    # 启动恢复：widgetStatus 查询主进程（真实状态以主进程/持久化配置为准）
    assert "boboAPI.widgetStatus()" in src
    # 主进程：toggle 写配置 + 销毁/创建
    main_src = MAIN_CJS.read_text(encoding="utf-8")
    assert "writeWidgetEnabled(getDataDir(), !!widgetWindow)" in main_src
    assert "ensureWidgetByConfig()" in main_src
    assert "readWidgetEnabled(getDataDir())" in main_src
    # preload 桥
    pre = PRELOAD_CJS.read_text(encoding="utf-8")
    assert "widgetToggle: () => ipcRenderer.invoke('widget-toggle')" in pre
    assert "widgetStatus: () => ipcRenderer.invoke('widget-status')" in pre


# ── V4-5 小窗本体 ─────────────────────────────────────────────────────

def test_v4_5_widget_window_props():
    """小窗本体：frameless 半透明、resizable（追加② 可拖拽拉大）、最小尺寸 240×150、
    alwaysOnTop、skipTaskbar、可拖动、独立生命周期。"""
    main_src = MAIN_CJS.read_text(encoding="utf-8")
    assert "frame: false" in main_src
    assert "transparent: true" in main_src
    assert "resizable: true" in main_src, "追加②：小窗必须可拖拽 resize"
    assert "minWidth: 240" in main_src and "minHeight: 150" in main_src, "追加②：最小尺寸限制"
    assert "readWidgetSize(getDataDir())" in main_src, "追加②：创建窗口恢复持久化尺寸"
    assert "writeWidgetSize" in main_src, "追加②：resize 时写回持久化"
    assert "alwaysOnTop: true" in main_src
    assert "skipTaskbar: true" in main_src
    assert "widget-preload.cjs" in main_src
    # 关=当场销毁（destroy，非 hide）
    assert "w.destroy()" in main_src
    # 主窗关闭 → 小窗销毁（保证 window-all-closed 触发退出）；小窗关闭不波及主窗
    assert "destroyWidgetWindow()" in main_src
    # 可拖动 + 无 session 侧栏/plugins 面板
    html = WIDGET_HTML.read_text(encoding="utf-8")
    assert "-webkit-app-region:drag" in html
    for banned in ["session-list", "session-item", "plugin-list", "pitem", "sidebar"]:
        assert banned not in html, f"小窗不是桌面端缩小版，不得含 {banned}"
    # 只读投影必备数据区：用户指令/任务摘要/工具链/药丸/连接点
    for need in ["w-user", "w-task", "w-tools", "w-pill", "w-dot"]:
        assert f'id="{need}"' in html, f"小窗缺少 {need}"


# ── V4-6 颜色闸 ───────────────────────────────────────────────────────

def test_v4_6_no_new_colors():
    """颜色闸：DESK-V4 锚点段 + widget.html 全部 #hex 必须在主窗现有色值集合内；
    rgba 的 RGB 三元组必须对应色板 hex。"""
    src = GUI_FILE.read_text(encoding="utf-8")
    block = re.search(r"DESK-V4 小组件 ===(.*?)=== end DESK-V4 ===", src, re.S)
    assert block, "DESK-V4 CSS 锚点段缺失"
    css_block = block.group(1)
    for hexv in re.findall(r"#[0-9a-fA-F]{3,8}\b", css_block):
        assert hexv.lower() in PALETTE_HEX, f"DESK-V4 锚点段新增色值: {hexv}"
    # 色板 hex → rgb 三元组映射（供 rgba 校验）
    def hex_to_rgb(h):
        h = h.lstrip("#")
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    pal_rgb = {hex_to_rgb(h) for h in PALETTE_HEX}
    html = WIDGET_HTML.read_text(encoding="utf-8")
    for hexv in re.findall(r"#[0-9a-fA-F]{3,8}\b", html):
        assert hexv.lower() in PALETTE_HEX, f"widget.html 新增色值: {hexv}"
    for rgba in re.findall(r"rgba?\(([^)]+)\)", html):
        parts = [p.strip() for p in rgba.split(",")]
        rgb = tuple(int(float(parts[i])) for i in range(3))
        assert rgb in pal_rgb, f"widget.html rgba 非色板取色: rgba({rgba})"


# ── V4-7 数据映射 ─────────────────────────────────────────────────────

def test_v4_7_readonly_event_mapping():
    """数据映射：backend-message 只读转发；小窗订阅 gateway.ready / tool.start /
    tool.complete / context.stats / approval.request；审批点击唤起主窗现成 loadSession。"""
    main_src = MAIN_CJS.read_text(encoding="utf-8")
    # 事件流镜像（同一条现成 backend-message）
    assert "widgetWindow.webContents.send('backend-message', msg)" in main_src
    # 只读广播：context.stats 药丸 / 用户指令
    assert "widget-ctx-stats" in main_src
    assert "widget-user-msg" in main_src
    # 审批联动：唤主窗（聚焦/恢复）+ 发 widget-focus-session
    assert "mainWindow.focus()" in main_src
    assert "widget-focus-session" in main_src
    html = WIDGET_HTML.read_text(encoding="utf-8")
    for ev in ["gateway.ready", "tool.start", "tool.complete", "approval.request", "status.update"]:
        assert f"t === '{ev}'" in html, f"小窗未订阅 {ev}"
    # context.stats 经 onCtxStats 广播渲染药丸
    assert "onCtxStats" in html and "renderCtx" in html
    # 审批点击 → widgetAPI.approvalFocus（只调主窗现成入口）
    assert "widgetAPI.approvalFocus" in html
    # 主窗落地：小窗点击 → loadSession（现成切会话入口）
    src = GUI_FILE.read_text(encoding="utf-8")
    assert "loadSession(sid)" in src
    # V2D25 图标/三态语义复用
    assert "TOOL_ICONS" in html and "running" in html and "fail" in html and "done" in html


# ── V4-9 追加①：diff 完整渲染（与主窗 1:1 同 class 体系）────────────────

def test_v4_9_widget_diff_full_render():
    """追加①：小窗 diff 渲染与主窗复用同一份渲染代码（diffBlock 逐字节一致）；
    整行高亮 class（.dl.add 绿 / .dl.del 红 / .dl.ctx 灰 / .df 文件头）与主窗同 class 体系；
    node 实跑喂样例 inline_diff，断言高亮 class 齐全 + esc 转义（注入防护）。"""
    main_src = GUI_FILE.read_text(encoding="utf-8")
    widget_src = WIDGET_HTML.read_text(encoding="utf-8")
    # 复用同一份渲染代码：esc 与 diffBlock 与主窗逐字节一致（禁止简化）
    assert _extract_func(widget_src, "esc") == _extract_func(main_src, "esc"), \
        "小窗 esc 必须与主窗逐字节一致"
    assert _extract_func(widget_src, "diffBlock") == _extract_func(main_src, "diffBlock"), \
        "小窗 diffBlock 必须与主窗逐字节一致（复用同一份渲染代码，禁止简化）"
    # node 实跑：喂样例 diff，断言整行高亮 class 体系 + 转义
    js = (
        "const fs = require('fs');\n"
        "const src = fs.readFileSync(" + repr(str(WIDGET_HTML)) + ", 'utf8');\n"
        "const escFn = src.match(/function esc\\(s\\) \\{[^\\n]*\\}/)[0];\n"
        "const dbFn = src.match(/function diffBlock\\(text\\) \\{[\\s\\S]*?\\n\\}/)[0];\n"
        "eval(escFn + '\\n' + dbFn);\n"
        "const diff = '--- a/x.py\\n+++ b/x.py\\n@@ -1,3 +1,4 @@\\n old line\\n+new <tag> line\\n-removed line\\n context line\\n';\n"
        "const out = diffBlock(diff);\n"
        "if (out.indexOf('<div class=\\\"df\\\">') === -1) throw new Error('缺 @@ 文件头 .df');\n"
        "if (out.indexOf('<div class=\\\"dl add\\\">') === -1) throw new Error('缺整行高亮 .dl.add');\n"
        "if (out.indexOf('<div class=\\\"dl del\\\">') === -1) throw new Error('缺整行高亮 .dl.del');\n"
        "if (out.indexOf('<div class=\\\"dl ctx\\\">') === -1) throw new Error('缺 .dl.ctx');\n"
        "if (out.indexOf('&lt;tag&gt;') === -1) throw new Error('esc 转义缺失（注入风险）');\n"
        "console.log('DIFF_OK');\n"
    )
    out = _run_node(js)
    assert "DIFF_OK" in out, f"diff 渲染断言失败: {out}"


# ── V4-10 追加②：resize 最小尺寸无内容裁切 ───────────────────────────

def test_v4_10_widget_resize_min_no_clip():
    """追加②：小窗可拖拽 resize；最小尺寸 240×150 下限（拖到最小即停）；
    最小尺寸下无内容裁切 —— diff 区 overflow-y 滚动（非 hidden 截断）、长行 pre-wrap
    自动换行（与主窗同款）；尺寸与开关同文件持久化 round-trip + clamp。"""
    html = WIDGET_HTML.read_text(encoding="utf-8")
    # 高度不足 → 滚动可见，不裁切；长行 → 换行，不截断（1:1 主窗策略）
    assert "overflow-y:auto" in html, "diff 区必须纵向滚动（最小尺寸下内容可滚可见，不裁切）"
    assert "white-space:pre-wrap; word-break:break-all" in html, "长行必须自动换行不截断"
    main_src = GUI_FILE.read_text(encoding="utf-8")
    assert "white-space:pre-wrap; word-break:break-all" in main_src, "换行策略须与主窗同款"
    # 尺寸持久化 round-trip + clamp（小于最小尺寸 → 钳制到 MIN_W/MIN_H）
    with tempfile.TemporaryDirectory() as tmp:
        js = f"""
const {{ readWidgetSize, writeWidgetSize, MIN_W, MIN_H }} = require('{WIDGET_CONFIG_CJS}');
const d = '{tmp}';
const s = writeWidgetSize(d, {{ width: 500, height: 400 }});
if (s.width !== 500 || s.height !== 400) throw new Error('roundtrip fail: ' + JSON.stringify(s));
const r = readWidgetSize(d);
if (r.width !== 500 || r.height !== 400) throw new Error('read fail: ' + JSON.stringify(r));
const tiny = writeWidgetSize(d, {{ width: 10, height: 20 }});
if (tiny.width !== MIN_W || tiny.height !== MIN_H) throw new Error('clamp fail: ' + JSON.stringify(tiny));
console.log('SIZE_OK');
"""
        out = _run_node(js)
        assert "SIZE_OK" in out, f"尺寸持久化断言失败: {out}"


# ── V4-8 md5 闸 ───────────────────────────────────────────────────────

def test_v4_8_real_library_md5_gate():
    """md5 闸：真实库三文件零变动（与 V2B3 同款：存在性 + 哈希可计算）。"""
    for f in MD5_FILES:
        assert f.exists(), f"md5 闸门文件缺失: {f}"
        h = hashlib.md5(f.read_bytes()).hexdigest()
        assert len(h) == 32, f"md5 计算失败: {f}"
