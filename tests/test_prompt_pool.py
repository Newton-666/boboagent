"""tests/test_prompt_pool.py — PromptPool 配置与降级测试。"""

import pytest

from core.prompt_pool import (
    DEFAULT_POOL_CHARS,
    DEFAULT_POOL_RATIO,
    IDENTITY_MIN_GUARANTEE,
    POOL_MAX,
    POOL_MIN,
    SECTION_RATIOS,
    PromptPool,
    get_prompt_pool,
    reset_prompt_pool,
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """每个测试前清理 PromptPool 相关环境变量，避免交叉污染。"""
    for key in ("BOBO_PROMPT_POOL_CHARS", "BOBO_PROMPT_POOL_RATIO", "BOBO_PROVIDER", "API_MODEL_NAME"):
        monkeypatch.delenv(key, raising=False)
    reset_prompt_pool()


def test_default_pool_equivalent_to_ln4():
    """金标准：默认 5000 池时，各段 floor/ceiling 与 LN-4 硬编码等价。"""
    pool = PromptPool(total=DEFAULT_POOL_CHARS, source="fallback")
    assert pool.floor("skills") == 800
    assert pool.ceiling("skills") == 1500
    assert pool.floor("memory") == 1000
    assert pool.ceiling("memory") == 2500
    assert pool.ceiling("note_pointers") == 300


def test_ratio_based_pool():
    """按模型窗口比例计算总池，并受上下限约束。"""
    pool = PromptPool(total=10000, source="ratio")
    assert pool.floor("skills") == 1600
    assert pool.ceiling("skills") == 3000
    assert pool.floor("memory") == 2000
    assert pool.ceiling("memory") == 5000
    assert pool.ceiling("note_pointers") == 600


def test_identity_guarantee():
    pool = PromptPool(total=1000, source="fallback")
    # identity 不纳入 ratio pool，但有最小保证
    assert pool.total == 1000


def test_from_env_override(monkeypatch):
    monkeypatch.setenv("BOBO_PROMPT_POOL_CHARS", "8000")
    monkeypatch.delenv("BOBO_PROMPT_POOL_RATIO", raising=False)
    reset_prompt_pool()
    pool = get_prompt_pool()
    assert pool.total == 8000
    assert pool.source == "override"


def test_from_env_ratio(monkeypatch):
    monkeypatch.delenv("BOBO_PROMPT_POOL_CHARS", raising=False)
    monkeypatch.setenv("BOBO_PROMPT_POOL_RATIO", "0.1")
    monkeypatch.setenv("BOBO_PROVIDER", "openai")
    reset_prompt_pool()
    pool = get_prompt_pool()
    # openai context_length=128000, ratio=0.1 → 12800, 受上限 20000 约束后仍为 12800
    assert pool.total == 12800
    assert pool.source == "ratio"


def test_from_env_ratio_clamped(monkeypatch):
    monkeypatch.delenv("BOBO_PROMPT_POOL_CHARS", raising=False)
    monkeypatch.setenv("BOBO_PROMPT_POOL_RATIO", "0.5")
    monkeypatch.setenv("BOBO_PROVIDER", "openai")
    reset_prompt_pool()
    pool = get_prompt_pool()
    # 128000 * 0.5 = 64000，应被压到上限 20000
    assert pool.total == POOL_MAX


def test_from_env_invalid_override_fallback(monkeypatch):
    monkeypatch.setenv("BOBO_PROMPT_POOL_CHARS", "not_a_number")
    monkeypatch.delenv("BOBO_PROMPT_POOL_RATIO", raising=False)
    reset_prompt_pool()
    pool = get_prompt_pool()
    assert pool.total == DEFAULT_POOL_CHARS
    assert pool.source == "fallback"


def test_from_env_out_of_range_fallback(monkeypatch):
    monkeypatch.setenv("BOBO_PROMPT_POOL_CHARS", "100000")
    monkeypatch.delenv("BOBO_PROMPT_POOL_RATIO", raising=False)
    reset_prompt_pool()
    pool = get_prompt_pool()
    assert pool.total == DEFAULT_POOL_CHARS
    assert pool.source == "fallback"


def test_from_env_invalid_ratio_fallback(monkeypatch):
    """ratio 无效时降级到默认 ratio，但仍按可读窗口计算（默认 provider openai）。"""
    monkeypatch.setenv("BOBO_PROMPT_POOL_RATIO", "2.0")
    reset_prompt_pool()
    pool = get_prompt_pool()
    # 默认 provider openai context_length=128000，默认 ratio 0.05 → 6400
    assert pool.total == 6400
    assert pool.source == "ratio"
