"""Skill 管理器 — 活系统：录制技能 + 技能列表。

TICKET-E3a：退役 YAML 通路（_load_all/add_skill/get_skill/execute_skill/
_resolve_vars/get_skill_tools/load_skill 全部删除，调用点已死或已移除）。
只保留活系统：save_from_recording（写 data/skill-standards/standard.md）
+ list_skills（扫描 data/skill-standards/，供前端 /skills 展示）。
"""

import os
import re
from pathlib import Path
from typing import List, Dict


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
    """活系统 Skill 管理器：技能目录 = data/skill-standards/。"""

    @staticmethod
    def _standards_dir() -> Path:
        return Path(__file__).resolve().parent.parent / "data" / "skill-standards"

    def list_skills(self) -> List[str]:
        """扫描 data/skill-standards/*/standard.md，返回技能名列表。"""
        std_dir = self._standards_dir()
        if not std_dir.is_dir():
            return []
        return sorted(
            entry.name
            for entry in std_dir.iterdir()
            if entry.is_dir() and (entry / "standard.md").exists()
        )

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
        std_dir = self._standards_dir() / skill_name
        os.makedirs(std_dir, exist_ok=True)
        filepath = std_dir / "standard.md"

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


_skill_manager = None


def get_skill_manager():
    global _skill_manager
    if _skill_manager is None:
        _skill_manager = SkillManager()
    return _skill_manager
