"""handlers/skills.py — Skills 面板 RPC（票 TICKET-SKILL-PANEL，A 票治理先行）。

skills.list：扫描 data/skill-standards/*/standard.md（preset 预设）+ 
  data/skills/custom/*（custom 自动沉淀，B 票后出现）→ 分组返回
  {preset: [{name, enabled}], custom: [{name, enabled}]}。
  enabled 状态读 data/skills/enabled.json（与 core/skill_loader._load_enabled
  同文件同约定：{"<skill 目录名>": true/false}，缺失默认 true）。

skills.toggle：{skill_name, enabled} → 写 enabled.json（保留其余项）。
  生效路径：injector 每轮经 skill_loader.load_standards() 重读 enabled.json
  （mtime 无关，每次注入都重读）→ 关掉的 skill 下一轮即不注入。

【守卫登记 P0-1 特批标记】本模块为 RPC handler（同 memory.py 模式），
TICKET-SKILL-PANEL owner 授权，守卫白名单已登记（desk_v4/v4b/tel）；
skill_loader.py 的 enabled 过滤为 COST-2 注入链白名单内追加。
"""

import json
import logging
import os
from pathlib import Path

from config import BOBO_DATA_DIR
from bobo_tui_gateway.server_utils import err, ok

logger = logging.getLogger(__name__)

# 路径（与 core/skill_loader 同源约定）
_SKILL_STD_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "skill-standards"
_SKILLS_DIR = Path(BOBO_DATA_DIR) / "skills"
_CUSTOM_DIR = _SKILLS_DIR / "custom"
_ENABLED_FILE = _SKILLS_DIR / "enabled.json"


def _load_enabled() -> dict:
    """读 enabled.json → {skill_name: bool}；缺失/损坏返回 {}（= 全默认开）。"""
    try:
        with open(_ENABLED_FILE, encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, dict):
            return {k: bool(v) for k, v in raw.items()}
    except (OSError, ValueError):
        pass
    return {}


def _scan_skills(root: Path) -> list:
    """扫描目录：每个含 standard.md 的子目录是一个 skill，返回目录名列表。"""
    out = []
    try:
        if not root.is_dir():
            return out
        for entry in sorted(os.listdir(root)):
            if os.path.isfile(os.path.join(root, entry, "standard.md")):
                out.append(entry)
    except OSError:
        pass
    return out


def _group(roots: list) -> list:
    """[{name, enabled}] 分组结构（目录名 + 治理开关状态）。"""
    names = []
    for root in roots:
        for n in _scan_skills(root):
            if n not in names:
                names.append(n)
    enabled = _load_enabled()
    return [{"name": n, "enabled": enabled.get(n, True)} for n in names]


def handle_skills_list(params: dict, rid: str, ctx) -> dict:
    """skills.list → {preset: [...], custom: [...]}。只读。"""
    preset = _group([_SKILL_STD_DIR])
    custom = _group([_CUSTOM_DIR])
    return ok(rid, {"preset": preset, "custom": custom})


def handle_skills_toggle(params: dict, rid: str, ctx) -> dict:
    """skills.toggle {skill_name, enabled} → 写 enabled.json，返回新状态。"""
    name = (params or {}).get("skill_name", "")
    enabled = bool((params or {}).get("enabled"))
    if not name or "/" in name or "\\" in name or name in (".", ".."):
        return err(rid, -32602, "skill_name 非法")
    try:
        _SKILLS_DIR.mkdir(parents=True, exist_ok=True)
        cur = _load_enabled()
        cur[name] = enabled
        with open(_ENABLED_FILE, "w", encoding="utf-8") as f:
            json.dump(cur, f, ensure_ascii=False, indent=2)
        return ok(rid, {"name": name, "enabled": enabled})
    except OSError as e:
        return err(rid, -32000, f"enabled.json 写入失败: {e}")


def register(reg_method, ctx):
    reg_method("skills.list")(lambda params, rid: handle_skills_list(params, rid, ctx))
    reg_method("skills.toggle")(lambda params, rid: handle_skills_toggle(params, rid, ctx))
