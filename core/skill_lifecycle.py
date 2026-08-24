"""core/skill_lifecycle.py — 技能生命周期（阶段 D：使用驱动状态机 + provenance）。

状态机：active → stale → archived（基于"最后使用时间"，非创建年龄）。
- stale_after_days 未用 → stale；archive_after_days 更久未用 → 归档（可逆，不删除）；
- 再用 → 自动 reactivate；
- pinned 技能永不自动改动；
- 时间锚定：新技能首见锚定 now；从未用过的锚 created_at（防新技能误杀）；
- 纯确定性实现（无 LLM）——符合"学习=后端监督"；
- provenance：只管理"自主沉淀"的技能。

存储：data/skills/lifecycle.json（skill 名 → 记录）。
"""
import json
import logging
import os
from datetime import datetime, timedelta, timezone

from pathlib import Path

logger = logging.getLogger(__name__)

_BASE = Path(__file__).resolve().parent.parent
_LIFECYCLE_FILE = _BASE / "data" / "skills" / "lifecycle.json"

STATE_ACTIVE = "active"
STATE_STALE = "stale"
STATE_ARCHIVED = "archived"

# 默认阈值（天）：未用 stale / 更久归档（可配置）
STALE_AFTER_DAYS = 21
ARCHIVE_AFTER_DAYS = 60


def _load() -> dict:
    try:
        if _LIFECYCLE_FILE.exists():
            with open(_LIFECYCLE_FILE, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
    except (OSError, ValueError):
        pass
    return {}


def _save(data: dict) -> None:
    try:
        _LIFECYCLE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_LIFECYCLE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError:
        logger.warning("skill_lifecycle save failed (silent)", exc_info=True)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse(ts) -> datetime | None:
    try:
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (TypeError, ValueError):
        return None


def register_skill(name: str, agent_created: bool = True) -> dict:
    """登记一个技能进生命周期（首次见到锚定 now，防新技能立即归档）。"""
    data = _load()
    if name in data:
        return data[name]
    rec = {
        "name": name,
        "created_at": _now(),
        "last_activity_at": _now(),
        "state": STATE_ACTIVE,
        "pinned": False,
        "agent_created": agent_created,
    }
    data[name] = rec
    _save(data)
    return rec


def mark_used(name: str) -> None:
    """技能被使用 → 更新 last_activity_at；stale 中 → 自动 reactivate。"""
    data = _load()
    rec = data.get(name)
    if rec is None:
        register_skill(name)
        rec = data[name]
    rec["last_activity_at"] = _now()
    if rec.get("state") == STATE_STALE:
        rec["state"] = STATE_ACTIVE
    _save(data)


def set_pinned(name: str, pinned: bool = True) -> None:
    """用户显式钉住：技能永不自动改动（stale/归档/删除都跳过）。"""
    data = _load()
    rec = data.setdefault(name, {})
    rec["name"] = name
    rec["pinned"] = pinned
    _save(data)


def apply_transitions(now: datetime | None = None) -> dict:
    """自动状态转换（纯函数无 LLM）：active→stale→archived；used 后 reactivate。

    pinned 跳过；时间锚定：never-active 用 created_at 锚定（防新技能误杀）。
    返回计数 {marked_stale, archived, reactivated, checked}。
    """
    if now is None:
        now = datetime.now(timezone.utc)
    stale_cutoff = now - timedelta(days=STALE_AFTER_DAYS)
    archive_cutoff = now - timedelta(days=ARCHIVE_AFTER_DAYS)
    counts = {"checked": 0, "marked_stale": 0, "archived": 0, "reactivated": 0}
    data = _load()
    changed = False
    for name, rec in data.items():
        if not isinstance(rec, dict):
            continue
        if rec.get("pinned"):
            continue
        counts["checked"] += 1
        anchor = _parse(rec.get("last_activity_at")) or _parse(rec.get("created_at")) or now
        state = rec.get("state", STATE_ACTIVE)
        if anchor <= archive_cutoff and state != STATE_ARCHIVED:
            rec["state"] = STATE_ARCHIVED
            counts["archived"] += 1
            changed = True
        elif anchor <= stale_cutoff and state == STATE_ACTIVE:
            rec["state"] = STATE_STALE
            counts["marked_stale"] += 1
            changed = True
        elif anchor > stale_cutoff and state == STATE_STALE:
            rec["state"] = STATE_ACTIVE
            counts["reactivated"] += 1
            changed = True
    if changed:
        _save(data)
    return counts


def list_managed() -> list:
    """被管理的技能记录（供路由/面板）。"""
    data = _load()
    return [rec for rec in data.values() if isinstance(rec, dict)]
