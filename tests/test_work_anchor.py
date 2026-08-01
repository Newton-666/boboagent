"""TICKET-020 工作锚点金标准测试。

验证：
1. 压缩后 history 中存在 [工作锚点 消息
2. 锚点包含已写文件 + 当前任务
3. 锚点只有一份（重复压缩不堆积）
4. 二次压缩后锚点内容更新
5. 降级路径：无 change_log/无台账/无任务时锚点正常生成
"""

import os
import sys
import pytest

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _project_root)


# ── helpers ─────────────────────────────────────────────────────────

def _make_engine(compression_texts=None, test_mode=True):
    """创建一个装配好 MockLLM 的 Engine，压缩时会用 canned 回复。"""
    from tests.mock_llm import MockLLMCaller, text_response
    from core.tool_executor import execute_tool
    from core.engine import Engine
    texts = compression_texts or ["压缩摘要"]
    caller = MockLLMCaller([text_response(t) for t in texts] + [text_response("ok")])
    return Engine(caller, execute_tool, test_mode=test_mode)


def _fill_history(engine, n_pairs=40, prefix="输入", include_tools=False):
    """填充 engine.history，可选附带 write_file tool 调用记录。"""
    engine.history = []
    for i in range(n_pairs):
        engine.history.append({"role": "user", "content": f"{prefix} {i}"})
        if include_tools and i in (5, 15, 25):
            # 模拟 assistant 调用 write_file
            tc_id = f"call_{i}"
            engine.history.append({
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": tc_id,
                    "type": "function",
                    "function": {
                        "name": "file_operation",
                        "arguments": f'{{"action":"write","path":"test_{i}.py"}}'
                    }
                }]
            })
            engine.history.append({
                "role": "tool",
                "tool_call_id": tc_id,
                "name": "file_operation",
                "content": f"[RESULT: wrote test_{i}.py]"
            })
        else:
            engine.history.append({"role": "assistant", "content": f"回复 {i}"})


# ── fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def engine_with_files():
    """Engine 带 change_log + task_ledger + current_user_input。"""
    eng = _make_engine()
    # 模拟已写文件（通过 change_log）
    eng.tracker._change_log = [
        {"ts": 1000, "desc": "x.py: old → new"},
        {"ts": 1001, "desc": "y.py（write）"},
        {"ts": 1002, "desc": "z.md: a → b"},
    ]
    eng.task_ledger = [
        {"id": "1", "title": "修复 bug", "status": "in_progress"},
        {"id": "2", "title": "写测试", "status": "pending"},
        {"id": "3", "title": "部署上线", "status": "pending"},
    ]
    eng.current_user_input = "创建 skill：自动备份工作区"
    return eng


# ── 金标准测试 ──────────────────────────────────────────────────────

class TestWorkAnchorGolden:

    def test_anchor_after_compression(self, engine_with_files, monkeypatch):
        """金标准 1：触发压缩后 history 中存在 [工作锚点 消息。"""
        monkeypatch.setenv("BOBO_CONTEXT_BUDGET", "30")
        _fill_history(engine_with_files)
        engine_with_files.sid = "test-session-001"

        engine_with_files._compress_history()

        anchors = [m for m in engine_with_files.history
                   if m.get("role") == "system"
                   and m.get("content", "").startswith("[工作锚点")]
        assert len(anchors) >= 1, "压缩后应有工作锚点"

        content = anchors[0]["content"]
        assert "x.py" in content
        assert "y.py" in content
        assert "z.md" in content
        assert "创建 skill" in content
        assert "修复 bug" in content
        assert "写测试" in content

    def test_anchor_single_copy(self, engine_with_files, monkeypatch):
        """金标准 2：重复压缩不堆积锚点。"""
        monkeypatch.setenv("BOBO_CONTEXT_BUDGET", "30")
        _fill_history(engine_with_files)
        engine_with_files.sid = "test-session-002"

        engine_with_files._compress_history()
        # 第二次压缩（重新构建历史触发）
        _fill_history(engine_with_files, n_pairs=20, prefix="后续")
        engine_with_files._compress_history()

        anchors = [m for m in engine_with_files.history
                   if m.get("role") == "system"
                   and m.get("content", "").startswith("[工作锚点")]
        assert len(anchors) == 1, f"锚点应只有一份，实际 {len(anchors)}"

    def test_anchor_updates_on_recompress(self, engine_with_files, monkeypatch):
        """金标准 3：二次压缩后锚点内容更新。"""
        monkeypatch.setenv("BOBO_CONTEXT_BUDGET", "30")
        _fill_history(engine_with_files)
        engine_with_files.sid = "test-session-003"

        engine_with_files._compress_history()

        # 模拟又写了一个新文件
        engine_with_files.tracker._change_log.append(
            {"ts": 2000, "desc": "w.py（write）"}
        )
        engine_with_files.current_user_input = "给 w.py 加日志"

        _fill_history(engine_with_files, n_pairs=20, prefix="后续")
        engine_with_files._compress_history()

        anchors = [m for m in engine_with_files.history
                   if m.get("role") == "system"
                   and m.get("content", "").startswith("[工作锚点")]
        content = anchors[0]["content"]
        assert "w.py" in content, "新文件 w.py 应出现在锚点中"
        assert "给 w.py 加日志" in content, "新的当前任务应出现在锚点中"
        assert len(anchors) == 1

    def test_llm_summary_unaffected(self, engine_with_files, monkeypatch):
        """金标准 4：现有七段 LLM 摘要逻辑不受影响。"""
        monkeypatch.setenv("BOBO_CONTEXT_BUDGET", "30")
        _fill_history(engine_with_files)
        engine_with_files.sid = "test-session-004"

        engine_with_files._compress_history()

        # 压缩后应同时存在锚点和 LLM 摘要
        anchors = [m for m in engine_with_files.history
                   if m.get("role") == "system"
                   and m.get("content", "").startswith("[工作锚点")]
        summaries = [m for m in engine_with_files.history
                     if m.get("role") == "system"
                     and m.get("content", "").startswith("[对话历史摘要]")]
        assert anchors, "应有锚点"
        assert summaries, "应有 LLM 摘要"


