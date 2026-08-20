"""TICKET-PROFILE-4 专项测试 — 设置页 Profile 入口（v1 骨架 + 空状态）。

覆盖（票验收）：
- F21-1 静态断言：Profile tab 存在（data-tab="profile"）、#page-profile 存在
  （当前用户模型区 + 更新历史区）
- F21-2 静态断言：gateway RPC 注册 —— server.py import profile 模块、
  profile.py register 注册 profile.get / profile.rollback
- F21-3 后端实跑：profile.rollback 恢复 USER.md 内容正确（构造快照 →
  回滚 → 断言 USER.md 分区行恢复 + knowledge_base 影子恢复 + 回滚记录追加）
- F21-4 node 桩实跑：renderProfileUserMd 分区渲染（含空分区"（暂无）"）
- F21-5 node 桩实跑：renderProfileHistory 渲染（空状态文案 + 有数据行含
  时间/徽标/diff/回滚按钮）
"""

import json
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
GUI_FILE = ROOT / "apps" / "desktop" / "dist" / "index.html"
SERVER_FILE = ROOT / "bobo_tui_gateway" / "server.py"
PROFILE_HANDLER = ROOT / "bobo_tui_gateway" / "handlers" / "profile.py"

# 模拟真实 USER.md（与 docs/USER.md 同构：手动初始条目 + （暂无）分区）
_USER_MD = (
    "# 用户模型（docs/USER.md）\n\n"
    "> 行为影响型画像。\n\n"
    "## 偏好\n"
    "- 代码评审意见的输出顺序：先讲风险，再讲优点。\n"
    "- 用户偏好直接执行工具调用，不说明、不道歉。\n\n"
    "## 禁忌\n"
    "（暂无）\n\n"
    "## 工作流\n"
    "- 直接调用工具建账，区分 done/pending，不解释不道歉。\n"
)


def _extract_func(src: str, fname: str) -> str:
    """按 { } 括号配对提取 function <fname> 完整源码（含 async 前缀）。"""
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
    r = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        raise AssertionError(f"node 执行失败: {r.stderr}")
    return r.stdout


# ── F21-1：静态断言（tab + 页面）───────────────────────────────────────

def test_f21_1_static_tab_and_page():
    src = GUI_FILE.read_text(encoding="utf-8")

    # Profile tab 存在
    m = re.search(r'<div class="settings-tab"\s+data-tab="profile">Profile</div>', src)
    assert m, "设置页缺 Profile tab（data-tab=\"profile\"）"

    # #page-profile 存在，含可编辑编辑器区 + 更新历史区（v2：白底 textarea + Save）
    assert 'id="page-profile"' in src, "缺 #page-profile 页面"
    assert 'id="profile-edit-area"' in src, "缺可编辑编辑器区（profile-edit-area）"
    assert 'id="profile-save-btn"' in src, "缺 Save 按钮（profile-save-btn）"
    assert 'id="profile-history"' in src, "缺更新历史区（profile-history）"
    # v2 历史着色：用户手动编辑 = 黄色高亮（src-user + profile-diff-user）
    assert "src-user" in src, "缺用户手动编辑行着色 class（src-user）"
    assert "profile-diff-user" in src, "缺用户手动编辑 diff 高亮 class（profile-diff-user）"
    # 空状态文案（v1 验收重点：jsonl 无数据时优雅空状态）。
    # 页面文案走 \u 转义（DESK-P2 金标准：index.html 非注释区零中文）→ 断言转义串
    assert "\\u6682\\u65e0\\u66f4\\u65b0\\u8bb0\\u5f55" in src, "缺更新历史空状态文案（\\u 转义）"
    assert "\\u5f53\\u524d\\u7528\\u6237\\u6a21\\u578b" in src, "缺当前用户模型标签（\\u 转义）"
    assert "\\uff08\\u53ef\\u7f16\\u8f91\\uff09" in src, "缺可编辑标签（\\u 转义）"

    # 回滚交互：确认弹窗 + profile.rollback 调用
    assert "profile.rollback" in src, "缺 profile.rollback 调用"
    assert "\\u56de\\u6eda\\u5230" in src, "缺回滚确认弹窗文案（\\u 转义）"


# ── F21-2：静态断言（gateway RPC 注册）─────────────────────────────────

def test_f21_2_static_rpc_registered():
    server_src = SERVER_FILE.read_text(encoding="utf-8")
    handler_src = PROFILE_HANDLER.read_text(encoding="utf-8")

    # server.py import 并注册 profile 模块
    assert "profile" in server_src, "server.py 未 import profile handler 模块"
    assert "memory, profile" in server_src, "server.py 注册循环缺 profile 模块"

    # profile.py 注册 profile.get / profile.rollback
    assert '"profile.get"' in handler_src, "profile.py 未注册 profile.get"
    assert '"profile.rollback"' in handler_src, "profile.py 未注册 profile.rollback"

    # 回滚复用 profile_writer._sync_user_md（对齐，不重写一套）
    assert "_sync_user_md" in handler_src, "profile.rollback 应复用 _sync_user_md"


# ── F21-3：后端实跑（profile.rollback 恢复 USER.md）────────────────────

