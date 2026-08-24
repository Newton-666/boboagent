"""spawn_worker 测试：角色预设（explorer/coder）+ 回调事件可见（TICKET-DESK-WORKER-VISIBLE）。

回调事件断言喂的是引擎实际发射的键（name/args/tool_result），不是回调自造的键——
旧版测试按回调的（错误）键名喂数据，正是"worker 事件空名"bug 存活的原因。
"""
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


def _cb_capture():
    emitted = []
    sw._worker_event_emitter = lambda etype, sid, data: emitted.append((etype, data))
    return emitted


def test_callback_tool_call_uses_real_engine_keys():
    """回调读引擎实际发射的键（name/args，不是 tool_name/tool_args）；
    事件带 worker+role 标识，前端才能路由进该 worker 独立折叠卡。"""
    emitted = _cb_capture()
    cb = sw._make_worker_callback("explorer-1")
    cb("tool_call", {"name": "grep_code", "args": {"query": "config"}, "status": "start"})
    starts = [d for e, d in emitted if e == "tool.start"]
    assert starts, "工具调用应发 tool.start"
    assert starts[0]["name"] == "grep_code", "工具名应取引擎的 name 键"
    assert starts[0]["worker"] == "explorer-1", "事件应带 worker 标识"
    assert starts[0]["role"] == "explorer", "事件应带检测出的角色"
    assert starts[0]["tool_id"].startswith("w-explorer-1-"), "tool_id 应带 worker 前缀"
    assert starts[0]["context"] == "config", "context 应带参数预览"


def test_callback_tool_result_marks_done():
    """tool_result → tool.complete：前端据此把折叠卡内工具行 dot 转 done/fail。"""
    emitted = _cb_capture()
    cb = sw._make_worker_callback("coder")
    cb("tool_result", {"name": "edit_file", "args": {}, "duration": 2.5, "success": True})
    comps = [d for e, d in emitted if e == "tool.complete"]
    assert comps and comps[0]["name"] == "edit_file"
    assert comps[0]["worker"] == "coder" and comps[0]["role"] == "coder"
    assert comps[0]["duration"] == 2.5 and comps[0]["success"] is True
    assert comps[0]["tool_id"] == "w-coder-edit_file"


def test_callback_thinking_carries_worker():
    """thinking（阶段）事件带 worker/role 标识 + 阶段消息（前端头部实时阶段）。"""
    emitted = _cb_capture()
    cb = sw._make_worker_callback("explorer-1")
    cb("thinking", {"phase": "calling_llm", "message": "正在思考..."})
    thinks = [d for e, d in emitted if e == "thinking"]
    assert thinks and thinks[0]["worker"] == "explorer-1"
    assert thinks[0]["role"] == "explorer"
    assert thinks[0]["message"] == "正在思考..."


def test_callback_writes_event_bus_diag():
    """诊断落账：每次发事件都写 worker.event 到事件总线（排障"前端看不到 worker 调用"用）。"""
    import core.event_bus as eb
    emitted = []
    sw._worker_event_emitter = lambda etype, sid, data: emitted.append((etype, data))
    written = []
    orig = eb.event_bus

    class _FakeBus:
        def write(self, etype, data):
            written.append((etype, data))

    eb.event_bus = _FakeBus()
    try:
        cb = sw._make_worker_callback("explorer-1")
        cb("tool_call", {"name": "grep_code", "args": {"query": "x"}, "status": "start"})
        cb("thinking", {"phase": "calling_llm", "message": "正在思考..."})
    finally:
        eb.event_bus = orig
    starts = [d for e, d in written if e == "worker.event" and d.get("etype") == "tool.start"]
    assert starts, "tool_call 应落 worker.event 诊断账"
    assert starts[0]["worker"] == "explorer-1" and starts[0]["name"] == "grep_code"
    assert any(d.get("etype") == "thinking" for e, d in written), "thinking 也应落账"


def test_resolve_worker_card_meta():
    """主卡附加字段：worker 键与回调标识一致 + 检测角色（与回调输入同一字符串）。"""
    assert sw.resolve_worker_card_meta({"name": "explorer-1"}) == {
        "worker": "explorer-1", "worker_role": "explorer"}
    m = sw.resolve_worker_card_meta({"name": "修复这个 bug", "instruction": "随便"})
    assert m["worker"] == "修复这个 bug" and m["worker_role"] == "coder"
    m2 = sw.resolve_worker_card_meta({"name": "", "instruction": "调查这个模块的结构"})
    assert m2["worker"] == "调查这个模块的结构" and m2["worker_role"] == "explorer"
    assert sw.resolve_worker_card_meta({})["worker"] == "worker"
    assert sw.resolve_worker_card_meta(None)["worker"] == "worker"
    assert sw.resolve_worker_card_meta({"name": "随便一个任务"})["worker_role"] == ""