# ── 降级路径测试 ────────────────────────────────────────────────────

class TestWorkAnchorDegradation:

    def test_no_change_log(self, monkeypatch):
        """无 change_log 时锚点正常生成（只有任务 + 台账）。"""
        eng = _make_engine()
        eng.tracker._change_log = []
        eng.task_ledger = [{"id": "1", "title": "唯一任务", "status": "pending"}]
        eng.current_user_input = "你好"
        monkeypatch.setenv("BOBO_CONTEXT_BUDGET", "30")
        _fill_history(eng)
        eng.sid = "test-degrade-001"

        eng._compress_history()

        anchors = [m for m in eng.history
                   if m.get("role") == "system"
                   and m.get("content", "").startswith("[工作锚点")]
        assert len(anchors) == 1
        content = anchors[0]["content"]
        assert "你好" in content
        assert "唯一任务" in content
        # 没有已写文件段
        assert "已写文件" not in content

    def test_no_task_ledger(self, monkeypatch):
        """无台账时锚点正常生成（只有任务 + 文件）。"""
        eng = _make_engine()
        eng.tracker._change_log = [{"ts": 1, "desc": "a.py（write）"}]
        eng.task_ledger = []
        eng.current_user_input = "写一个脚本"
        monkeypatch.setenv("BOBO_CONTEXT_BUDGET", "30")
        _fill_history(eng)
        eng.sid = "test-degrade-002"

        eng._compress_history()

        anchors = [m for m in eng.history
                   if m.get("role") == "system"
                   and m.get("content", "").startswith("[工作锚点")]
        content = anchors[0]["content"]
        assert "a.py" in content
        assert "写一个脚本" in content
        assert "台账" not in content

    def test_no_current_user_input(self, monkeypatch):
        """无 current_user_input 时锚点仍有文件 + 台账。"""
        eng = _make_engine()
        eng.tracker._change_log = [{"ts": 1, "desc": "b.md（write）"}]
        eng.task_ledger = [{"id": "1", "title": "任务", "status": "pending"}]
        eng.current_user_input = None
        monkeypatch.setenv("BOBO_CONTEXT_BUDGET", "30")
        _fill_history(eng)
        eng.sid = "test-degrade-003"

        eng._compress_history()

        anchors = [m for m in eng.history
                   if m.get("role") == "system"
                   and m.get("content", "").startswith("[工作锚点")]
        content = anchors[0]["content"]
        assert "b.md" in content
        assert "任务" in content
        assert "当前任务" not in content  # 无任务时不输出该行

    def test_completely_empty(self, monkeypatch):
        """完全无状态时锚点仍生成（只有标题行）。"""
        eng = _make_engine()
        eng.tracker._change_log = []
        eng.task_ledger = []
        eng.current_user_input = ""
        monkeypatch.setenv("BOBO_CONTEXT_BUDGET", "30")
        _fill_history(eng)
        eng.sid = "test-degrade-004"

        eng._compress_history()

        anchors = [m for m in eng.history
                   if m.get("role") == "system"
                   and m.get("content", "").startswith("[工作锚点")]
        assert len(anchors) == 1
        # 即使完全空，至少标题行存在
        content = anchors[0]["content"]
        assert "工作锚点" in content

    def test_anchor_survives_pure_tool_segment(self, monkeypatch):
        """金标准扩展：纯工具记录段（零摘要路径）也应有锚点。"""
        eng = _make_engine(["压缩摘要"])
        eng.tracker._change_log = [{"ts": 1, "desc": "x.py（write）"}]
        eng.task_ledger = [{"id": "1", "title": "修复", "status": "pending"}]
        eng.current_user_input = "修复"
        monkeypatch.setenv("BOBO_CONTEXT_BUDGET", "10")  # 极小预算确保压缩
        eng.sid = "test-pure-tool-001"

        # 纯工具消息（无 user/assistant 文本内容），触发零摘要路径
        eng.history = []
        for i in range(20):
            tc_id = f"call_{i}"
            eng.history.append({
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": tc_id,
                    "type": "function",
                    "function": {
                        "name": "grep_code",
                        "arguments": f'{{"pattern":"test{i}"}}'
                    }
                }]
            })
            eng.history.append({
                "role": "tool",
                "tool_call_id": tc_id,
                "name": "grep_code",
                "content": f"[RESULT: found test_{i}]"
            })

        eng._compress_history()

        anchors = [m for m in eng.history
                   if m.get("role") == "system"
                   and m.get("content", "").startswith("[工作锚点")]
        assert len(anchors) == 1, "纯工具记录段压缩后也应有锚点"
        content = anchors[0]["content"]
        assert "x.py" in content
        assert "修复" in content


