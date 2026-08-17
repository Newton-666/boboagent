"""票 DESK-P1 验收测试：欢迎屏文案 + Work with a project（项目文件夹模式）。

对应票据验收（专项部分）：
  1. 欢迎屏文案：ASCII BOBO 大字（pre#welcome-logo）摘除 → 'Let's finish up
     something today.'（Charter 700 30px，var(--font-reply) 零新增字体资源）
  2. 按钮渲染：#project-pill 存在（输入框下方左侧）
  3. 下拉交互：project-menu 结构（最近项目/Choose a folder/Clear project）
  4. IPC mock：preload 暴露 boboAPI.chooseFolder；main.cjs 有 openDirectory handler
  5. 无项目零注入：project_root=None 时注入段一字节都不出现
  6. 有项目注入且前缀稳定：注入段在尾部动态块，history 区逐字节不动
"""

import os
from pathlib import Path

from core.injector import PromptInjector

REPO = Path(__file__).resolve().parent.parent
INDEX = REPO / "apps" / "desktop" / "dist" / "index.html"
PRELOAD = REPO / "apps" / "desktop" / "electron" / "preload.cjs"
MAIN_CJS = REPO / "apps" / "desktop" / "electron" / "main.cjs"


class MockEngine:
    """最小 MockEngine：injector 所需属性 + DESK-P1 project_root。"""

    def __init__(self, project_root=None):
        self.history = [{"role": "user", "content": "hello world"}]
        self.current_user_input = "测试"
        self._pending_diff = ""
        self._compressing = False
        self._just_compressed = False
        self.tracker = type("T", (), {"_change_log": [], "_read_files": {}})()
        self.proactive = type(
            "P", (), {"inject_context": lambda self, msgs: msgs}
        )()
        self.skill_loader = type(
            "S", (), {"load_standards": lambda self, _r=None: []}
        )()
        self.project_root = project_root


def _build(engine):
    return PromptInjector(engine).build_messages(
        system_prompt="You are Bobo.",
        user_input="测试",
        tools_schema=[],
        extra_categories=set(),
        session_id="desk-p1-test",
    )


# ═══════════════════════════════════════════════════════════════════════
# ① 欢迎屏文案 + Charter 字体
# ═══════════════════════════════════════════════════════════════════════

class TestWelcomeCopy:

    def test_ascii_logo_removed(self):
        """金标准 1：ASCII BOBO 大字（pre#welcome-logo）已摘除。"""
        html = INDEX.read_text(encoding="utf-8")
        # 注释文本可提及 pre#welcome-logo（摘除说明），但元素 id 必须不存在
        assert 'id="welcome-logo"' not in html, "pre#welcome-logo 元素应已摘除"
        assert "████" not in html, "ASCII 大字不应残留"

    def test_title_present(self):
        """金标准 2：#welcome-title 存在且文案正确。"""
        html = INDEX.read_text(encoding="utf-8")
        assert 'id="welcome-title"' in html
        assert "Let's finish up something today." in html
        assert "你的个人 AI 助手" in html, "副标题小字保留"

    def test_title_uses_charter(self):
        """金标准 3：#welcome-title 用 var(--font-reply)（vendored Charter）700。"""
        css = INDEX.read_text(encoding="utf-8")
        # 从 CSS 段提取 #welcome-title 规则
        idx = css.find("#welcome-title")
        assert idx != -1, "#welcome-title CSS 规则应存在"
        seg = css[idx:idx + 300]
        assert "var(--font-reply)" in seg, "字体必须走 vendored Charter（var(--font-reply)）"
        assert "font-weight:700" in seg, "必须粗体 700"


# ═══════════════════════════════════════════════════════════════════════
# ② 按钮渲染 + 下拉交互
# ═══════════════════════════════════════════════════════════════════════

class TestProjectPill:

    def test_pill_button_rendered(self):
        """金标准 4：#project-pill 存在且默认文案正确。"""
        html = INDEX.read_text(encoding="utf-8")
        assert 'id="project-pill"' in html
        assert "Work with a project" in html

    def test_dropdown_structure(self):
        """金标准 5：下拉含最近项目区 / Choose a folder / Clear project。"""
        html = INDEX.read_text(encoding="utf-8")
        assert 'id="project-recents"' in html
        assert 'id="project-choose"' in html
        assert 'id="project-clear"' in html
        assert "Choose a folder" in html
        assert "Clear project" in html

    def test_js_interaction_present(self):
        """金标准 6：交互函数与状态变量存在。"""
        html = INDEX.read_text(encoding="utf-8")
        assert "currentProjectRoot" in html
        assert "function prjChooseFolder" in html
        assert "function prjClear" in html
        assert "boboRecentProjects" in html, "最近项目 localStorage 持久化"
        assert "localStorage" in html

    def test_prompt_submit_carries_project_root(self):
        """金标准 7：sendPrompt 有条件带 project_root（有值才带，null 兼容）。"""
        html = INDEX.read_text(encoding="utf-8")
        assert "project_root" in html
        assert "if (currentProjectRoot) submitParams.project_root = currentProjectRoot" in html


