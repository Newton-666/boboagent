"""票 REASONING-ECHO 回归测试 — DeepSeek thinking 模式 reasoning_content 回传修复。

覆盖（验收 1/2/3 静态侧）：
- 构造"两个 user 之间夹工具轮"history（user → assistant(tool_calls, thinking=X)
  → tool → user），断言 build_messages 发送副本中该 assistant 消息带
  reasoning_content 且值与 thinking 相同；
- 断言 engine.history 原 dict 未被污染（仍只有 thinking，无 reasoning_content
  字段——GUI-F8 折叠框读取路径不受影响）；
- 断言无 thinking 的 assistant（纯文本）不补字段；
- 断言孤儿清洗路径（clean_orphan_tool_calls 返回新 list 后）同样补字段。

注：实弹验证（DeepSeek 是否接受 reasoning_content:""）结论见收工报告，
压缩路径定案同步在此测试。
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.context import clean_orphan_tool_calls
from core.injector import PromptInjector


class _MockEngine:
    """最小 Mock：仅承载 history + build_messages 需要的属性。"""

    class _Tracker:
        _change_log = []
        _read_files = {}

        def retroactive_mark(self):
            pass

    class _Proactive:
        def inject_context(self, messages):
            return messages

        def peek(self, *a, **k):
            return ""

    class _SkillLoader:
        def load_standards(self):
            return []

        def list_available(self):
            return ""

        def load(self, *a, **k):
            return None

    def __init__(self, history):
        self.history = history
        self.current_user_input = "当前轮问题"
        self._pending_diff = ""
        self._compressing = False
        self.tracker = self._Tracker()
        self.proactive = self._Proactive()
        self.skill_loader = self._SkillLoader()


def _build(history, user_input="当前轮问题"):
    """走真实 build_messages，返回 (发送副本, engine.history 原引用)。"""
    eng = _MockEngine(history)
    inj = PromptInjector(eng)
    msgs = inj.build_messages(
        system_prompt="You are Bobo.",
        user_input=user_input,
        tools_schema=[],
        extra_categories=set(),
        session_id="s-reasoning-echo",
    )
    return msgs, eng.history


def _tool_round_history():
    """两个 user 之间夹工具轮（触发结构，官方规则场景）。"""
    return [
        {"role": "user", "content": "第一轮：帮我改代码"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": "call_1", "type": "function",
                 "function": {"name": "read_file", "arguments": "{}"}},
            ],
            # 引擎落盘字段（GUI-F8 折叠框内部名，engine.py:1646）
            "thinking": "我先读文件确认现状",
        },
        {"role": "tool", "tool_call_id": "call_1", "name": "read_file",
         "content": "file content"},
        {"role": "user", "content": "第二轮：继续"},
    ]


# ── 验收 1：发送副本补 reasoning_content，值与 thinking 相同 ──────────

def test_echo_reasoning_content_on_send_copy():
    msgs, _ = _build(_tool_round_history())
    # 找带 tool_calls 的 assistant 消息
    tool_assistant = [m for m in msgs
                      if m.get("role") == "assistant" and m.get("tool_calls")]
    assert len(tool_assistant) == 1, "应恰有一条带 tool_calls 的 assistant"
    m = tool_assistant[0]
    assert m.get("reasoning_content") == "我先读文件确认现状", \
        "发送副本必须带 reasoning_content 且与 thinking 相同"


# ── 验收 2：engine.history 原 dict 零污染 ─────────────────────────────

def test_history_original_not_polluted():
    history = _tool_round_history()
    msgs, hist = _build(history)
    assert msgs is not history, "发送副本必须是新 list"
    tool_assistant = [m for m in msgs
                      if m.get("role") == "assistant" and m.get("tool_calls")][0]
    # 副本补了字段
    assert "reasoning_content" in tool_assistant
    # 原 history dict 无 reasoning_content（GUI-F8 读 thinking 不受影响）
    orig = [m for m in hist
            if m.get("role") == "assistant" and m.get("tool_calls")][0]
    assert "reasoning_content" not in orig, "engine.history 原 dict 零污染"
    assert orig.get("thinking") == "我先读文件确认现状", "原 dict 的 thinking 保留"


# ── 验收：无 thinking 的 assistant（纯文本）不补字段 ─────────────────

def test_no_thinking_assistant_not_echoed():
    history = [
        {"role": "user", "content": "第一轮"},
        {"role": "assistant", "content": "纯文本回答，无思考无工具"},
        {"role": "user", "content": "第二轮"},
    ]
    msgs, _ = _build(history)
    plain = [m for m in msgs
             if m.get("role") == "assistant" and not m.get("tool_calls")]
    assert len(plain) == 1
    assert "reasoning_content" not in plain[0], "无 thinking 的 assistant 不补字段"


# ── 验收：孤儿清洗路径（返回新 list）后同样补字段 ────────────────────

def test_echo_survives_orphan_clean():
    msgs, _ = _build(_tool_round_history())
    # 模拟 engine.py:1460 的 Layer 1 清洗（可能返回新 list）
    cleaned, report = clean_orphan_tool_calls(msgs)
    assert isinstance(cleaned, list)
    tool_assistant = [m for m in cleaned
                      if m.get("role") == "assistant" and m.get("tool_calls")]
    assert tool_assistant, "清洗后应仍有带 tool_calls 的 assistant"
    assert tool_assistant[0].get("reasoning_content") == "我先读文件确认现状", \
        "孤儿清洗返回新 list 后 reasoning_content 必须保留"


# ── 验收：tool_calls 轮 assistant 若 thinking 为空字符串 → 补空串 ────

def test_empty_thinking_echoed_as_empty_string():
    """压缩摘要消息结构：assistant 带 tool_calls 但无 thinking（归档剔除字段）。
    实弹定案（2026-08-20）：DeepSeek 拒绝 reasoning_content 空串（HTTP 400
    'reasoning_content must be passed back'），接受完全跳过（不带该字段）。
    此处锁定行为：thinking 空串 → 不补 reasoning_content 字段。"""
    history = [
        {"role": "user", "content": "第一轮"},
        {"role": "assistant", "content": None,
         "tool_calls": [{"id": "c1", "type": "function",
                         "function": {"name": "x", "arguments": "{}"}}],
         "thinking": ""},
        {"role": "tool", "tool_call_id": "c1", "name": "x", "content": "r"},
        {"role": "user", "content": "第二轮"},
    ]
    msgs, _ = _build(history)
    ta = [m for m in msgs
          if m.get("role") == "assistant" and m.get("tool_calls")][0]
    assert "reasoning_content" not in ta, "thinking 空串 → 跳过不补（实弹定案）"


# ── 验收：压缩摘要结构（带 tool_calls、无 thinking 字段）→ 跳过 ────

def test_compressed_summary_tool_calls_echoed_empty():
    """压缩归档剔除 thinking 字段（context.py 只保留 role/content/tool_calls
    等），摘要 assistant 带 tool_calls 但无 thinking → 跳过不补（2026-08-20
    实弹定案：空串 400、跳过被接受）。"""
    history = [
        {"role": "user", "content": "第一轮"},
        {"role": "assistant", "content": "（压缩摘要）前段完成工具调用",
         "tool_calls": [{"id": "c9", "type": "function",
                         "function": {"name": "y", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "c9", "name": "y", "content": "r"},
        {"role": "user", "content": "第二轮"},
    ]
    msgs, _ = _build(history)
    ta = [m for m in msgs
          if m.get("role") == "assistant" and m.get("tool_calls")][0]
    assert "thinking" not in ta, "摘要消息本无 thinking 字段"
    assert "reasoning_content" not in ta, "工具轮无 thinking → 跳过不补（实弹定案）"
