"""TICKET-LEDGER-400 专项测试 — L1 自动销账注入不破坏工具轮链。

根因（COST-7 实锤形态）：engine.py 原实现 self.history.append({"role":"system"})
把建议消息硬插在工具轮链中间（assistant(tool_calls)→tool→system→assistant），
DeepSeek thinking 模式要求该结构中间 assistant 带 reasoning_content 而 history
没有 → HTTP 400（bobo 施工时 run_tests 全绿反复触发）。

修复：改为 COST-6 动态块模式——追加到最后一个 user 消息 content。

覆盖：
- LEDGER-400-1：全绿信号 → 建议追加到最后一个 user 消息（非独立 system）
- LEDGER-400-2：消息结构合法——工具轮链中间无 system 消息（400 根因断言）
- LEDGER-400-3：无 user 消息兜底走 system（理论不可达分支）
"""

import re


def _apply_auto_suggest(history, tool_result_content, pending_cnt):
    """复刻 engine.py 修复后的注入逻辑（行为契约测试，与实现同步维护）。"""
    if not re.search(r"\d+\s+passed", tool_result_content) or \
            re.search(r"[1-9]\d*\s+failed", tool_result_content):
        return False
    suggest = (
        "💡 检测到测试全绿强完成信号（run_tests）。"
        f"台账仍有 {pending_cnt} 项 pending：若对应工作已由测试"
        "验证完成，请用 task_ledger update 标 done（带 evidence："
        "测试数字/文件路径）；否则忽略本条建议（模型可推翻）。"
    )
    for m in reversed(history):
        if m.get("role") == "user":
            m["content"] = (m.get("content") or "") + "\n\n" + suggest
            return True
    history.append({"role": "system", "content": suggest})
    return True


def _has_system_between_tool_rounds(history):
    """断言：工具轮链中间不存在 system 消息（400 根因结构）。"""
    prev = None
    for m in history:
        if prev == "tool" and m.get("role") == "system":
            return True
        prev = m.get("role")
    return False


def test_ledger400_1_appends_to_last_user():
    """全绿信号 → 建议追加到最后一个 user 消息（非独立 system）。"""
    history = [
        {"role": "user", "content": "开始施工"},
        {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "run_tests"}}]},
        {"role": "tool", "content": "2800 passed, 0 failed"},
        {"role": "assistant", "content": "继续"},
    ]
    ok = _apply_auto_suggest(history, "2800 passed, 0 failed", 3)
    assert ok
    # 建议在最后一个 user 消息里，且没有新增独立 system 消息
    assert "检测到测试全绿强完成信号" in history[0]["content"]
    roles = [m.get("role") for m in history]
    assert roles.count("system") == 0, f"不应有独立 system 消息: {roles}"


def test_ledger400_2_no_system_between_tool_rounds():
    """核心回归：工具轮链中间无 system（400 根因结构断言）。"""
    history = [
        {"role": "user", "content": "施工"},
        {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "run_tests"}}]},
        {"role": "tool", "content": "2812 passed"},
        {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "edit_file"}}]},
        {"role": "tool", "content": "ok"},
    ]
    _apply_auto_suggest(history, "2812 passed", 2)
    assert not _has_system_between_tool_rounds(history), \
        "工具轮链中间出现 system 消息 = 400 根因复现"


def test_ledger400_3_no_user_fallback_system():
    """无 user 消息时兜底独立 system（理论不可达分支不炸）。"""
    history = [
        {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "run_tests"}}]},
        {"role": "tool", "content": "100 passed"},
    ]
    ok = _apply_auto_suggest(history, "100 passed", 1)
    assert ok
    assert history[-1]["role"] == "system"
    assert "检测到测试全绿强完成信号" in history[-1]["content"]


def test_ledger400_4_non_green_no_inject():
    """非全绿（有 failed）不注入——原语义保持。"""
    history = [{"role": "user", "content": "施工"}]
    ok = _apply_auto_suggest(history, "5 passed, 1 failed", 2)
    assert not ok
    assert "检测到测试全绿" not in history[0]["content"]
