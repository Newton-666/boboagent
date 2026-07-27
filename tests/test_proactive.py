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
        pm.stats["offered"] = 1  # 必须在 offered>0 时才会计数
        pm.track_engagement("yes, that's helpful")
        assert pm.stats["engaged"] == 1

    def test_track_engagement_noop_when_not_offered(self, pm):
        pm.track_engagement("hello")
        assert pm.stats["engaged"] == 0


class TestInjectContext:
    def test_inject_context_off_returns_original(self, pm):
        msgs = [{"role": "user", "content": "hello"}]
        result = pm.inject_context(msgs)
        assert result is msgs  # 原对象返回
        assert len(result) == 1

    def test_inject_context_off_offered_not_incremented(self, pm):
        pm.inject_context([{"role": "user", "content": "hello"}])
        assert pm.stats["offered"] == 0


class TestMaybeDowngrade:
    def test_downgrade_full_to_subtle(self, pm):
        pm.mode = "full"
        pm.stats = {"offered": 10, "engaged": 1}  # 参与率 10% < 20%
        result = pm._maybe_downgrade()
        assert pm.mode == "subtle"
        assert result is not None
        assert "ful" in result and "subtle" in result

    def test_no_downgrade_when_engaged_enough(self, pm):
        pm.mode = "full"
        pm.stats = {"offered": 10, "engaged": 5}  # 参与率 50% ≥ 20%
        result = pm._maybe_downgrade()
        assert pm.mode == "full"
        assert result is None

    def test_no_downgrade_below_threshold(self, pm):
        pm.mode = "full"
        pm.stats = {"offered": 3, "engaged": 0}  # offered<5 不触发
        result = pm._maybe_downgrade()
        assert pm.mode == "full"
        assert result is None
