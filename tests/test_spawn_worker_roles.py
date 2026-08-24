"""spawn_worker 修复测试：角色预设（explorer/coder）+ 回调阶段事件可见。"""
import sys
import unittest.mock as um

import tools.spawn_worker as sw


def test_detect_role():
    assert sw._detect_role("explorer-1") == "explorer"
    assert sw._detect_role("研究员") == "explorer"
    assert sw._detect_role("coder") == "coder"
    assert sw._detect_role("修复代码") == "coder"
    assert sw._detect_role("随便一个任务") == ""


def test_explorer_prompt_has_no_modify():
    p = sw._build_worker_prompt("调查这个模块", "explorer-1")
    assert "只探索、不修改" in p, "explorer 应声明不修改"


def test_coder_prompt_has_implement():
    p = sw._build_worker_prompt("修复这个 bug", "coder")
    assert "动手实现" in p, "coder 应声明动手实现"


def test_generic_prompt_no_role_preset():
    p = sw._build_worker_prompt("随便做点什么", "")
    assert "只探索" not in p and "动手实现" not in p


def test_callback_emits_phase_and_tool():
    """回调：工具调用发 tool.start（标准工具卡 svg+名字）+ 状态/思考可见。"""
    emitted = []
    sw._worker_event_emitter = lambda etype, sid, data: emitted.append((etype, data))
    cb = sw._make_worker_callback("w1")
    cb("tool_call", {"tool_name": "grep_code", "tool_args": {"query": "config"}})
    cb("state.change", {"to": "EXECUTING"})
    cb("thinking", {"message": "我在看配置"})
    starts = [d for e, d in emitted if e == "tool.start"]
    assert starts and starts[0]["name"] == "grep_code", "工具调用应发 tool.start（svg+名字卡）"
    assert "Worker w1" in starts[0]["context"], "context 应标注 Worker 角色"
    assert any(e == "status.update" for e, _ in emitted), "阶段应可见"
    assert any(e == "thinking" for e, _ in emitted), "思考应可见"
