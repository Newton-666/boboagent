"""保存技能 - 把当前对话中的操作步骤保存为技能"""

from core.skill_manager import get_skill_manager

TOOL_NAME = "save_skill"

# 全局引擎引用
_engine_ref = None

def set_engine(engine):
    global _engine_ref
    _engine_ref = engine

def execute(skill_name: str, description: str = "") -> str:
    """保存当前会话中的操作步骤为技能"""
    if _engine_ref is None:
        return "❌ 无法获取对话历史"
    
    sm = get_skill_manager()
    steps = sm.extract_steps_from_history(_engine_ref.history)
    
    if not steps:
        return "❌ 没有找到可保存的操作步骤"
    
    result = sm.create_skill_from_history(skill_name, description or f"由 Bobo 学习生成", steps)
    
    return f"✅ 已学会新技能: {skill_name}\n📁 位置: {result['file']}\n📋 包含 {result['steps']} 个步骤"

TOOL_FUNC = execute
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "save_skill",
        "description": "【用途】将刚才执行的一系列操作保存为一个技能，下次可以直接调用。适用场景：用户说'把这些步骤保存成技能'、'记住这个流程'。",
        "parameters": {"type": "object", "properties": {"skill_name": {"type": "string"}, "description": {"type": "string"}}, "required": ["skill_name"]}
    }
}

def register(reg):
    reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA)
