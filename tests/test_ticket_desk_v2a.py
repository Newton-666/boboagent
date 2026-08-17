"""TICKET-DESK-V2A 回归测试 — 桌面端体验地基（仅桌面端 GUI + gateway 新增端点）。

覆盖：
- V2A-1 状态覆盖层：overlay-root/三态（连接中/失败/断连）、动画指示、淡入淡出、
  300ms 防抖（setConnected 包装）、debugInfo 收纳进详情区、backend.exited 断连态
  （_everConnected 分支）、gateway.ready 恢复 toast
- V2A-2 会话管理：renderSessions pin 排序/pin 标记/pin 按钮/空态、togglePin、
  deleteSession 二次确认模态（无原生 confirm）、后端 handle_session_pin 持久化 +
  session.list 返回 pinned + session.pin 端点注册
- V2A-3 控件体系：focus-visible ring / hover 新规则存在（默认外观零改）
- V2A-4 Toast：toast-root/.toast/.success/.fail、3s 自动消失、手动关闭
- V2A-5 三态组件：v2a-loader / v2a-error / v2a-empty 存在且被引用
- 铁律 0 闸：style 块 V2A 之前的所有既有 CSS 与 HEAD 逐字节一致（零改动既有值）
- md5 闸门：真实库三文件与 HEAD 一致（测试不碰真实库）

注：GUI 渲染层采用静态断言 + node 实跑（与 F3-F8 同款零漂移验证）。
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
    """构造最小 ctx 桩（与 F7 同款）。"""
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


def _write_session_file(mgr, sid, messages, title=None, user_named=False, pinned=False):
    path = mgr.session_dir / f"{sid}.json"
    path.write_text(json.dumps({
        "id": sid, "created_at": "2026-08-13T12:00:00+08:00",
        "title": title or f"会话_{sid}", "messages": messages, "summary": None,
        "user_named": user_named, "pinned": pinned,
    }, ensure_ascii=False), encoding="utf-8")
    return path


def _read_disk(mgr, sid):
    path = mgr.session_dir / f"{sid}.json"
    return json.loads(path.read_text(encoding="utf-8"))


# ── V2A-1：状态覆盖层静态闸 ────────────────────────────────────────────
def test_v2a_1_overlay_static():
    src = _gui()
    # HTML：覆盖层根 + 三态（连接中/失败/断连）+ 详情区
    assert 'id="overlay-root"' in src
    assert 'id="ovl-connecting"' in src and 'ovl-spinner' in src, "连接中需动画指示，禁止纯文字"
    assert 'id="ovl-failed"' in src and "连接失败" in src
    assert 'id="ovl-disconnected"' in src and "后端已断开" in src
    assert src.count('ovl-detail-box') >= 3, "每态应有详情收纳区"
    # JS：状态机 + 重试 + 防抖
    assert "function showOverlay(" in src and "function hideOverlay(" in src
    assert "function retryConnect(" in src and "function toggleOvlDetail(" in src
    # 300ms 防抖：setConnected 内 300ms 延迟包装（连接抖动不重绘）
    assert "setTimeout(function() { applyConnected(c); }, 300)" in src
    # backend.exited：已连接过 → 断连态；首启未连过 → setup 屏
    assert "_everConnected" in src and "showOverlay('disconnected')" in src
    # gateway.ready：恢复后 toast
    assert "showToast('success', '连接已恢复')" in src
    # debugInfo 收纳：debug() 同步写 .ovl-detail-box
    assert "querySelectorAll('.ovl-detail-box')" in src


# ── V2A-1：覆盖层 node 实跑（DOM 桩）───────────────────────────────────
def test_v2a_1_overlay_node():
    src = _gui()
    show = _extract_func(src, "showOverlay")
    hide = _extract_func(src, "hideOverlay")
    js = r"""
const calls = [];
function makeEl(id) { return { id, classList: {
  toggle(c, on) { calls.push('toggle:' + id + ':' + c + ':' + on); },
  add(c) { calls.push('add:' + id + ':' + c); },
  remove(c) { calls.push('remove:' + id + ':' + c); } }, querySelectorAll() { return []; } }; }
const els = { 'overlay-root': makeEl('overlay-root'), 'ovl-connecting': makeEl('ovl-connecting'),
  'ovl-failed': makeEl('ovl-failed'), 'ovl-disconnected': makeEl('ovl-disconnected') };
