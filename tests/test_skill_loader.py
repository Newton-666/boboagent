"""Tests for SkillLoader — 技能标准加载与列表。"""

import tempfile
import os
import pytest

from core.skill_loader import SkillLoader


@pytest.fixture
def empty_loader():
    """返回空 history 的 loader。"""
    return SkillLoader(get_history=lambda: [])


@pytest.fixture
def matching_loader():
    """返回含匹配触发词 history 的 loader。"""
    history = [{"role": "user", "content": "帮我修复这个 bug"}]
    return SkillLoader(get_history=lambda: history)


class TestLoadStandards:
    def test_load_standards_returns_list(self, empty_loader):
        result = empty_loader.load_standards()
        assert isinstance(result, list)

    def test_no_crash_with_no_history(self, empty_loader):
        result = empty_loader.load_standards()
        # 有或无标准目录都应返回 list 而不崩溃
        assert isinstance(result, list)

    def test_load_standards_with_matching_topic(self, matching_loader):
        result = matching_loader.load_standards()
        assert isinstance(result, list)
        # 如果 data/skill-standards/ 中有匹配 "bug" 关键词的标准，会返回
        # 即使没有，也不应崩溃


class TestListAvailable:
    def test_list_available_returns_string(self, empty_loader):
        result = empty_loader.list_available()
        assert isinstance(result, str)

    def test_list_available_not_crashing(self, empty_loader):
        result = empty_loader.list_available()
        # 无论是否有标准目录，都不崩溃
        assert isinstance(result, str)


class TestMissingDir:
    def test_handles_missing_skill_standards_dir(self):
        """即使 data/skill-standards/ 不存在也不崩溃。"""
        loader = SkillLoader(get_history=lambda: [])
        result = loader.load_standards()
        assert isinstance(result, list)
        result2 = loader.list_available()
        assert isinstance(result2, str)
