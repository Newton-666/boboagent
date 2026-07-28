"""Tests for ProactiveManager — 主动模式配置/注入/参与度追踪。"""

import os
import pytest

from core.proactive import ProactiveManager


@pytest.fixture
def pm():
    return ProactiveManager()


class TestInitialState:
    def test_initial_mode_is_off(self, pm):
        assert pm.mode == "off"

    def test_initial_stats_zero(self, pm):
        assert pm.stats["offered"] == 0
        assert pm.stats["engaged"] == 0


class TestLoadConfig:
    def test_load_config_from_env_full(self, pm, monkeypatch):
        monkeypatch.setattr("config.BOBO_PROACTIVE_MODE", "full", raising=False)
        pm.load_config()
        assert pm.mode == "full"

    def test_load_config_from_env_subtle(self, pm, monkeypatch):
        monkeypatch.setattr("config.BOBO_PROACTIVE_MODE", "subtle", raising=False)
        pm.load_config()
        assert pm.mode == "subtle"


class TestTrackEngagement:
    def test_track_engagement_increments(self, pm):
        pm.stats["offered"] = 1
        pm.track_engagement("yes, that's helpful")
        assert pm.stats["engaged"] == 1

    def test_track_engagement_noop_when_not_offered(self, pm):
        pm.track_engagement("hello")
        assert pm.stats["engaged"] == 0


class TestInjectContext:
    def test_inject_context_off_returns_original(self, pm):
        msgs = [{"role": "user", "content": "hello"}]
        result = pm.inject_context(msgs)
        assert result is msgs
        assert len(result) == 1

    def test_inject_context_off_offered_not_incremented(self, pm):
        pm.inject_context([{"role": "user", "content": "hello"}])
        assert pm.stats["offered"] == 0


class TestTrackCitation:
    """track_citation 类型混淆回归测试（票 C）。"""

    def test_track_citation_with_mixed_types(self, pm, monkeypatch):
        """记忆列表中混入 str 时不 crash"""
        from unittest.mock import MagicMock
        monkeypatch.setattr(
            "tools.v5_memory.get_entries",
            lambda: [
                {"id": "1", "content": "重要发现"},
                "this is a raw string that should be skipped",
                {"id": "2", "content": "另一条记忆"},
            ],
        )
        monkeypatch.setattr("tools.v5_memory.bump_signal", MagicMock())

        pm._last_memory_ids = ["1"]
        pm.track_citation("根据重要发现，我们需要改进", ["1"])
        pm.track_citation("测试", ["999"])

    def test_track_citation_skips_str_memories(self, pm, monkeypatch):
        """str 被跳过，不影响 dict 记忆的匹配"""
        from unittest.mock import MagicMock
        bump = MagicMock()
        monkeypatch.setattr(
            "tools.v5_memory.get_entries",
            lambda: [
                {"id": "1", "content": "关键结论"},
                "raw string noise",
            ],
        )
        monkeypatch.setattr("tools.v5_memory.bump_signal", bump)

        pm._last_memory_ids = ["1"]
        pm.track_citation("关键结论是确定的", ["1"])
        bump.assert_called_once_with("1")


class TestMaybeDowngrade:
    def test_downgrade_full_to_subtle(self, pm):
        pm.mode = "full"
        pm.stats = {"offered": 10, "engaged": 1}
        result = pm._maybe_downgrade()
        assert pm.mode == "subtle"
        assert result is not None
        assert "ful" in result and "subtle" in result

    def test_no_downgrade_when_engaged_enough(self, pm):
        pm.mode = "full"
        pm.stats = {"offered": 10, "engaged": 5}
        result = pm._maybe_downgrade()
        assert pm.mode == "full"
        assert result is None

    def test_no_downgrade_below_threshold(self, pm):
        pm.mode = "full"
        pm.stats = {"offered": 3, "engaged": 0}
        result = pm._maybe_downgrade()
        assert pm.mode == "full"
        assert result is None
