"""Skill 管理器 — 加载、执行、录制技能。技能作为动态工具暴露给 LLM。"""

import json
import os
import re
import yaml
from pathlib import Path
from typing import Optional, List, Dict


def _auto_triggers(name: str, desc: str = "") -> list:
    """Auto-generate trigger keywords from skill name and description."""
    keywords = set()
    text = f"{name} {desc}".lower()
    # Extract Chinese words (2-4 chars)
    for m in re.finditer(r"[\u4e00-\u9fff]{2,6}", text):
        word = m.group()
        if word not in ("录制", "步骤", "描述", "教学", "技能", "工作", "参考", "使用", "分析"):
            keywords.add(word)
    # Extract English keywords (split by space/slash/hyphen)
    for part in re.split(r"[\s/\-_,]", name):
        part = part.strip().lower()
        if len(part) > 2 and part not in ("the", "and", "for", "from", "with", "skill"):
            keywords.add(part)
    return sorted(keywords)[:6]


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
            triggers = skill.get("triggers", [])
            tool = {
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
            }
            if triggers:
                tool["triggers"] = triggers
            tools.append(tool)
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

    def save_from_recording(self, skill_name: str, messages: List[Dict], description: str = "") -> str:
        """将录制的对话保存为 standard.md 格式的 skill（data/skill-standards/）。"""
        if not messages:
            return "没有记录到任何对话"

        # 提取工具调用序列
        tool_seq = []
        user_inputs = []
        for msg in messages:
            role = msg.get("role")
            if role == "user":
                user_inputs.append(msg.get("content", "")[:80])
            elif role == "tool_call":
                tool_seq.append(msg.get("name", ""))

        # 生成触发词
        triggers = _auto_triggers(skill_name, description)
        trigger_str = ", ".join(triggers) if triggers else skill_name

        # 生成 tool 序列描述
        tool_flow = " → ".join(dict.fromkeys(tool_seq)) if tool_seq else "（未检测到工具调用）"
        user_examples = "、".join([u[:40] for u in user_inputs[:3]]) if user_inputs else skill_name

        # 写 standard.md
        _project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        std_dir = os.path.join(_project_root, "data", "skill-standards", skill_name)
        os.makedirs(std_dir, exist_ok=True)
        filepath = os.path.join(std_dir, "standard.md")

        content = f"""# {skill_name} v1

> keywords: {trigger_str}
> status: draft

## 工作流

录制于 Bobo 教学模式。工具序列: {tool_flow}

示例场景: {user_examples}

## 描述

{description or f'从 {len(messages)} 条录制消息中提取的工作流。'}

## 步骤

"""
        for i, msg in enumerate(messages, 1):
            role = msg.get("role", "")
            if role == "user":
                content += f"{i}. 用户: {msg.get('content', '')[:200]}\n"
            elif role == "assistant":
                c = msg.get("content", "")
                if c:
                    content += f"{i}. Bobo: {c[:200]}\n"
            elif role == "tool_call":
                tool = msg.get("name", "")
                args = str(msg.get("args", {}))[:120]
                content += f"{i}. 工具: {tool}({args})\n"

        content += """
## 验收

- [ ] 在工作流触发时自动注入
- [ ] 状态机步骤完整
"""

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        return f"Skill '{skill_name}' 已保存到 data/skill-standards/{skill_name}/standard.md\n触发词: {trigger_str}\n工具流: {tool_flow}"

    def load_skill(self, skill_name: str) -> dict:
        """从 YAML 文件加载单个 skill（兼容旧 SkillExecutor 接口）。"""
        filepath = self.skills_dir / f"{skill_name}.yaml"
        if not filepath.exists():
            return None
        with open(filepath, encoding="utf-8") as f:
            return yaml.safe_load(f)


_skill_manager = None


def get_skill_manager():
    global _skill_manager
    if _skill_manager is None:
        _skill_manager = SkillManager()
    return _skill_manager


# 兼容别名：旧代码用 skill_executor → 统一到 skill_manager
get_skill_executor = get_skill_manager
