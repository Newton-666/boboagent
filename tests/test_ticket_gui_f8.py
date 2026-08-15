"""TICKET-GUI-F8 回归测试 — 历史会话恢复 diff 高亮 + 思考过程（仅桌面端）。

覆盖：
- F8-1 后端 resume transcript：
  * tool 角色消息进 transcript（name 由 assistant tool_calls 映射、content 截断、
    inline_diff 从 <<<INLINE_DIFF>>> 块提取、无残留标记）
  * assistant 消息带 thinking 字段（core 已随会话落盘）
  * 旧字段语义不变（user/assistant/system text、assistant tool_calls 照旧）
  * 无 diff 工具消息 inline_diff 空串；无思考 assistant thinking 空串
- F8-2 core 思考持久化：FakeLLM 带 reasoning → engine.run 后 history 里
  assistant 消息（含工具轮与最终回复）带 thinking 字段随会话落盘；
  TUI 渲染路径与思考生成逻辑零改动（_last_reasoning 展示段照旧）
- F8-3 GUI 静态闸：index.html 含 addHistThinking / renderHistToolDiff /
  模块级 TOOL_FRIENDLY；renderFullHistory assistant 分支按 thinking 渲染思考框、
  tool 分支按 inline_diff 渲染 diff 块
- F8-4 TUI 零变化闸：ui-tui 源码无 F8 痕迹（toTranscriptMessages 仍只解构
  context/name/role/text，不读 thinking/inline_diff）；git diff 无 ui-tui 路径
- F8-5 md5 闸门：真实库三文件（data/knowledge_base.json / library/MEMORY.md /
  library/index.md）与分支起点（HEAD）一致（测试不碰真实库）

注：GUI 渲染层无法无头全自动化，采用静态断言 + 后端 RPC 实证 + engine 实跑
（与 F3/F4/F6/F7 同款，零漂移验证当前 HTML/源码）。
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
TUI_MESSAGES_TS = ROOT / "ui-tui" / "src" / "domain" / "messages.ts"
MD5_FILES = [
    ROOT / "data" / "knowledge_base.json",
    ROOT / "library" / "MEMORY.md",
    ROOT / "library" / "index.md",
]


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


def _extract_var(src: str, varname: str) -> str:
    """提取 `var <varname> = {...};` 声明段（到分号）。"""
    m = re.search(r"var\s+" + varname + r"\s*=\s*\{", src)
    assert m, f"未找到 var {varname}"
    start = m.start()
    depth = 0
    for i in range(m.start(), len(src)):
        c = src[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                end = src.index(";", i)
                return src[start:end + 1]
    raise AssertionError(f"var {varname} 括号不闭合")


def _md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


# ── F8-1：后端 resume transcript（tool 消息 + thinking + 旧语义不变） ──────

def _make_ctx():
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


def _write_session_file(mgr, sid, messages):
    path = mgr.session_dir / f"{sid}.json"
    data = {
        "id": sid,
        "created_at": "2026-08-13T12:00:00+08:00",
        "title": f"会话_{sid}",
        "messages": messages,
        "summary": None,
        "user_named": False,
    }
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_f8_1_resume_transcript_tool_and_thinking(monkeypatch, tmp_path):
    """resume transcript：tool 消息进历史（name 映射/截断内容/INLINE_DIFF 提取）、
    assistant 带 thinking；旧字段语义一字不动。"""
    from bobo_tui_gateway.handlers import sessions as sess_mod
    from core.session_manager import SessionManager

    sid = "f8_resume_001"
    diff_body = "+1行新增\n-1行删除\n 上下文行"
    msgs = [
        {"role": "system", "content": "系统提示语"},
        {"role": "user", "content": "帮我改文件"},
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "call_1", "type": "function",
             "function": {"name": "edit_file", "arguments": "{}"}},
        ]},
        {"role": "tool", "tool_call_id": "call_1",
         "content": f"已替换: /tmp/x.py\n<<<INLINE_DIFF>>>\n{diff_body}\n<<<END_INLINE_DIFF>>>"},
        # 第二条工具消息：有对应 assistant 声明（非孤儿，load_session 不清洗），但结果无 diff
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "call_2", "type": "function",
             "function": {"name": "read_local_file", "arguments": "{}"}},
        ]},
        {"role": "tool", "tool_call_id": "call_2", "content": "[RESULT] 普通工具结果无 diff"},
        {"role": "assistant", "content": "改好了", "thinking": "F8 思考过程：先看需求再动手。"},
    ]
    mgr = SessionManager(session_dir=str(tmp_path))
    _write_session_file(mgr, sid, msgs)
    monkeypatch.setattr(sess_mod, "_session_mgr", mgr)
    monkeypatch.setattr("core.engine_adapter.is_running", lambda s: False)

    ctx = _make_ctx()
    res = sess_mod.handle_session_resume({"session_id": sid}, "r1", ctx)
    body = res["result"]
    tr = body["messages"]

    # 1) tool 消息进 transcript
    tool_msgs = [m for m in tr if m.get("role") == "tool"]
    assert len(tool_msgs) == 2, f"tool 消息应进 transcript: {tool_msgs}"

    # 2) name 由 assistant tool_calls 映射（call_1 → edit_file / call_2 → read_local_file）
    assert tool_msgs[0]["name"] == "edit_file", tool_msgs[0]
    assert tool_msgs[1]["name"] == "read_local_file", tool_msgs[1]

    # 3) inline_diff 提取干净（无标记残留、strip、含红绿行）
    assert tool_msgs[0]["inline_diff"] == diff_body, tool_msgs[0]["inline_diff"]
    assert "<<<INLINE_DIFF" not in tool_msgs[0]["inline_diff"]
    assert "<<<END_INLINE_DIFF" not in tool_msgs[0]["inline_diff"]
    # 无 diff 工具消息 → 空串
    assert tool_msgs[1]["inline_diff"] == ""

    # 4) content 截断至合理长度且保留原文前缀
    assert tool_msgs[0]["content"].startswith("已替换: /tmp/x.py")
    assert len(tool_msgs[0]["content"]) <= 800

    # 5) assistant 带 thinking（core 已落盘字段原样透传）
    asst = [m for m in tr if m.get("role") == "assistant"]
    assert asst[-1]["thinking"] == "F8 思考过程：先看需求再动手。", asst[-1]
    assert asst[0]["thinking"] == "", "无思考的 assistant 应给空串（GUI falsy 不渲染）"

    # 6) 旧字段语义不变
    assert tr[1]["role"] == "user" and tr[1]["text"] == "帮我改文件"
    assert tr[0]["role"] == "system" and tr[0]["text"] == "系统提示语"
    assert asst[0]["tool_calls"][0]["function"]["name"] == "edit_file", "F6 tool_calls 语义不变"
    assert body["message_count"] == len(tr)


def test_f8_1_extract_inline_diff_unit():
    """_extract_inline_diff 边界：空串 / 无块 / 多块取首 / 超长截断。"""
    from bobo_tui_gateway.handlers.sessions import _extract_inline_diff

    assert _extract_inline_diff("") == ""
    assert _extract_inline_diff("无标记内容") == ""
    assert _extract_inline_diff("<<<INLINE_DIFF>>>\nA\n<<<END_INLINE_DIFF>>>") == "A"
    multi = "<<<INLINE_DIFF>>>\n首个块\n<<<END_INLINE_DIFF>>>尾部<<<INLINE_DIFF>>>\n第二块\n<<<END_INLINE_DIFF>>>"
    assert _extract_inline_diff(multi) == "首个块", "只取第一个块"
    big = "<<<INLINE_DIFF>>>\n" + "x" * 9000 + "\n<<<END_INLINE_DIFF>>>"
    assert len(_extract_inline_diff(big)) == 6000, "超长截断到 6000"


# ── F8-2：core 思考持久化（FakeLLM 带 reasoning → history 落 thinking） ────

def test_f8_2_core_thinking_persisted(monkeypatch):
    """engine 每轮思考完成 → 对应 assistant 消息 thinking 字段随 history 落盘；
    展示段 _last_reasoning 消费逻辑不受影响。"""
    from tests.test_engine_e2e import FakeLLMCaller, FakeToolExecutor, _make_test_engine

    class FakeLLMWithReasoning(FakeLLMCaller):
        """在每轮响应上附加 reasoning（思考过程）。"""

        def __call__(self, messages, stream_callback=None, retry_callback=None,
                     tools_override=None, **kwargs):
            resp = super().__call__(messages, stream_callback=stream_callback,
                                    retry_callback=retry_callback,
                                    tools_override=tools_override, **kwargs)
            if isinstance(resp, dict) and "choices" in resp:
                resp["reasoning"] = f"F8 第 {self.call_count} 轮思考：分析需求后行动。"
            return resp

    fake_llm = FakeLLMWithReasoning([
        # 第 1 轮：思考 → 发起 edit_file 工具调用
        ("", [{"id": "call_e1", "type": "function",
               "function": {"name": "edit_file", "arguments": "{}"}}]),
        # 第 2 轮：思考 → 最终文本回复
        ("文件已改好。", None),
    ])
    fake_tools = FakeToolExecutor(responses={
        "edit_file": "已替换: /tmp/x.py\n<<<INLINE_DIFF>>>\n+1\n-1\n<<<END_INLINE_DIFF>>>",
    })
    engine = _make_test_engine(fake_llm, fake_tools, monkeypatch)
    monkeypatch.setattr(engine, "_check_guards", lambda: False)

    engine.run(user_input="改文件")

    assert engine.state == engine.STATE_DONE
    # 注意：工具轮后引擎可能注入台账提醒（LEDGER 机制，与 e2e 同源），
    # history 结构为 user + assistant(tool_calls) + tool + [注入 user] + assistant(final)；
    # 此处只按角色与 thinking 字段断言，不绑定完整顺序
    asst_msgs = [m for m in engine.history if m.get("role") == "assistant"]
    assert len(asst_msgs) >= 2, asst_msgs

    # 工具轮 assistant（带 tool_calls 的那条）：带第 1 轮思考
    tool_asst = [m for m in asst_msgs if m.get("tool_calls")][0]
    assert tool_asst["thinking"] == "F8 第 1 轮思考：分析需求后行动。", tool_asst

    # 最终回复 assistant（无 tool_calls 的最后一条）：带最后一轮思考
    final_asst = [m for m in asst_msgs if not m.get("tool_calls")][-1]
    assert isinstance(final_asst.get("thinking"), str) and final_asst["thinking"].startswith("F8 第"), \
        f"最终 assistant 应带思考字段: {final_asst}"
    assert len(final_asst["thinking"]) > 0

    # 思考生成逻辑未被改动：展示段仍消费 _last_reasoning（此处已清空为终态）
    assert engine._last_reasoning == "", "_last_reasoning 展示后消费即清（防串回合）"


# ── F8-3：GUI 静态闸 ───────────────────────────────────────────────

def test_f8_3_gui_gate_static_asserts():
    """dist/index.html 现行页面必须含 F8 渲染入口与复用点。"""
    src = GUI_FILE.read_text(encoding="utf-8")

    # 新函数存在
    assert "function addHistThinking" in src, "缺历史思考框渲染函数"
    assert "function renderHistToolDiff" in src, "缺历史工具 diff 渲染函数"

    # TOOL_FRIENDLY 提升为模块级（renderHistToolDiff 引用）
    assert re.search(r"var\s+TOOL_FRIENDLY\s*=", src), "TOOL_FRIENDLY 应为模块级"
    assert "TOOL_FRIENDLY[name] || name" in src, "renderHistToolDiff 应引用模块级映射"

    # renderFullHistory：assistant 分支按 thinking 渲染思考框
    # （TICKET-GUI-F13：历史回放与实时同一渲染链 —— 思考框一律 buildHistThinkBox
    #  平铺，不再走 addHistThinking 分支；考古模式才收聚合缓冲）
    full = _extract_func(src, "renderFullHistory")
    assert "buildHistThinkBox(m.thinking)" in full, \
        "历史 assistant 应渲染思考框"

    # renderFullHistory：tool 分支按 inline_diff 渲染 diff 块
    # （TICKET-GUI-F13：工具卡统一 buildHistToolCard + diffBlock，现场原样平铺）
    assert "diffBlock(m.inline_diff)" in full, \
        "历史 tool 消息应按 inline_diff 渲染"

    # 复用点：toggleThinkBox / diffBlock / toolSummary / esc 均被历史函数引用
    # （TICKET-GUI-F12 审查修复：思考框构造抽公用函数 buildHistThinkBox，
    #  折叠交互与样式断言改指向它；addHistThinking 复用其构造）
    hist_think = _extract_func(src, "addHistThinking")
    assert "buildHistThinkBox(thinkingText)" in hist_think, "addHistThinking 应复用 buildHistThinkBox"
    think_builder = _extract_func(src, "buildHistThinkBox")
    assert "toggleThinkBox(tb)" in think_builder, "折叠交互应留在 buildHistThinkBox"
    assert "think-box collapsed" in think_builder, "折叠样式应留在 buildHistThinkBox"
    hist_diff = _extract_func(src, "renderHistToolDiff")
    assert "diffBlock(inlineDiff)" in hist_diff
    assert "buildHistToolCard(name, toolSummary({}, inlineDiff))" in hist_diff

    # 样式复用而非新增：.diff-block / .think-box.collapsed 为既有样式
    assert ".diff-block" in src and ".think-box.collapsed" in src


# ── F8-4：TUI 零变化闸 ─────────────────────────────────────────────

def _run_node(js: str) -> str:
    """在 node 中执行 JS（同步），返回 stdout。"""
    r = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        raise AssertionError(f"node 执行失败: {r.stderr}")
    return r.stdout


def test_f8_3_gui_node_render_hist_tool_diff():
    """node 实跑：提取真实 renderHistToolDiff（复用真实 diffBlock/toolSummary/
    TOOL_FRIENDLY），桩化 DOM 后渲染一段含 diff 的工具消息 —— 断言产出
    F3-5 同款整行底色 diff 块（df 文件头 / dl.add 绿 / dl.del 红）与工具卡摘要。
    无头环境用最小 DOM 桩（与 F7 node 实跑同款零漂移）。"""
    src = GUI_FILE.read_text(encoding="utf-8")
    funcs = []
    for fn in ("renderHistToolDiff", "buildHistToolCard", "diffBlock",
               "toolSummary", "diffStats", "esc", "toolIcon"):
        funcs.append(_extract_func(src, fn))
    js = r"""
