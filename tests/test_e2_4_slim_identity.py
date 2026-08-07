"""Tests for TICKET-E2-④ — 瘦身份段：16 节 → 7 节行为回归。

验证 _build_system_prompt 身份段：
- 7 保留节标题齐全
- 9 退役节标题已移除
- 长度 ≤ 2.5K 字符（原 ~4.5K）
- 保留节关键措辞锚点未动（防误删行为内核）
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.engine import Engine
from core.tool_executor import execute_tool
from tests.mock_llm import MockLLMCaller, text_response

# 票 E2-④ 保留 7 节（措辞一字不动）
KEPT_SECTIONS = [
    "## 核心原则",
    "## 防循环规则（重要）",
    "## 对话规则",
    "## 收工汇报（重要）",
    "## 可信度",
    "## 命令安全",
    "## 输出格式",
]

# 票 E2-④ 退役 9 节
RETIRED_SECTIONS = [
    "## ⚡ 项目任务拆分（重要）",
    "## 工具结果标记",
    "## 记住指令",
    "## 用户资料",
    "## 技能",
    "## 工具并行",
    "## 会话记忆",
    "## 代码修改工作流（重要）",
    "## 工具使用",
]

# 保留节关键措辞锚点（防误删行为内核）
KEPT_ANCHORS = [
    "单独的纯文字回复 = 任务结束",
    "不要重复调用同一个工具读取同一个文件",
    "跟踪用户的原始目标",
    "最后一条回复必须是简短的收工汇报",
    "不要假装成功",
    "白名单命令",
    "不要使用 emoji",
]


@pytest.fixture(scope="module")
def system_prompt() -> str:
    caller = MockLLMCaller([text_response("ok")])
    engine = Engine(caller, execute_tool, test_mode=True)
    return engine.system_prompt


class TestSlimIdentity:
    def test_kept_sections_all_present(self, system_prompt):
        for sec in KEPT_SECTIONS:
            assert f"{sec}\n" in system_prompt, f"保留节缺失: {sec}"

    def test_retired_sections_all_absent(self, system_prompt):
        for sec in RETIRED_SECTIONS:
            assert f"{sec}\n" not in system_prompt, f"退役节残留: {sec}"

    def test_length_within_2500(self, system_prompt):
        assert len(system_prompt) <= 2500, f"身份段 {len(system_prompt)} 字符 > 2500"

    def test_kept_anchors_untouched(self, system_prompt):
        for anchor in KEPT_ANCHORS:
            assert anchor in system_prompt, f"保留节措辞锚点缺失: {anchor}"
