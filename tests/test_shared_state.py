"""并发共享状态修复测试：_file_checkpoints 实例隔离、_COMMAND_CACHE / _WORKER_RESULTS 锁。"""

import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestFileCheckpointsIsolation:
    """_file_checkpoints 必须是每个 Engine 实例独立，不能共享类级 dict。"""

    def _make_engine(self):
        from core.engine import Engine
        from core.tool_executor import execute_tool
        from tests.mock_llm import MockLLMCaller, text_response

        caller = MockLLMCaller([text_response("ok")])
        return Engine(caller, execute_tool, test_mode=True)

    def test_instances_do_not_share_checkpoints(self):
        e1 = self._make_engine()
        e2 = self._make_engine()
        e1._file_checkpoints["/tmp/a.py"] = "content-a"
        assert e2._file_checkpoints == {}
        assert e1._file_checkpoints is not e2._file_checkpoints

    def test_reset_only_clears_own_checkpoints(self):
        e1 = self._make_engine()
        e2 = self._make_engine()
        e1._file_checkpoints["/tmp/a.py"] = "content-a"
        e2._file_checkpoints["/tmp/b.py"] = "content-b"
        e1.reset()
        assert e1._file_checkpoints == {}
        assert e2._file_checkpoints == {"/tmp/b.py": "content-b"}

    def test_class_attribute_has_no_mutable_default(self):
        """ToolRunnerMixin 类上不应再有可变的 _file_checkpoints 默认值。"""
        from core.tool_runner import ToolRunnerMixin
        assert "_file_checkpoints" not in ToolRunnerMixin.__dict__ \
            or not isinstance(ToolRunnerMixin.__dict__["_file_checkpoints"], dict)


class TestSharedDictsLocked:
    """全局共享 dict 必须有锁保护读写。"""

    def test_command_cache_concurrent_access(self):
        """多线程并发读写 _COMMAND_CACHE 不抛异常、结果一致。"""
        from core.tool_executor import _COMMAND_CACHE, _COMMAND_CACHE_LOCK
        assert isinstance(_COMMAND_CACHE_LOCK, type(threading.Lock()))

        errors = []

        def writer(i):
            try:
                for j in range(200):
                    with _COMMAND_CACHE_LOCK:
                        _COMMAND_CACHE[("tool", f"{i}-{j}")] = (0.0, "x")
            except Exception as e:  # pragma: no cover
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        with _COMMAND_CACHE_LOCK:
            _COMMAND_CACHE.clear()

    def test_worker_results_lock_exists_and_works(self):
        from tools.spawn_worker import _WORKER_RESULTS, _WORKER_RESULTS_LOCK, execute_read_worker_result
        assert isinstance(_WORKER_RESULTS_LOCK, type(threading.Lock()))
        with _WORKER_RESULTS_LOCK:
            _WORKER_RESULTS["test_worker"] = "摘要内容"
        try:
            assert execute_read_worker_result("test_worker") == "摘要内容"
        finally:
            with _WORKER_RESULTS_LOCK:
                _WORKER_RESULTS.pop("test_worker", None)