# ── TICKET-025：锚点瑕疵补丁验收 ──────────────────────────────────────

class TestAnchorRobust:

    def test_colon_filename_preserved(self, monkeypatch):
        """验收 1：含冒号文件名（report_10:30.md）写入后锚点含完整路径。"""
        eng = _make_engine()
        # 模拟 file_operation write → 引擎同步入集
        eng._session_written_files = {"report_10:30.md", "data/config:backup.json"}
        eng.tracker._change_log = [
            {"ts": 1000, "desc": "report_10:30.md（write）", "path": "report_10:30.md"},
            {"ts": 1001, "desc": "data/config:backup.json: old → new", "path": "data/config:backup.json"},
        ]
        eng.task_ledger = [{"id": "1", "title": "冒号文件", "status": "in_progress"}]
        eng.current_user_input = "保存报告"
        monkeypatch.setenv("BOBO_CONTEXT_BUDGET", "30")
        _fill_history(eng)
        eng.sid = "test-colon-001"

        eng._compress_history()
        anchors = [m for m in eng.history
                   if m.get("role") == "system"
                   and m.get("content", "").startswith("[工作锚点")]
        assert len(anchors) == 1
        content = anchors[0]["content"]
        # 完整路径不被截断
        assert "report_10:30.md" in content
        assert "data/config:backup.json" in content
        # 不会被误截断为 "report_10"
        assert '"report_10"' not in content

    def test_session_files_survive_compress(self, monkeypatch):
        """验收 2：触发 compress_changelog 塌缩后，锚点仍含早期文件。"""
        eng = _make_engine()
        # 会话级集合——包含"早期"和"近期"文件
        eng._session_written_files = {"early_a.py", "early_b.md", "recent_x.py"}
        # change_log 触发塌缩（>20 条）
        eng.tracker._change_log = [
            {"ts": i, "desc": f"file_{i}.py（write）", "path": f"file_{i}.py"}
            for i in range(30)
        ]
        eng.task_ledger = [{"id": "1", "title": "塌缩后存活", "status": "in_progress"}]
        eng.current_user_input = "继续工作"
        monkeypatch.setenv("BOBO_CONTEXT_BUDGET", "30")
        _fill_history(eng)
        eng.sid = "test-survive-002"

        # 先触发 change_log 塌缩
        eng.tracker.compress_changelog()
        # 塌缩后 change_log 只剩最近 10 条 + 1 条历史摘要
        assert len(eng.tracker._change_log) <= 11

        eng._compress_history()
        anchors = [m for m in eng.history
                   if m.get("role") == "system"
                   and m.get("content", "").startswith("[工作锚点")]
        content = anchors[0]["content"]
        # 早期文件仍在（来自 _session_written_files，不受塌缩影响）
        assert "early_a.py" in content
        assert "early_b.md" in content
        assert "recent_x.py" in content

    def test_change_log_path_field_used(self, monkeypatch):
        """结构化 path 字段优先：即使 desc 含复杂冒号也可正确提取。"""
        eng = _make_engine()
        # 不设 _session_written_files，验证回退路径用 path 字段
        eng._session_written_files = set()  # falsy → 回退 change_log
        eng.tracker._change_log = [
            {"ts": 1000, "desc": "a:b:c（复杂描述）", "path": "a:b:c"},
            {"ts": 1001, "desc": "x.py: 旧→新", "path": "x.py"},
        ]
        eng.task_ledger = []
        eng.current_user_input = "测试 path 字段"
        monkeypatch.setenv("BOBO_CONTEXT_BUDGET", "30")
        _fill_history(eng)
        eng.sid = "test-path-003"

        eng._compress_history()
        anchors = [m for m in eng.history
                   if m.get("role") == "system"
                   and m.get("content", "").startswith("[工作锚点")]
        content = anchors[0]["content"]
        assert "a:b:c" in content
        assert "x.py" in content