# ═══════════════════════════════════════════════════════════════════════
# ③ IPC mock
# ═══════════════════════════════════════════════════════════════════════

class TestIPC:

    def test_preload_exposes_choose_folder(self):
        """金标准 8：preload 暴露 boboAPI.chooseFolder（复用 select-folder IPC）。"""
        src = PRELOAD.read_text(encoding="utf-8")
        assert "chooseFolder" in src
        assert "selectFolder" in src

    def test_main_cjs_open_directory_handler(self):
        """金标准 9：main.cjs select-folder handler 用 openDirectory。"""
        src = MAIN_CJS.read_text(encoding="utf-8")
        assert "ipcMain.handle('select-folder'" in src
        assert "openDirectory" in src


# ═══════════════════════════════════════════════════════════════════════
# ④ 注入：无项目零注入 / 有项目注入且前缀稳定
# ═══════════════════════════════════════════════════════════════════════

class TestProjectRootInjection:

    def test_no_project_zero_injection(self):
        """金标准 10：project_root=None 时注入段零出现（缓存前缀稳定红线）。"""
        msgs = _build(MockEngine(project_root=None))
        joined = "\n".join(str(m.get("content", "")) for m in msgs)
        assert "当前项目根" not in joined, "无项目时一字节都不许多"

    def test_with_project_injected_in_tail(self):
        """金标准 11：有项目时注入'当前项目根'提示。"""
        msgs = _build(MockEngine(project_root="/tmp/demo-project"))
        joined = "\n".join(str(m.get("content", "")) for m in msgs)
        assert "当前项目根：/tmp/demo-project" in joined
        assert "所有文件操作/终端命令基于该目录" in joined

    def test_prefix_stable_with_project(self):
        """金标准 12：有项目 vs 无项目，history 区逐字节不动（注入段只在尾部动态块）。"""
        msgs_no = _build(MockEngine(project_root=None))
        msgs_yes = _build(MockEngine(project_root="/tmp/demo-project"))
        # 历史消息区（最后一条 user 之外）必须逐字节一致
        assert len(msgs_no) == len(msgs_yes)
        for i in range(len(msgs_no) - 1):
            assert msgs_no[i] == msgs_yes[i], f"history 区第 {i} 条被改动——前缀稳定红线"
        # 最后一条 user 含动态块：无项目不含 project_root 段，有项目含
        last_no = str(msgs_no[-1].get("content", ""))
        last_yes = str(msgs_yes[-1].get("content", ""))
        assert "当前项目根" not in last_no
        assert "当前项目根：/tmp/demo-project" in last_yes


# ═══════════════════════════════════════════════════════════════════════
# ⑤ gateway 落库：prompt.submit 带 project_root → 会话元数据
# ═══════════════════════════════════════════════════════════════════════

class TestGatewayPersist:

    def _fake_ctx(self):
        import threading
        class _Ctx:
            pass
        ctx = _Ctx()
        ctx.sessions = {}
        ctx.sessions_lock = threading.Lock()
        ctx.engine_cache = {}
        ctx.active_engine_threads = []
        ctx.engine_threads_lock = threading.Lock()
        ctx.pending_confirm = {}
        ctx.pending_confirm_result = {}
        ctx.confirm_lock = threading.Lock()
        ctx.auto_mode = {}
        ctx.current_engines = {}
        ctx.current_engines_lock = threading.Lock()
        ctx.session_usage = {}
        ctx.session_usage_lock = threading.Lock()
        ctx.save_session_to_disk = lambda sid, c: None
        # 预建会话
        sid = "desk-p1-gw-test"
        ctx.sessions[sid] = {"id": sid, "title": "t", "created_at": 1, "messages": []}
        return ctx, sid

    def test_prompt_submit_persists_project_root(self, monkeypatch):
        """金标准 13：prompt.submit 带 project_root → session 元数据落库（None 兼容）。"""
        import core.engine_adapter as ea
        import bobo_tui_gateway.handlers.prompts as prompts
        ctx, sid = self._fake_ctx()
        captured = {}
        # 不真跑 LLM：拦截 engine 线程入口（prompts.py 函数内局部导入 engine_adapter.run_engine）
        monkeypatch.setattr(
            ea, "run_engine",
            lambda *a, **k: captured.setdefault("args", a),
        )
        # 带 project_root：落库 + 规范化（去尾部斜杠）
        r1 = prompts.handle_prompt_submit(
            {"session_id": sid, "text": "你好", "project_root": "/tmp/demo-prj/"}, "r1", ctx)
        assert r1["result"]["ok"] is True
        assert ctx.sessions[sid]["project_root"] == "/tmp/demo-prj", "应去除尾部斜杠"
        # 不带 project_root：字段不落地（保持 None 兼容，不污染）
        sid2 = "desk-p1-gw-test2"
        ctx.sessions[sid2] = {"id": sid2, "title": "t", "created_at": 1, "messages": []}
        r2 = prompts.handle_prompt_submit(
            {"session_id": sid2, "text": "你好"}, "r2", ctx)
        assert r2["result"]["ok"] is True
        assert "project_root" not in ctx.sessions[sid2], "未下发 project_root 时不得落库"