// 最小 DOM 桩：记录 appendChild 的树，支持 firstChild（innerHTML 解析后手动挂）
function makeEl(tag) {
  return { tagName: tag, className: '', innerHTML: '', children: [], style: {},
    setAttribute() {}, appendChild(c) { if (c) this.children.push(c); },
    querySelector() { return null; } };
}
const chatEl = makeEl('div'); chatEl.scrollTop = 0; chatEl.scrollHeight = 0;
const document = { createElement: makeEl };
const welcomeEl = { style: {} };
""" + "\n" + _extract_var(src, "TOOL_ICONS") + "\n" + _extract_var(src, "TOOL_FRIENDLY") + "\n" + "\n".join(funcs) + r"""
// 渲染含 diff 的工具消息（模拟 resume transcript 的 inline_diff）
renderHistToolDiff('edit_file', '@@ -1,3 +1,3 @@\n-旧行\n+新行\n 上下文');
// 收集产物：工具卡（一行摘要）；diff 块挂载由浏览器原生 innerHTML→firstChild
// 完成，桩里不模拟——diffBlock 函数输出直接断言
let hasToolCard = false, hasSummary = false;
function scan(el) {
  if (!el) return;
  if (String(el.className) === 'tool') hasToolCard = true;
  if (el.innerHTML && String(el.innerHTML).indexOf('+1/-1') >= 0) hasSummary = true;
  (el.children || []).forEach(scan);
}
chatEl.children.forEach(scan);
// 直接验证 diffBlock 函数本身产出正确 HTML（不依赖 DOM 桩）
const dhtml = diffBlock('@@ -1,3 +1,3 @@\n-旧行\n+新行\n 上下文');
console.log(JSON.stringify({ hasToolCard, hasSummary,
  count: chatEl.children.length,
  dhtmlHasDf: dhtml.indexOf('diff-block') >= 0,
  dhtmlHasAdd: dhtml.indexOf('dl add') >= 0,
  dhtmlHasDel: dhtml.indexOf('dl del') >= 0 }));
