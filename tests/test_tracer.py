'''Tracer 单元测试'''

import time
from core.tracer import Tracer, get_tracer, trace


class TestTracer:
    '''Tracer 类核心功能'''

    def test_start_end_tracks_time(self):
        t = Tracer()
        t.start("step1")
        time.sleep(0.01)
        t.end("step1")
        assert len(t.steps) == 1
        assert t.steps[0]["name"] == "step1"
        assert t.steps[0]["start"] > 0
        assert t.steps[0]["end"] > t.steps[0]["start"]

    def test_end_without_name_closes_last(self):
        t = Tracer()
        t.start("a")
        t.start("b")
        t.end()  # closes 'b'
        assert t.steps[1]["end"] is not None
        # 'a' still open
        assert t.steps[0]["end"] is None

    def test_clear_empties_steps(self):
        t = Tracer()
        t.start("x")
        t.end("x")
        t.clear()
        assert t.steps == []

    def test_report_with_no_steps(self):
        t = Tracer()
        r = t.report()
        assert "没有追踪数据" in r

    def test_report_format(self):
        t = Tracer()
        t.start("alpha")
        time.sleep(0.005)
        t.end("alpha")
        r = t.report()
        assert "alpha" in r
        assert "总计:" in r
        assert "⏱" in r

    def test_disabled_start_does_nothing(self):
        t = Tracer()
        t.enabled = False
        t.start("ghost")
        assert t.steps == []

    def test_disabled_end_does_nothing(self):
        t = Tracer()
        t.enabled = False
        t.end()
        assert t.steps == []

    def test_start_end_large_timing(self):
        '''验证毫秒级以上的耗时被合理记录'''
        t = Tracer()
        t.start("slow")
        time.sleep(0.02)
        t.end("slow")
        elapsed = t.steps[0]["end"] - t.steps[0]["start"]
        assert elapsed >= 0.02


class TestGetTracer:
    '''get_tracer() 单例'''

    def test_returns_same_instance(self):
        a = get_tracer()
        b = get_tracer()
        assert a is b

    def test_instance_is_tracer(self):
        t = get_tracer()
        assert isinstance(t, Tracer)


class TestTraceDecorator:
    '''trace(name) 装饰器'''

    def test_trace_decorator_tracks(self):
        tracer = get_tracer()
        tracer.clear()

        @trace("my_func")
        def my_func():
            return 42

        result = my_func()
        assert result == 42
        # check that trace created a step
        names = [s["name"] for s in tracer.steps if s["name"] == "my_func"]
        assert len(names) >= 1

    def test_trace_decorator_error_still_closes(self):
        tracer = get_tracer()
        tracer.clear()

        @trace("failing")
        def fail():
            raise ValueError("oops")

        import pytest
        with pytest.raises(ValueError):
            fail()
        # step should still be closed
        closed = [s for s in tracer.steps if s["name"] == "failing" and s["end"] is not None]
        assert len(closed) >= 1