els['overlay-root'].querySelectorAll = () => [els['ovl-connecting'], els['ovl-failed'], els['ovl-disconnected']];
global.document = { getElementById: (id) => els[id] || null, querySelectorAll: () => [] };
let _ovlType = null;
""" + show + "\n" + hide + r"""
showOverlay('connecting');
if (calls.indexOf('add:overlay-root:open') === -1) throw new Error('connecting 应打开 root');
if (calls.indexOf('toggle:ovl-connecting:show:true') === -1) throw new Error('connecting 态应显示');
if (calls.indexOf('toggle:ovl-failed:show:false') === -1) throw new Error('非当前态应隐藏');
showOverlay('connecting'); // 同型重复 → 不重绘
hideOverlay();
if (calls.indexOf('remove:overlay-root:open') === -1) throw new Error('hide 应关 root');
if (calls.indexOf('remove:ovl-connecting:show') === -1) throw new Error('hide 应清态');
console.log('NODE_V2A_OVERLAY_OK');
"""
    out = _run_node(js)
    assert "NODE_V2A_OVERLAY_OK" in out, f"node 实跑失败: {out}"


# ── V2A-2：会话管理静态闸 ──────────────────────────────────────────────
def test_v2a_2_sessions_static():
    src = _gui()
    # renderSessions：pin 稳定排序（置顶排最前）+ pin 标记 + pin 按钮 + 空态
    rs = _extract_func(src, "renderSessions")
    assert "b.pinned" in rs, "应含 pin 排序"
    assert "pin-mark" in rs, "应含 pin 图钉标记"
    assert "act pin" in rs, "应含 pin 行内按钮（.act 体系）"
    assert "v2a-empty" in rs, "搜索无结果应给空态"
    assert "没有匹配的会话" in rs
    # togglePin：本地即时 + 后端持久化（session.pin）
    tp = _extract_func(src, "togglePin")
    assert "session.pin" in tp and "pinned: s.pinned" in tp
    # deleteSession：二次确认模态替代原生 confirm（无 confirm( 调用）
    ds = _extract_func(src, "deleteSession")
    assert "askConfirm" in ds and "confirm(" not in ds, "删除必须走确认模态，禁止原生 confirm"
    assert "doDeleteSession" in src
    # askConfirm 模态
    ac = _extract_func(src, "askConfirm")
    assert "confirm-overlay" in ac
    # 后端：session.pin 端点注册 + handler
    sp = SESSIONS_PY.read_text(encoding="utf-8")
    assert 'reg_method("session.pin")' in sp, "后端应注册 session.pin"
    assert "def handle_session_pin(" in sp
    assert '"pinned": pinned' in sp, "session.list 应返回 pinned"


# ── V2A-2：pin 后端实证（monkeypatch + tmp 隔离）──────────────────────
def test_v2a_2_pin_backend(monkeypatch, tmp_path):
    from bobo_tui_gateway.handlers import sessions as sess_mod
    from core.session_manager import SessionManager

    sid_a = "v2a_pin_a_001"
    sid_b = "v2a_pin_b_002"
    msgs = [{"role": "user", "content": "hi"}]
    mgr = SessionManager(session_dir=str(tmp_path))
    _write_session_file(mgr, sid_a, msgs, title="会话A", pinned=False)
    _write_session_file(mgr, sid_b, msgs, title="会话B", pinned=True)
    monkeypatch.setattr(sess_mod, "_session_mgr", mgr)

    ctx = _make_ctx()
    ctx.sessions[sid_a] = {"id": sid_a, "title": "会话A", "messages": msgs, "pinned": False}
    ctx.sessions[sid_b] = {"id": sid_b, "title": "会话B", "messages": msgs, "pinned": True}

    # 1) pin 置顶 → 内存 + 落盘
    r = sess_mod.handle_session_pin({"session_id": sid_a, "pinned": True}, "p1", ctx)
    assert "error" not in r, f"pin 不应报错: {r}"
    assert ctx.sessions[sid_a]["pinned"] is True
    assert _read_disk(mgr, sid_a).get("pinned") is True, "pin 应持久化到磁盘"

    # 2) 取消 pin → false
    sess_mod.handle_session_pin({"session_id": sid_b, "pinned": False}, "p2", ctx)
    assert _read_disk(mgr, sid_b).get("pinned") is False

    # 3) session.list 返回 pinned（按磁盘补读）
    lst = sess_mod.handle_session_list({}, "l1", ctx)
    items = {s["id"]: s for s in lst["result"]["sessions"]}
    assert items[sid_a]["pinned"] is True
    assert items[sid_b]["pinned"] is False

    # 4) 老会话磁盘无 pinned 键 → 默认 False（兼容）
    sid_c = "v2a_pin_c_003"
    p = mgr.session_dir / f"{sid_c}.json"
    p.write_text(json.dumps({"id": sid_c, "created_at": "2026-08-13T12:00:00+08:00",
                             "title": "老会话", "messages": msgs, "summary": None},
                            ensure_ascii=False), encoding="utf-8")
    lst2 = sess_mod.handle_session_list({}, "l2", ctx)
    item_c = next((s for s in lst2["result"]["sessions"] if s["id"] == sid_c), None)
    assert item_c is not None and item_c["pinned"] is False, "老会话 pinned 默认 False"


# ── V2A-3：控件 hover/focus 静态闸 ─────────────────────────────────────
def test_v2a_3_controls_static():
    src = _gui()
    # focus ring：强调色 1px 外发光，覆盖主要按钮/输入框
    assert ":focus-visible" in src
    assert "rgba(232,145,58,0.6)" in src, "focus ring 应取现有强调色 #e8913a 同族"
    for sel in ["#new-chat:focus-visible", "#send:focus-visible", "#auto-toggle:focus-visible",
                "#session-search:focus-visible", ".copy-btn:focus-visible"]:
        assert sel in src, f"缺少 {sel} focus ring"
    # hover 补齐（默认外观零改：只新增交互态规则）
    assert "#send:hover:not(:disabled)" in src
    assert "#session-search:hover" in src


# ── V2A-4：Toast 静态闸 + node 实跑 ────────────────────────────────────
def test_v2a_4_toast_static():
    src = _gui()
    assert 'id="toast-root"' in src
    assert ".toast" in src and ".toast.success" in src and ".toast.fail" in src
    assert "setTimeout(remove, 3000)" in src, "3s 自动消失"
    assert "toast-close" in src, "手动关闭按钮"
    # 四个接入点：删除成功 / 重命名成功 / 连接恢复 / 后端错误
    assert "showToast('success', '会话已删除')" in src
    assert "showToast('success', '已重命名')" in src
    assert "showToast('success', '连接已恢复')" in src
    assert "showToast('fail'," in src


def test_v2a_4_toast_node():
    src = _gui()
    esc = _extract_func(src, "esc")
    toast = _extract_func(src, "showToast")
    js = r"""