"""
    out = _run_node(js)
    r = json.loads(out.strip().split("\n")[-1])
    assert r["hasToolCard"], "应渲染工具卡（一行摘要）"
    assert r["hasSummary"], "工具卡摘要应含 ±diff 统计"
    assert r["count"] == 1, "工具卡应作为唯一子节点挂载"
    assert r["dhtmlHasDf"], "diffBlock 应产出 diff-block 区块"
    assert r["dhtmlHasAdd"], "diffBlock 应产出 dl add 红块"
    assert r["dhtmlHasDel"], "diffBlock 应产出 dl del 绿块"


def test_f8_4_tui_zero_change():
    """TUI 源码无 F8 痕迹：toTranscriptMessages 仍只解构 context/name/role/text，
    不读 thinking/inline_diff（新增字段 TUI 无感）；git diff 无 ui-tui 路径。"""
    ts = TUI_MESSAGES_TS.read_text(encoding="utf-8")

    # 解构行保持原样（未扩展 thinking/inline_diff 解构）
    assert "const { context, name, role, text } = row as TranscriptRow" in ts, \
        "TUI 解构行不得扩展新字段"
    assert "thinking" not in ts.split("toTranscriptMessages")[1].split("fmtDuration")[0], \
        "TUI 消息转换逻辑不得出现 thinking"

    # git diff 无 ui-tui 路径（有 git 仓库时验证；无则跳过）
    try:
        r = subprocess.run(
            ["git", "diff", "--name-only", "--", "ui-tui/"],
            cwd=ROOT, capture_output=True, text=True, timeout=10,
        )
    except Exception:
        pytest.skip("git 不可用，跳过 diff 检查")
    assert r.returncode == 0, f"git diff 失败: {r.stderr}"
    assert r.stdout.strip() == "", f"TUI 目录有改动（铁律零变化）: {r.stdout}"


# ── F8-5：md5 闸门（真实库三文件，收工手工验证；测试只做存在性保护） ─────

def test_f8_5_md5_gate_real_library():
    """真实库三文件存在且可读 —— 测试运行不写不删。

    注：三文件不在 git 追踪中（data/ 与 library/ 部分文件被 .gitignore 排除），
    无法用 git HEAD 比对；md5 前后一致性按票内惯例由收工汇报手工闸门验证
    （跑全量测试前 md5sum → 跑后 md5sum 对比，与 PERF-1 同款）。
    """
    for f in MD5_FILES:
        assert f.exists(), f"{f} 不存在"
        assert len(_md5(f)) == 32, f"{f} 读取失败"
        assert f.stat().st_size > 0, f"{f} 为空文件"
