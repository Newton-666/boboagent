"""
core/skill_executor.py - Skill 执行器
"""

import yaml
import json
from pathlib import Path
from typing import Dict, List, Any

from core.tool_executor import execute_tool


class SkillExecutor:
    def __init__(self, skills_dir: str = "skills"):
        self.skills_dir = Path(skills_dir)
        self.skills_dir.mkdir(exist_ok=True)
    
    def save_from_recording(self, skill_name: str, messages: List[Dict], description: str = "") -> str:
        """从录制的对话保存 Skill"""
        if not messages:
            return "没有记录到任何对话"
        
        steps = []
        for msg in messages:
            role = msg.get('role')
            
            if role == 'user':
                steps.append({
                    "type": "user_input",
                    "content": msg.get('content', '')
                })
            elif role == 'assistant':
                # 记录 assistant 的回复
                steps.append({
                    "type": "assistant_output",
                    "content": msg.get('content', '')
                })
            elif role == 'tool_call':
                steps.append({
                    "type": "tool_call",
                    "tool": msg.get('name'),
                    "args": msg.get('args', {})
                })
            elif role == 'tool_result':
                steps.append({
                    "type": "tool_result",
                    "result": msg.get('result', '')
                })
        
        skill = {
            "name": skill_name,
            "description": description or f"从教学模式学习的 Skill，包含 {len(steps)} 个步骤",
            "steps": steps,
            "created_by": "teaching_mode"
        }
        
        filepath = self.skills_dir / f"{skill_name}.yaml"
        with open(filepath, 'w', encoding='utf-8') as f:
            yaml.dump(skill, f, allow_unicode=True, default_flow_style=False)
        
        return f"✅ Skill '{skill_name}' 已保存，包含 {len(steps)} 个步骤"
    
    def load_skill(self, skill_name: str) -> Dict:
        """加载 Skill"""
        filepath = self.skills_dir / f"{skill_name}.yaml"
        if not filepath.exists():
            return None
        with open(filepath, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    
    def execute_skill(self, skill: Dict, context: Dict = None) -> str:
        """执行 Skill"""
        if not skill:
            return "Skill 不存在"
        
        steps = skill.get('steps', [])
        results = []
        
        for step in steps:
            step_type = step.get('type')
            
            if step_type == 'tool_call':
                tool_name = step.get('tool')
                args = step.get('args', {})
                result = execute_tool(tool_name, args)
                results.append(f"[工具] {tool_name}: {result[:100] if result else '完成'}")
            
            elif step_type == 'user_input':
                results.append(f"[用户] {step.get('content', '')}")
            
            elif step_type == 'assistant_output':
                results.append(f"[Bobo] {step.get('content', '')}")
        
        return '\n'.join(results) if results else "Skill 执行完成"


# 单例
_skill_executor = None


def get_skill_executor():
    global _skill_executor
    if _skill_executor is None:
        _skill_executor = SkillExecutor()
    return _skill_executor
