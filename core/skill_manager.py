"""
core/skill_manager.py - Skill 管理器
"""

import os
import json
import yaml
import re
from pathlib import Path
from typing import Dict, Any, List, Optional

from core.tool_executor import execute_tool


class SkillManager:
    def __init__(self, skills_dir: str = "skills"):
        self.skills_dir = Path(skills_dir)
        self.skills_dir.mkdir(exist_ok=True)
        self.skills = {}
        self._load_all_skills()
    
    def _load_all_skills(self):
        for yaml_file in self.skills_dir.glob("*.yaml"):
            try:
                with open(yaml_file, 'r', encoding='utf-8') as f:
                    skill = yaml.safe_load(f)
                    self.skills[skill.get('name')] = skill
            except:
                pass
    
    def get_skill(self, name: str) -> Optional[Dict]:
        return self.skills.get(name)
    
    def match_skill(self, user_input: str) -> Optional[Dict]:
        user_input_lower = user_input.lower()
        keywords = {
            "coding_master": ["写代码", "编写代码", "写程序", "编程", "开发", "写一个", "创建代码", "写个", "实现"],
        }
        for skill_name, kw_list in keywords.items():
            for kw in kw_list:
                if kw in user_input_lower:
                    return self.get_skill(skill_name)
        return None
    
    def extract_context(self, user_input: str, llm_caller) -> Dict:
        """用 LLM 从用户输入中提取上下文"""
        prompt = f"""从用户输入中提取以下信息，返回 JSON 格式：

用户输入: {user_input}

需要提取:
- file_path: 要创建的文件名（如 test.py, hello.js），如果没有则用 "code.py"
- code_content: 要写的代码内容

示例输出: {{"file_path": "calc.py", "code_content": "print(1+2)"}}

只输出 JSON，不要其他内容。"""

        try:
            response = llm_caller([{"role": "user", "content": prompt}], use_tools=False)
            if isinstance(response, dict) and 'choices' in response:
                content = response['choices'][0]['message']['content']
                # 提取 JSON
                json_match = re.search(r'\{.*\}', content, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group())
        except:
            pass
        
        # 默认值
        return {"file_path": "code.py", "code_content": ""}
    
    def execute_skill(self, skill: Dict, context: Dict, llm_caller=None) -> str:
        steps = skill.get('steps', [])
        result_summary = []
        
        for step in steps:
            step_name = step.get('name', '未知步骤')
            tool_name = step.get('tool')
            args = step.get('args', {})
            
            # 替换变量
            resolved_args = self._resolve_vars(args, context)
            
            if tool_name:
                result = execute_tool(tool_name, resolved_args)
                preview = result[:100] if result else "完成"
                result_summary.append(f"[{step_name}] {preview}")
                context['last_result'] = result
            elif step.get('action') == 'display':
                result_summary.append(f"[{step_name}] {step.get('description', '')}")
        
        return '\n'.join(result_summary)
    
    def _resolve_vars(self, value: Any, context: Dict) -> Any:
        if isinstance(value, str):
            for k, v in context.items():
                value = value.replace(f'{{{k}}}', str(v))
            return value
        elif isinstance(value, dict):
            return {k: self._resolve_vars(v, context) for k, v in value.items()}
        elif isinstance(value, list):
            return [self._resolve_vars(v, context) for v in value]
        return value
    
    def list_skills(self) -> List[str]:
        return list(self.skills.keys())


_skill_manager = None


def get_skill_manager():
    global _skill_manager
    if _skill_manager is None:
        _skill_manager = SkillManager()
    return _skill_manager