def test_f21_3_rollback_restores_user_md(tmp_path, monkeypatch):
    from bobo_tui_gateway.handlers import profile as ph

    # 隔离数据文件：USER.md / jsonl / knowledge_base → tmp
    user_md = tmp_path / "USER.md"
    user_md.write_text(_USER_MD, encoding="utf-8")
    versions = tmp_path / "profile_versions.jsonl"
    kb = tmp_path / "knowledge_base.json"

    # 当前状态：偏好 = 新值（knowledge_base 影子 + USER.md 行）；快照 ts=111 记录旧值
    snapshot_ts = 111.0
    old_entry = "用户偏好直接执行工具调用，不说明、不道歉。"
    new_entry = "用户偏好轻量化设计。"
    versions.write_text(json.dumps({
        "ts": snapshot_ts, "category": "preference", "entry": old_entry,
        "diff": "+ " + old_entry, "reason": "behavioral", "signal_source": "user",
    }, ensure_ascii=False) + "\n", encoding="utf-8")
    kb.write_text(json.dumps({
        "entries": [],
        "profile": {"preference": {"value": new_entry, "updated": "2026-08-20T10:00:00"}},
    }, ensure_ascii=False), encoding="utf-8")
    # USER.md 偏好分区当前含 new_entry 行（模拟 PROFILE-2 写入后的状态）
    user_md.write_text(_USER_MD.replace(
        "- 用户偏好直接执行工具调用，不说明、不道歉。",
        "- " + new_entry,
    ), encoding="utf-8")

    # 重定向 profile.py 与 profile_writer 的路径常量（回滚复用 _sync_user_md）
    monkeypatch.setattr(ph, "_USER_MD_PATH", user_md)
    monkeypatch.setattr(ph, "_VERSIONS_FILE", versions)
    monkeypatch.setattr(ph, "_KB_PATH", kb)
    import core.profile_writer as pw
    monkeypatch.setattr(pw, "_USER_MD_PATH", user_md)
    monkeypatch.setattr(pw, "_VERSIONS_FILE", versions)
    monkeypatch.setattr(pw, "_KB_PATH", kb)

    r = ph.handle_profile_rollback({"ts": snapshot_ts}, "rid-1")
    assert r["id"] == "rid-1"
    assert "result" in r, f"回滚应成功: {r}"

    # USER.md 偏好分区恢复旧值行，新值行被替换
    md_text = user_md.read_text(encoding="utf-8")
    assert "- " + old_entry in md_text, "USER.md 应恢复快照 entry"
    assert "- " + new_entry not in md_text, "当前值行应被替换（不残留）"

    # knowledge_base 影子恢复
    kb_data = json.loads(kb.read_text(encoding="utf-8"))
    assert kb_data["profile"]["preference"]["value"] == old_entry

    # 回滚记录追加到 jsonl（现在 2 行：原快照 + rollback 记录）
    lines = [json.loads(ln) for ln in versions.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 2, "应追加 1 条回滚记录"
    assert lines[1]["reason"] == "rollback"
    assert lines[1]["category"] == "preference"
    assert lines[1]["entry"] == old_entry


def test_f21_3b_rollback_unknown_ts_returns_error(tmp_path, monkeypatch):
    from bobo_tui_gateway.handlers import profile as ph

    versions = tmp_path / "profile_versions.jsonl"
    versions.write_text(json.dumps({
        "ts": 111.0, "category": "preference", "entry": "x", "diff": "+ x",
    }) + "\n", encoding="utf-8")
    monkeypatch.setattr(ph, "_VERSIONS_FILE", versions)

    r = ph.handle_profile_rollback({"ts": 999.0}, "rid-2")
    assert "error" in r, "未知 ts 应返回 error"
    assert "未找到" in r["error"]["message"]


# ── F21-6：后端实跑（profile.save 用户手动编辑保存）────────────────────

def test_f21_6_save_user_edit(tmp_path, monkeypatch):
    from bobo_tui_gateway.handlers import profile as ph

    user_md = tmp_path / "USER.md"
    user_md.write_text(_USER_MD, encoding="utf-8")
    versions = tmp_path / "profile_versions.jsonl"
    kb = tmp_path / "knowledge_base.json"
    kb.write_text(json.dumps({"entries": [], "profile": {}}, ensure_ascii=False),
                  encoding="utf-8")

    monkeypatch.setattr(ph, "_USER_MD_PATH", user_md)
    monkeypatch.setattr(ph, "_VERSIONS_FILE", versions)
    monkeypatch.setattr(ph, "_KB_PATH", kb)
    import core.profile_writer as pw
    monkeypatch.setattr(pw, "_USER_MD_PATH", user_md)
    monkeypatch.setattr(pw, "_VERSIONS_FILE", versions)
    monkeypatch.setattr(pw, "_KB_PATH", kb)

    # 用户手动编辑：偏好分区加一条
    edited = _USER_MD.replace(
        "## 偏好\n- 代码评审意见的输出顺序：先讲风险，再讲优点。\n",
        "## 偏好\n- 代码评审意见的输出顺序：先讲风险，再讲优点。\n"
        "- 汇报时先给结论再给细节。\n",
    )
    r = ph.handle_profile_save({"user_md": edited}, "rid-3")
    assert r["id"] == "rid-3"
    assert "result" in r, f"保存应成功: {r}"

    # USER.md 已更新（含用户新增行）
    md_text = user_md.read_text(encoding="utf-8")
    assert "- 汇报时先给结论再给细节。" in md_text, "USER.md 应含用户新增条目"

    # 快照 signal_source=user_edit（黄色高亮的数据标记）
    lines = [json.loads(ln) for ln in versions.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 1, "应追加 1 条 user_edit 快照"
    assert lines[0]["signal_source"] == "user_edit", "手动保存应标记 user_edit"
    assert lines[0]["category"] == "user_edit"

    # knowledge_base 影子同步（新条目进 profile）
    kb_data = json.loads(kb.read_text(encoding="utf-8"))
    assert "汇报时先给结论再给细节" in kb_data["profile"]["preference"]["value"]


def test_f21_6b_save_empty_rejected(tmp_path, monkeypatch):
    from bobo_tui_gateway.handlers import profile as ph

    user_md = tmp_path / "USER.md"
    user_md.write_text(_USER_MD, encoding="utf-8")
    monkeypatch.setattr(ph, "_USER_MD_PATH", user_md)

    r = ph.handle_profile_save({"user_md": "   "}, "rid-4")
    assert "error" in r, "空 USER.md 应返回 error"
    assert "不能为空" in r["error"]["message"]


# ── F21-4：node 桩实跑（renderProfileUserMd 分区渲染）──────────────────

def test_f21_4_node_renders_user_md():
    src = GUI_FILE.read_text(encoding="utf-8")
    render = _extract_func(src, "renderProfileUserMd")
    js = r"""
var _els = {};
function getEl(id) {
  if (!_els[id]) _els[id] = { innerHTML: '', value: '', textContent: '' };
  return _els[id];
}
var document = { getElementById: getEl };
function esc(s) { return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
""" + render + r"""
var md = '# 用户模型\n\n## 偏好\n- 代码评审意见的输出顺序：先讲风险，再讲优点。\n\n## 禁忌\n（暂无）\n\n## 工作流\n- 直接调用工具建账。\n';
renderProfileUserMd(md);
var area = _els['profile-edit-area'];
console.log('NODE_F21_4 ' + JSON.stringify({ value: area.value, label: _els['profile-edit-label'].textContent }));
"""
    out = _run_node(js)
    m = re.search(r"NODE_F21_4 (\{.*\})", out)
    assert m, f"未输出 NODE_F21_4 标记: {out}"
    st = json.loads(m.group(1))
    value = st["value"]
    # v2：整个 USER.md 原文填入可编辑 textarea（用户可编辑）
    assert "## 偏好" in value and "## 禁忌" in value and "## 工作流" in value
    assert "- 代码评审意见的输出顺序：先讲风险，再讲优点。" in value
    # 标题带"可编辑"标记
    assert "可编辑" in st["label"]


# ── F21-5：node 桩实跑（renderProfileHistory 渲染）────────────────────

def test_f21_5_node_renders_history():
    src = GUI_FILE.read_text(encoding="utf-8")
    render = _extract_func(src, "renderProfileHistory")
    fmt = _extract_func(src, "fmtProfileTs")
    diff_html = _extract_func(src, "profileDiffHtml")
    js = r"""
var _els = {};
function getEl(id) {
  if (!_els[id]) _els[id] = { innerHTML: '', querySelectorAll: function() { return []; } };
  return _els[id];
}
var document = { getElementById: getEl };
function esc(s) { return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
""" + fmt + "\n" + diff_html + "\n" + render + r"""
// 空状态
renderProfileHistory([]);
var emptyHtml = _els['profile-history'].innerHTML;
// 有数据
renderProfileHistory([
  { ts: 1755651600, category: 'preference', entry: '用户偏好X', diff: '旧值 → 用户偏好X' },
  { ts: 1755651000, category: 'taboo', entry: '不要用 sudo', diff: '+ 不要用 sudo' }
]);
var html = _els['profile-history'].innerHTML;
console.log('NODE_F21_5 ' + JSON.stringify({ emptyHtml: emptyHtml, html: html }));
"""
    out = _run_node(js)
    m = re.search(r"NODE_F21_5 (\{.*\})", out)
    assert m, f"未输出 NODE_F21_5 标记: {out}"
    st = json.loads(m.group(1))

    # 空状态文案（v1 验收重点）
    assert "暂无更新记录" in st["emptyHtml"], "空状态缺指定文案"

    # 有数据：行 / 徽标 / diff 红绿 / 回滚按钮
    assert "profile-history-row" in st["html"]
    assert "preference" in st["html"] and "taboo" in st["html"]
    assert "profile-diff-add" in st["html"], "diff 应含 + 绿"
    assert "profile-diff-del" in st["html"], "diff 应含 - 红"
    assert "profile-rollback-btn" in st["html"], "每行应含回滚按钮"
    assert "data-ts=" in st["html"], "回滚按钮应带 data-ts"
