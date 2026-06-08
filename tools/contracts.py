# contracts.py — 统一工具契约（单一数据源）

from typing import Dict, List

# ============================================================
# Agent 可用工具定义（单一数据源）
# ============================================================

AGENT_TOOLS: Dict[str, List[str]] = {
    "Researcher": ["web_search", "web_fetch", "web_scrape"],
    "Librarian": ["search_obsidian", "read_obsidian", "save_to_knowledge_base"],
    "Executor": ["write_obsidian", "append_obsidian", "run_command"],
    "Critic": ["evaluate", "cross_validate", "verify"],
    "PaperWriter": ["write_draft", "refine_sections"],
    "PaperReader": ["parse_pdf", "extract_citations"],
    "Boss": [],  # Boss 只做规划，不执行工具
}

# ============================================================
# 模糊匹配映射（处理 LLM 生成的近似工具名）
# ============================================================

FUZZY_ACTION_MATRIX: Dict[str, Dict[str, str]] = {
    "Librarian": {
        "summarize": "read_obsidian",
        "retrieve": "read_obsidian",
        "fetch_notes": "read_obsidian",
    },
    "Executor": {
        "read_obsidian_note": "write_obsidian",
        "get_note": "write_obsidian",
        "append_and_write_obsidian": "append_obsidian",  # 幻觉修复
        "write": "write_obsidian",                       # 通用写映射
        "save": "write_obsidian",                        # 保存映射
    },
    "PaperWriter": {
        "write_daily_summary": "write_draft",
        "create_report": "write_draft",
        "draft": "write_draft",
        "write": "write_draft",
    },
    "Researcher": {
        "deep_fetch": "web_scrape",
    },
}

# ============================================================
# 辅助函数
# ============================================================

def get_valid_actions(agent_name: str) -> List[str]:
    """获取指定 Agent 的可用工具列表"""
    return AGENT_TOOLS.get(agent_name, [])


def is_valid_action(agent_name: str, action: str) -> bool:
    """检查工具是否对该 Agent 有效"""
    return action in AGENT_TOOLS.get(agent_name, [])


def normalize_action(agent_name: str, action: str) -> str:
    """
    规范化动作名称：如果动作无效，尝试模糊匹配
    返回规范化后的动作名，如果无法匹配则返回原值
    """
    if is_valid_action(agent_name, action):
        return action
    
    # 尝试模糊匹配
    fuzzy_map = FUZZY_ACTION_MATRIX.get(agent_name, {})
    if action in fuzzy_map:
        return fuzzy_map[action]
    
    # 特殊处理：append 相关动作映射到 append_obsidian
    if agent_name == "Executor" and "append" in action.lower():
        return "append_obsidian"
    
    return action  # 无法匹配，返回原值


def get_all_agents() -> List[str]:
    """获取所有 Agent 名称"""
    return list(AGENT_TOOLS.keys())


def get_all_tools() -> List[str]:
    """获取所有工具名称"""
    all_tools = set()
    for tools in AGENT_TOOLS.values():
        all_tools.update(tools)
    return sorted(all_tools)


if __name__ == "__main__":
    print("=" * 60)
    print("测试 contracts.py")
    print("=" * 60)
    
    print("\n📋 Agent 工具定义:")
    for agent, tools in AGENT_TOOLS.items():
        print(f"   {agent}: {tools}")
    
    print("\n🔧 模糊匹配映射:")
    for agent, mapping in FUZZY_ACTION_MATRIX.items():
        for bad, good in mapping.items():
            print(f"   {agent}.{bad} → {good}")
    
    print("\n✅ 辅助函数测试:")
    print(f"   Executor 可用工具: {get_valid_actions('Executor')}")
    print(f"   is_valid_action('Executor', 'append_obsidian'): {is_valid_action('Executor', 'append_obsidian')}")
    print(f"   normalize_action('Executor', 'append_and_write_obsidian'): {normalize_action('Executor', 'append_and_write_obsidian')}")
    print(f"   normalize_action('Executor', 'write'): {normalize_action('Executor', 'write')}")
    
    print("\n✅ contracts.py 测试完成")


def register(reg):
    pass
