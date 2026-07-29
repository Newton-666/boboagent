"""票 L 热修回归：_engine 注入禁止污染调用方字典本体。

病根（2026-07-29 10:53 线上事故）：tool_runner/tool_executor 往 tool_args
字典本体内注入 _engine=Engine，该字典被下游 tool_result 通知引用 →
emit → json.dumps → TypeError: Object of type Engine is not JSON serializable。
每次调用 task_ledger 必炸 tool.complete 事件。
"""

import os
import sys

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _project_root)


class TestEngineInjectionNoPollution:
    """_engine 只能进副本，调用方字典本体必须保持 JSON 可序列化。"""

    def test_executor_does_not_mutate_caller_dict(self):
        import json
        from core.tool_executor import execute_tool

        args = {"action": "list"}
        execute_tool("task_ledger", args, engine=None)

        assert "_engine" not in args, (
            "execute_tool 污染了调用方字典：_engine 注入到了本体而非副本"
        )
        # 终极判官：调用方字典必须始终 JSON 可序列化
        json.dumps(args)

    def test_executor_routes_via_copy(self):
        """副本路径下台账工具仍正常执行（注入没被修坏）。"""
        from core.tool_executor import execute_tool

        args = {"action": "create", "items": [{"id": "t1", "title": "x", "status": "pending"}]}
        result = execute_tool("task_ledger", args, engine=None)
        assert "台账" in result or "ledger" in result.lower() or "✅" in result

    def test_tool_runner_submit_uses_copy(self):
        """静态检查：tool_runner 必须先 dict(tool_args) 再注入 _engine。"""
        import inspect
        import core.tool_runner as tr

        src = inspect.getsource(tr)
        inject_pos = src.find('exec_args["_engine"] = self')
        copy_pos = src.find("exec_args = dict(tool_args)")
        assert copy_pos != -1, "tool_runner 缺少 exec_args = dict(tool_args) 副本"
        assert copy_pos < inject_pos, "副本必须先于 _engine 注入"
        assert 'tool_args["_engine"] = self' not in src, (
            "禁止向 tool_args 本体注入 _engine"
        )
