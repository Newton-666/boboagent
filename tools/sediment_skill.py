"""tools/sediment_skill.py — 技能沉淀工具（阶段 D：agent 自主触发）。

agent 判断"这段工作流值得沉淀"时调用——创建技能包（写进可路由目录）
+ 登记生命周期（agent_created provenance）。替代从未成功的 count-based 触发。
"""
import logging
import os
import re
from pathlib import Path

logger = logging.getLogger(__name__)

_BASE = Path(__file__).resolve().parent.parent
_ROUTABLE_DIR = _BASE / "data" / "skill-standards" / "custom"  # skill_loader 扫描目录下


def _slugify(name: str) -> str:
    """技能名 → 目录名（小写短横线，防路径注入）。"""
    s = re.sub(r"[^a-z0-9]+", "-", str(name).lower()).strip("-")
    return s or "custom-skill"


def sediment_skill(name: str, description: str, workflow: str) -> str:
    """创建技能包 + 登记生命周期。返回技能目录名（失败返回错误串）。

    description/流程语言 = 技能包内容（语言工作流，无工具声明——B 设计）。
    """
    try:
        slug = _slugify(name)
        std_dir = _ROUTABLE_DIR / slug
        std_dir.mkdir(parents=True, exist_ok=True)
        content = (
            f"# {name}\n\n"
            f"> 价值: {description}\n"
            f"> 自主沉淀（agent 判断值得）：{description}\n\n"
            f"**工作流（必须遵守）**：\n{workflow}\n"
        )
        (std_dir / "standard.md").write_text(content, encoding="utf-8")
        # 登记生命周期（agent_created provenance）
        from core.skill_lifecycle import register_skill
        register_skill(slug, agent_created=True)
        return f"技能已沉淀: {slug}（可被路由，写入 {std_dir}）"
    except Exception as e:
        logger.warning("sediment_skill failed (silent)", exc_info=True)
        return f"沉淀失败: {e}"