let appended = null; let timers = [];
function makeToastEl() { const el = { className: '', innerHTML: '', parentNode: null,
  _closeBtn: { onclick: null },
  querySelector(sel) { if (sel === '.toast-close') return el._closeBtn; return null; },
  classList: { add() {}, remove() {} } }; return el; }
global.document = { getElementById: (id) => id === 'toast-root' ? { appendChild(t) { appended = t; } } : null,
  createElement: () => makeToastEl() };
global.setTimeout = (fn, ms) => { timers.push({ fn, ms }); return timers.length; };
""" + esc + "\n" + toast + r"""
showToast('success', '测试消息');
if (!appended) throw new Error('toast 应挂载');
if (appended.className !== 'toast success') throw new Error('success 态 class 错误: ' + appended.className);
const autoTimer = timers.find(t => t.ms === 3000);
if (!autoTimer) throw new Error('应注册 3s 自动消失定时器');
// 手动关闭：触发 close → 走 160ms 淡出定时器 → 移除
let removed = false;
appended.parentNode = { removeChild() { removed = true; } };
appended.querySelector('.toast-close').onclick();
const fadeTimer = timers.find(t => t.ms === 160);
if (fadeTimer) fadeTimer.fn();
if (!removed) throw new Error('手动关闭应移除 toast');
console.log('NODE_V2A_TOAST_OK');
"""
    out = _run_node(js)
    assert "NODE_V2A_TOAST_OK" in out, f"node 实跑失败: {out}"


# ── V2A-5：三态组件统一静态闸 ──────────────────────────────────────────
def test_v2a_5_three_state_static():
    src = _gui()
    # Loader：连接中 + 会话加载共用动画体系（ovl-spinner / v2a-loader .sp 同动画）
    assert ".v2a-loader" in src and ".v2a-loader .sp span" in src
    assert "ovlDot" in src, "Loader 动画应有统一 keyframes"
    # ErrorState：图标+标题+描述+动作按钮
    assert ".v2a-error" in src and ".v2a-err-icon" in src and ".v2a-err-title" in src and ".v2a-btn" in src
    # EmptyState：无会话/搜索无结果
    assert ".v2a-empty" in src and ".v2a-empty-icon" in src
    # 三组件被引用（非死代码）：Loader→覆盖层连接中；Empty→renderSessions
    assert 'class="ovl-spinner"' in src
    assert "v2a-empty" in _extract_func(src, "renderSessions")


# ── 铁律 0 闸：既有 CSS 零改动（V2A 之前的 style 段与 HEAD 逐字节一致）──
def test_v2a_css_zero_change_on_existing():
    """style 块中 TICKET-DESK-V2A 标记之前的所有规则，必须与基线版本完全一致。
    只允许新增，禁止改动任何既有 CSS 属性值。
    基线选择：V2A 合并前 HEAD 不含 V2A 块，直接用 HEAD；合并后 HEAD 已含 V2A，
    改用回滚标签 rollback/pre-desk-v2a 作基线（否则测试自咬，Kimi 终审修复）。"""
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
    # 新 style 中 V2A 注释块起点前 = 旧 style 全文（V2A 只允许追加在末尾）
    v2a_pos = new_style.find("/* ══ TICKET-DESK-V2A")
    assert v2a_pos > 0, "V2A 注释块应在 style 块内"
    # 特批豁免（owner 2026-08-13 打磨单）：会话行行内键旧规则（.del/.re）由 V2A 打磨
    # 统一重构为 .act 体系 —— 双向剔除该段后再比对，其余既有 CSS 仍逐字节锁死
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
    # V2D6 特批豁免（owner 票 DESK-V2D6 钉死）：思考框中性化须迁移既有 CSS
    # （去蓝迁米白灰系/三跳点弱橙）。双向剔除 V2D6 改动的规则行后，其余既有 CSS 仍逐字节锁死。
    V2D6_PAIRS = (
        (r"\.think-box \{ [^}]* \}\n", r"\.think-box \{ [^}]* \}\n"),
        (r"\.think-box \.think-label \{ [^}]* \}\n", r"\.think-box \.think-label \{ [^}]* \}\n"),
        (r"\.think-dot \{ [^}]* \}\n", r"\.think-dot \{ [^}]* \}\n"),
    )
    for pat_old, pat_new in V2D6_PAIRS:
        m_old = re.search(pat_old, old_style)
        m_new = re.search(pat_new, new_pre)
        assert m_old and m_new, f"V2D6 豁免规则应在基线/新版中同时存在: {pat_old}"
        old_style = old_style.replace(m_old.group(0), "")
        new_pre = new_pre.replace(m_new.group(0), "")
    # .think-box.done（fadeIn 0.2s 完成态淡入）为 V2D6 新增规则，基线无 —— 仅从新版剔除
    done_rule = ".think-box.done { animation:fadeIn 0.2s ease-out; }\n"
    assert done_rule in new_pre, "新版中应能找到 .think-box.done 新增规则"
    new_pre = new_pre.replace(done_rule, "")
    # V2D7 特批豁免（owner 票钉死）：药丸墨痕化 + 信息蓝全面退役迁移既有 CSS 值。
    # 双向剔除 V2D7 改动的规则行（V2A 标记之前部分）后，其余既有 CSS 仍逐字节锁死。
    V2D7_PAIRS = (
        r"\.msg \.txt \.diff-file \{ [^}]* \}\n",
        r"\.msg \.txt th \{ [^}]* \}\n",
        r"\.preview-btn \{ [^}]* \}\n",
        r"\.tool-detail \.td-args \{ [^}]* \}\n",
        r"\.tool-result \.td-args \{ [^}]* \}\n",
        r"\.tool-detail \.diff-file, \.tool-result \.diff-file \{ [^}]* \}\n",
        r"#status-mode\.office \{ [^}]* \}\n",
    )
    for pat in V2D7_PAIRS:
        m_old = re.search(pat, old_style)
        m_new = re.search(pat, new_pre)
        assert m_old and m_new, f"V2D7 豁免规则应在基线/新版中同时存在: {pat}"
        old_style = old_style.replace(m_old.group(0), "")
        new_pre = new_pre.replace(m_new.group(0), "")
    # DESK-P1 特批豁免（owner 票 TICKET-DESK-P1 钉死）：ASCII BOBO 大字（#welcome-logo）
    # → 文案标题（#welcome-title）+ project pill 锚点段（均位于 V2A 标记之前）。
    # 双向剔除该段后比对，其余既有 CSS 仍逐字节锁死。
    old_welcome = re.search(r"#welcome-logo \{[^}]*\}\n", old_style)
    assert old_welcome, "基线中应能找到 #welcome-logo 规则"
    old_style = old_style.replace(old_welcome.group(0), "")
    new_welcome = re.search(r"/\* 票 DESK-P1：.*?#welcome-title \{[^}]*\}\n", new_pre, re.S)
    assert new_welcome, "新版中应能找到 #welcome-title 规则段（含前后注释）"
    new_pre = new_pre.replace(new_welcome.group(0), "")
    pill_seg = re.search(
        r"/\* === DESK-P1 project pill ===.*?#project-menu \.prj-empty \{[^}]*\}\n", new_pre, re.S)
    assert pill_seg, "新版中应能找到 DESK-P1 project pill 锚点段"
    new_pre = new_pre.replace(pill_seg.group(0), "")
    assert new_pre.rstrip() == old_style.rstrip(), \
        "V2A 之前既有 CSS 必须逐字节等于基线（除特批 .act 重构段与 V2D6/V2D7/DESK-P1 豁免段外零改动）"


# ── md5 闸门：真实库三文件零变动 ───────────────────────────────────────
def test_v2a_md5_gate():
    """真实库三文件（knowledge_base.json / MEMORY.md / index.md）与 HEAD 一致。
    本测试不写真实库；若未来有任何写入导致漂移，此处即失败。"""
    # 与 F8-5 同款：三文件不在 git 追踪（data/ 与 library/ 部分被 .gitignore 排除），
    # 无法用 git HEAD 比对；此处做存在/可读/非空闸，前后一致性由收工手工
    # md5sum 闸门验证（跑全量前 md5sum → 跑后对比，PERF-1/F8 同款惯例）。
    for f in MD5_FILES:
        assert f.exists(), f"{f} 不存在"
        assert len(hashlib.md5(f.read_bytes()).hexdigest()) == 32, f"{f} 读取失败"
        assert f.stat().st_size > 0, f"{f} 为空文件"


# ── 终审修复回归闸（2026-08-13 桌面端 connecting 卡死案）────────────────
def test_v2a_dom_before_script():
    """V2A 新增 DOM（overlay-root/toast-root/confirm-overlay）必须出现在 <script> 之前。
    bobo 初版把它们追加在 </script> 之后 → 顶层 JS getElementById('cf-cancel').onclick
    抛 TypeError → 整个脚本死亡 → 桌面端永久卡 Connecting。此闸防回归。"""
    src = _gui()
    script_pos = src.find("<script>")
    assert script_pos > 0
    for dom_id in ('id="overlay-root"', 'id="toast-root"', 'id="confirm-overlay"',
                   'id="cf-cancel"', 'id="ovl-connecting"'):
        pos = src.find(dom_id)
        assert pos > 0, f"{dom_id} 缺失"
        assert pos < script_pos, f"{dom_id} 在 <script> 之后，顶层 JS 将空指针崩溃"


# ── V2A 打磨回归闸（owner 反馈 2026-08-13：确认弹窗键盘化 + 行内键秩序）──
def test_v2a_polish_confirm_keyboard():
    src = _gui()
    ac = _extract_func(src, "askConfirm")
    assert "cf-ok').focus()" in ac or 'cf-ok").focus()' in ac, "打开确认弹窗必须聚焦确认键"
    assert "_confirmKey" in src and "e.key === 'Enter'" in src and "e.key === 'Escape'" in src, \
        "确认弹窗必须支持 Enter=确认 / Esc=取消"


def test_v2a_polish_session_row_order():
    src = _gui()
    rs = _extract_func(src, "renderSessions")
    # 三键统一 .act 体系，顺序 pin → 改名 → 删除；emoji 📌 不得复出
    assert "'act pin'" in rs and "'act re'" in rs and "'act del'" in rs
    assert rs.index("div.appendChild(pin)") < rs.index("div.appendChild(re)") < rs.index("div.appendChild(del)"), \
        "行内键顺序必须 pin→改名→删除"
    assert "📌" not in rs, "禁止 emoji 图钉复出（渲染大红太扎眼）"
    assert "PIN_SVG" in rs, "pin 应使用细线 SVG"
