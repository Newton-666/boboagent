"""prompt_pool.py — 系统提示总池比例化配置。

票 LN-5：将系统提示各段（identity / memory / skills / note_pointers）
从硬编码 ceiling 改为基于模型 context window 的可配置总池 + 比例 ceiling。

设计约束：
- identity 段必须保持 conversation-stable，以 preserved prompt caching。
- 其他段按各自 ratio 计算 floor/ceiling，超限时在本段内独立淘汰/截断。
- 段与段之间不互相借用预算（no steal），避免单轮系统 prompt 内容抖动。
- 配置无效时静默降级到 LN-4 等价默认值，并写 notes.error 事件。
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Dict, Tuple

logger = logging.getLogger(__name__)

# LN-4 等价默认值：总池 5000 时，skill=800/1500, memory=1000/2500, note_pointers=300
DEFAULT_POOL_CHARS = 5000
DEFAULT_POOL_RATIO = 0.05  # context window 的 5%
POOL_MIN = 3000
POOL_MAX = 20000

# identity 最小保证：即使按比例算出来更小，也至少给这么多字符
IDENTITY_MIN_GUARANTEE = 800

# 各段占 总池 的比例（floor/ceiling）
# 5000 池时换算：skill=800/1500, memory=1000/2500, note_pointers=300
SECTION_RATIOS: Dict[str, Dict[str, float]] = {
    "skills": {"floor": 0.16, "ceiling": 0.30},
    "memory": {"floor": 0.20, "ceiling": 0.50},
    "note_pointers": {"ceiling": 0.06},
}


def _get_model_context_window() -> Tuple[int, str]:
    """尝试从当前 provider/model 配置读取 context window。

    返回 (context_window, source)，source 为 "provider" | "model" | "fallback"。
    """
    try:
        from core.provider import get_provider

        provider_name = os.environ.get("BOBO_PROVIDER", "openai").lower()
        model_name = os.environ.get("API_MODEL_NAME", "")
        provider = get_provider(provider_name)
        if not provider:
            return DEFAULT_POOL_CHARS, "fallback"

        # 优先用 model_context 中的模型特定窗口
        model_ctx = provider.get("model_context", {})
        if model_name and model_name in model_ctx:
            return int(model_ctx[model_name]), "model"

        # 否则用 provider 级 context_length
        ctx = provider.get("context_length")
        if ctx:
            return int(ctx), "provider"
    except Exception as e:
        logger.warning("读取模型 context window 失败: %s", e)

    return DEFAULT_POOL_CHARS, "fallback"


@dataclass(frozen=True)
class PromptPool:
    """系统提示总池配置。"""

    total: int = DEFAULT_POOL_CHARS
    source: str = "fallback"  # "override" | "ratio" | "fallback"
    ratios: Dict[str, Dict[str, float]] = field(default_factory=lambda: SECTION_RATIOS.copy())

    def section(self, name: str) -> Dict[str, int]:
        """返回某一段的 floor/ceiling。"""
        cfg = self.ratios.get(name, {})
        result: Dict[str, int] = {}
        if "floor" in cfg:
            result["floor"] = int(self.total * cfg["floor"])
        if "ceiling" in cfg:
            result["ceiling"] = int(self.total * cfg["ceiling"])
        return result

    def floor(self, name: str) -> int:
        return self.section(name).get("floor", 0)

    def ceiling(self, name: str) -> int:
        return self.section(name).get("ceiling", 0)

    @classmethod
    def from_env(cls) -> "PromptPool":
        """从环境变量读取配置，失败时降级到默认值并记录原因。"""
        raw_chars = os.environ.get("BOBO_PROMPT_POOL_CHARS", "")
        raw_ratio = os.environ.get("BOBO_PROMPT_POOL_RATIO", "")

        # 显式覆盖最高优先级
        if raw_chars:
            try:
                total = int(raw_chars)
                if POOL_MIN <= total <= POOL_MAX:
                    return cls(total=total, source="override")
                else:
                    cls._emit_config_error(
                        f"BOBO_PROMPT_POOL_CHARS out of range [{POOL_MIN}, {POOL_MAX}]: {total}"
                    )
                    return cls(total=DEFAULT_POOL_CHARS, source="fallback")
            except ValueError:
                cls._emit_config_error(f"BOBO_PROMPT_POOL_CHARS invalid: {raw_chars}")
                return cls(total=DEFAULT_POOL_CHARS, source="fallback")

        # 按 ratio × context window 计算
        ratio = DEFAULT_POOL_RATIO
        if raw_ratio:
            try:
                ratio = float(raw_ratio)
                if not 0 < ratio <= 1:
                    raise ValueError("ratio must be in (0, 1]")
            except ValueError as e:
                cls._emit_config_error(f"BOBO_PROMPT_POOL_RATIO invalid: {raw_ratio} ({e})")
                ratio = DEFAULT_POOL_RATIO

        ctx_window, source = _get_model_context_window()
        total = int(ctx_window * ratio)
        total = max(POOL_MIN, min(POOL_MAX, total))

        # 如果 source 是 fallback，pool_source 也记为 fallback
        if source == "fallback":
            return cls(total=total, source="fallback")
        return cls(total=total, source="ratio")

    @staticmethod
    def _emit_config_error(message: str) -> None:
        """静默写一条 notes.error 事件，不阻塞主流程。"""
        try:
            from core.event_bus import event_bus

            event_bus.write("notes.error", {"error": f"prompt_pool config: {message}"})
        except Exception:
            pass


# 模块级单例：启动时从环境变量加载一次，避免每轮重新解析
_prompt_pool: PromptPool | None = None


def get_prompt_pool() -> PromptPool:
    """返回全局 PromptPool 配置。"""
    global _prompt_pool
    if _prompt_pool is None:
        _prompt_pool = PromptPool.from_env()
    return _prompt_pool


def reset_prompt_pool() -> None:
    """测试/热重载用：清空缓存，下次调用重新读取环境变量。"""
    global _prompt_pool
    _prompt_pool = None
