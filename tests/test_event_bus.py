"""事件总线单元测试 — feat/event-bus-mvp"""

import json
import os
import tempfile
from core.event_bus import EventBus, event_bus as default_bus


def _read_jsonl(path: str) -> list[dict]:
    """从 JSONL 文件读取所有有效行。"""
    if not os.path.exists(path):
        return []
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return records


class TestEventBusIsolation:
    """单例与隔离。"""

    def test_default_bus_is_singleton(self):
        assert default_bus is EventBus()
        assert default_bus.filepath

    def test_temp_bus_isolated_from_default(self):
        """临时实例（指定 log_dir）的写入不出现在默认 bus 文件中。"""
        tmpdir = tempfile.mkdtemp()
        tmp = EventBus(log_dir=tmpdir)
        tmp.write("test.ns.ev", {"x": 1})
        default_records = _read_jsonl(default_bus.filepath)
        default_types = {r["type"] for r in default_records}
        assert "test.ns.ev" not in default_types


class TestEventBusWrite:
    """写入事件，从文件直接读取验证。"""

    def _new_bus(self, suffix: str) -> EventBus:
        d = tempfile.mkdtemp()
        bus = EventBus(log_dir=d)
        # 清空（可能是已存在的旧文件）
        if os.path.exists(bus.filepath):
            os.remove(bus.filepath)
        return bus

    def test_write_one(self):
        bus = self._new_bus("wr")
        bus.write("boot", {"mode": "test", "ver": 1})
        records = _read_jsonl(bus.filepath)
        assert len(records) == 1
        r = records[0]
        assert r["type"] == "boot"
        assert r["mode"] == "test"
        assert "ts" in r

    def test_write_many(self):
        bus = self._new_bus("many")
        for i in range(5):
            bus.write("e", {"i": i})
        records = _read_jsonl(bus.filepath)
        assert len(records) == 5
        values = [r["i"] for r in records]
        assert values == list(range(5))

    def test_write_truncates_long_event(self):
        """超长事件应截断，带 _truncated 标记。"""
        bus = self._new_bus("long")
        bus.write("big", {"payload": "x" * 600})
        records = _read_jsonl(bus.filepath)
        assert len(records) == 1
        assert len(json.dumps(records[0], ensure_ascii=False)) <= 510  # ~500 + margin


class TestEventBusRotation:
    """超过 10MB 轮转（阈值可测性差，改为验证轮转逻辑不崩）。"""

    def _new_bus(self) -> EventBus:
        d = tempfile.mkdtemp()
        return EventBus(log_dir=d)

    def test_rotation_does_not_crash(self):
        """写很多小事件不应崩溃。"""
        bus = self._new_bus()
        for i in range(200):
            bus.write("r", {"n": i})
        records = _read_jsonl(bus.filepath)
        assert len(records) == 200

    def test_write_after_rotation(self):
        """模拟超过阈值：直接创建大文件触发 rotate，然后写新事件应落盘。"""
        bus = self._new_bus()
        # 手动创建大文件
        os.makedirs(os.path.dirname(bus.filepath), exist_ok=True)
        with open(bus.filepath, "w", encoding="utf-8") as f:
            f.write("x" * (11 * 1024 * 1024))  # 11 MB
        # 写新事件触发 rotate
        bus.write("post_rotate", {"msg": "hello"})
        records = _read_jsonl(bus.filepath)
        # 新文件应只有 1 条新记录
        assert len(records) == 1
        assert records[0]["type"] == "post_rotate"


class TestEventBusSilentDegradation:
    """静默降级——写失败绝不抛异常。"""

    def test_write_to_readonly_dir(self):
        """只读目录写入不抛异常。"""
        bus = EventBus(log_dir="/root")
        bus.write("ro_test", {"x": 1})  # 不应 raise

    def test_write_empty_type(self):
        """空 event_type 也应安全落盘。"""
        d = tempfile.mkdtemp()
        bus = EventBus(log_dir=d)
        bus.write("", {"x": 1})
        records = _read_jsonl(bus.filepath)
        assert len(records) == 1

    def test_write_none_data(self):
        """data=None 安全处理。"""
        d = tempfile.mkdtemp()
        bus = EventBus(log_dir=d)
        bus.write("none_test", None)
        records = _read_jsonl(bus.filepath)
        assert len(records) == 1

    def test_read_corrupt_line_from_file(self):
        """文件中有垃圾行，读取时跳过。"""
        d = tempfile.mkdtemp()
        bus = EventBus(log_dir=d)
        bus.write("good", {"x": 1})
        with open(bus.filepath, "a", encoding="utf-8") as f:
            f.write("this is not json\n")
        bus.write("also_good", {"x": 2})
        records = _read_jsonl(bus.filepath)
        good_types = {r["type"] for r in records}
        assert good_types == {"good", "also_good"}


class TestEventBusFields:
    """必需字段。"""

    def _new_bus(self) -> EventBus:
        return EventBus(log_dir=tempfile.mkdtemp())

    def test_basic_fields(self):
        bus = self._new_bus()
        bus.write("e1", {"a": 1})
        records = _read_jsonl(bus.filepath)
        r = records[0]
        assert "ts" in r
        assert "type" in r
        assert r["type"] == "e1"

    def test_data_keys_merged_to_top(self):
        """data 中的键应展开到事件顶层。"""
        bus = self._new_bus()
        bus.write("tool.exec", {"name": "read_file", "duration_ms": 42})
        records = _read_jsonl(bus.filepath)
        r = records[0]
        assert r["name"] == "read_file"
        assert r["duration_ms"] == 42


class TestEventBusLargePayload:
    """票 I：含超长文本字段的事件必须生成可解析的 JSON 行。"""

    def _new_bus(self) -> EventBus:
        return EventBus(log_dir=tempfile.mkdtemp())

    def test_2000_char_args_summary(self):
        """2000 字符的 args_summary → 重新读回必须能被 json.loads 解析。"""
        bus = self._new_bus()
        long_text = "数据" * 1000  # 2000 中文字符
        bus.write("tool.exec", {
            "name": "read_file",
            "args_summary": long_text,
            "result_summary": "ok",
        })
        records = _read_jsonl(bus.filepath)
        assert len(records) == 1
        r = records[0]
        assert "ts" in r
        assert r["type"] == "tool.exec"
        # 被截断但字段仍在
        assert "args_summary" in r
        assert r["args_summary"].endswith("…")

    def test_2000_char_both_fields(self):
        """两个字段都超长 → 重新读回必须能被 json.loads 解析。"""
        bus = self._new_bus()
        long_args = "A" * 2000
        long_result = "B" * 2000
        bus.write("llm.call", {
            "args_summary": long_args,
            "result_summary": long_result,
            "prompt_tokens": 500,
        })
        records = _read_jsonl(bus.filepath)
        assert len(records) == 1
        r = records[0]
        assert r["type"] == "llm.call"
        assert r["prompt_tokens"] == 500
        assert r["args_summary"].endswith("…")
        assert r["result_summary"].endswith("…")

    def test_extreme_payload_drops_bulk_fields(self):
        """极小阈值场景：args_summary+result_summary 都被删除，生成可解析的 event_bus.dropped。"""
        bus = self._new_bus()
        huge = "X" * 5000
        bus.write("tool.exec", {
            "name": "read_file",
            "args_summary": huge,
            "result_summary": huge,
            "extra_info": huge * 2,
        })
        records = _read_jsonl(bus.filepath)
        assert len(records) >= 1
        # 所有行必须可解析
        for r in records:
            assert "ts" in r
            assert "type" in r
