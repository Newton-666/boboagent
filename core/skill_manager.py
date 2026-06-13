"""Skill 管理器 — 加载、执行技能。技能作为动态工具暴露给 LLM。"""

import json
import yaml
from pathlib import Path
from typing import Optional


class SkillManager:
    def __init__(self, skills_dir: str = "skills"):
        self.skills_dir = Path(skills_dir)
        self.skills_dir.mkdir(exist_ok=True)
        self._skills: dict = {}
        self._load_all()

    def _load_all(self):
        self._skills = {}
        for f in self.skills_dir.glob("*.yaml"):
            try:
                with open(f, encoding="utf-8") as fp:
                    skill = yaml.safe_load(fp)
                if skill and skill.get("name"):
                    self._skills[skill["name"]] = skill
            except Exception:
                pass
        # Also load from index.json for backward compatibility
        idx = self.skills_dir / "index.json"
        if idx.exists():
            try:
                with open(idx, encoding="utf-8") as fp:
                    for entry in json.load(fp).get("skills", []):
                        name = entry["name"]
                        if name not in self._skills:
                            self._skills[name] = {
                                "name": name,
                                "description": entry.get("description", ""),
                                "steps": [],
                            }
            except Exception:
                pass

    def list_skills(self):
        return list(self._skills.keys())

    def get_skill(self, name: str) -> Optional[dict]:
        return self._skills.get(name)

    def get_skill_tools(self) -> list:
        """Return tool definitions for all skills (for dynamic registration)."""
        tools = []
        for name, skill in self._skills.items():
            desc = skill.get("description", f"Skill: {name}")
            tools.append({
                "type": "function",
                "function": {
                    "name": f"run_skill:{name}",
                    "description": desc,
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": [],
                    },
                },
            })
        return tools

    def execute_skill(self, skill: dict, context: dict = None) -> str:
        """Execute a skill's steps. Returns a summary string."""
        from core.tool_executor import execute_tool

        steps = skill.get("steps", [])
        results = []
        context = context or {}

        for step in steps:
            step_type = step.get("type") or step.get("action", "tool_call")

            if step_type == "tool_call":
                tool_name = step.get("tool") or step.get("name", "")
                args = step.get("args", {})
                resolved = self._resolve_vars(args, context)
                try:
                    result = execute_tool(tool_name, resolved)
                    preview = (result or "")[:100].replace("\n", " ")
                    results.append(f"[{tool_name}] {preview}")
                    context["last_result"] = result
                except Exception as e:
                    results.append(f"[{tool_name}] 失败: {str(e)}")
            elif step_type == "display":
                results.append(step.get("description", ""))
            elif step_type == "generate_code":
                results.append("[生成代码] 由 LLM 处理")

        return "\n".join(results) if results else "Skill 执行完成"

    def add_skill(self, skill: dict):
        """Add a skill and save to disk."""
        name = skill["name"]
        self._skills[name] = skill
        path = self.skills_dir / f"{name}.yaml"
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(skill, f, allow_unicode=True, default_flow_style=False)

    def _resolve_vars(self, value, context: dict):
        if isinstance(value, str):
            for k, v in context.items():
                value = value.replace(f"{{{k}}}", str(v))
            return value
        if isinstance(value, dict):
            return {k: self._resolve_vars(v, context) for k, v in value.items()}
        if isinstance(value, list):
            return [self._resolve_vars(v, context) for v in value]
        return value


_skill_manager = None


def get_skill_manager():
    global _skill_manager
    if _skill_manager is None:
        _skill_manager = SkillManager()
    return _skill_manager
