"""保存技能 - 把当前对话中的操作步骤保存为技能。

TICKET-E3a：重写为调用活系统 save_from_recording（写入 data/skill-standards/）。
旧实现调 extract_steps_from_history/create_skill_from_history（YAML 通路已退役，
方法不存在）→ 必崩 AttributeError。本文件为修复后版本。
"""

from core.skill_manager import get_skill_manager

TOOL_NAME = "save_skill"

# 全局引擎引用
_engine_ref = None


def set_engine(engine):
    global _engine_ref
    _engine_ref = engine


def _normalize_history(history: list) -> list:
    """把标准对话历史归一化为 save_from_recording 期望的消息结构。

    save_from_recording 识别顶层 role: user/assistant/tool_call。
    标准 history 中工具调用嵌套在 assistant.tool_calls 里 → 平铺提取。
    """
    out = []
    for msg in history:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        if role == "assistant" and msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                fn = tc.get("function", {})
                name = fn.get("name", "")
                args = fn.get("arguments", "")
                try:
                    import json

                    args = json.loads(args) if isinstance(args, str) else args
                except Exception:
                    args = {}
                out.append({"role": "tool_call", "name": name, "args": args})
            # 工具调用附带的文字内容也保留
            if msg.get("content"):
                out.append({"role": "assistant", "content": msg["content"]})
        else:
            out.append(msg)
    return out


def execute(skill_name: str, description: str = "") -> str:
    """保存当前会话中的操作步骤为技能"""
    if _engine_ref is None:
        return "❌ 无法获取对话历史"

    sm = get_skill_manager()
    history = _normalize_history(_engine_ref.history)
    if not history:
        return "❌ 没有找到可保存的对话记录"

    result = sm.save_from_recording(
        skill_name, history, description or "由 Bobo 学习生成"
    )

    return f"✅ 已保存技能: {skill_name}\n{result}"


TOOL_FUNC = execute
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "save_skill",
        "description": "【用途】将刚才执行的一系列操作保存为一个技能，下次可以直接调用。适用场景：用户说'把这些步骤保存成技能'、'记住这个流程'。",
        "parameters": {"type": "object", "properties": {"skill_name": {"type": "string", "description": "要保存的技能名称"}, "description": {"type": "string", "description": "技能的简要描述"}}, "required": ["skill_name"]}
    }
}


def register(reg):
    reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA)
