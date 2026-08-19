# memory_migrate.py — 票 P0-1：656 条记忆六类迁移（确定性启发式，纯代码规则）

# 设计约束（Hermes 21.4-① / 票据禁止项）：
#   - 纯代码规则，不用 LLM（可复现、可审计、零成本）
#   - 只改 type 字段，不动内容/信号分/时间戳
#   - 显式已知 type 优先；未知/默认 type 走文本启发式
#   - 启发式按优先级判定：RULES > USER_PREF > LESSON > GOAL > ACHIEVEMENT > FACT

import json
import re
from pathlib import Path

from tools.v5_memory import MEMORY_TYPES, normalize_type

# 文本启发式规则（正则，优先级从高到低）
_RULES_RE = re.compile(r"必须|禁止|不要|绝不能|绝对不能|一定不要|不得|永远不要|规则|要求[：:，,]|请务必|一律|授权|只读|才可|须经|需经|需授权|需审批|需 ticket|违反|铁律|纪律", re.IGNORECASE)
_USER_PREF_RE = re.compile(r"偏好|喜欢|习惯|不爱|不喜欢|最爱|钟爱|倾向于|偏爱", re.IGNORECASE)
_LESSON_RE = re.compile(r"教训|踩坑|坑[：:，,]|原因是|错误在于|别再|不要再|导致.*失败|吸取", re.IGNORECASE)
_GOAL_RE = re.compile(r"目标[是：:]|希望达到|用户希望|希望[让能]|计划[要在：:]|想要实现|愿景|打算[在要]", re.IGNORECASE)
_ACHIEVEMENT_RE = re.compile(r"已创建|已完成|实现了|已实现|交付了|上线了|已发布|发布了|建成|开发完成|完成报告|提交了|已提交|修复完成|已修复", re.IGNORECASE)

# 显式 type 覆盖（KEY_DECISION → FACT 由 normalize_type 处理；其余已知值直接归位）
_EXPLICIT_MAP = {
    "USER_PREF": "USER_PREF",
    "RULES": "RULES",
    "FACT": "FACT",
    "ACHIEVEMENT": "ACHIEVEMENT",
    "LESSON": "LESSON",
    "GOAL": "GOAL",
}


def classify_text(text: str) -> str:
    """确定性启发式：按优先级返回六类之一。"""
    if not text:
        return "FACT"
    if _RULES_RE.search(text):
        return "RULES"
    if _USER_PREF_RE.search(text):
        return "USER_PREF"
    if _LESSON_RE.search(text):
        return "LESSON"
    if _GOAL_RE.search(text):
        return "GOAL"
    if _ACHIEVEMENT_RE.search(text):
        return "ACHIEVEMENT"
    return "FACT"


def migrate_entry_type(entry: dict) -> tuple:
    """对单条 entry 判定六类 type。返回 (new_type, 依据)。

    依据：'explicit'（原有显式六类/KEY_DECISION 等规范 type）或
    'heuristic:规则名'（文本启发式）或 'default'（兜底 FACT）。
    """
    raw = entry.get("type", "")
    t = normalize_type(raw)
    # 原 type 已是六类之一（含 KEY_DECISION→FACT 等规范映射）→ 显式保留
    if raw and str(raw).strip().upper() in MEMORY_TYPES:
        return t, "explicit"
    text = entry.get("text", "") or ""
    # 原 type 是旧枚举之一（KEY_DECISION/FACT/USER_PREF 等）→ 尊重原语义映射
    legacy = str(raw).strip().upper().replace(" ", "_")
    if legacy in ("KEY_DECISION", "FACT", "USER_PREF", "OBSERVATION"):
        if legacy == "USER_PREF":
            return "USER_PREF", "explicit"
        if legacy == "OBSERVATION":
            return "FACT", "explicit"
        return "FACT", "explicit"
    # 其余（draft/general/knowledge/核心原则/记忆/memory/DELETE_MEMORY_2/脏值）→ 文本启发式
    # 脏值（DELETE_MEMORY_2 等）当作无类型处理，走启发式
    return classify_text(text), "heuristic"


def migrate_entries(entries: list) -> tuple:
    """批量迁移。返回 (新 entries 列表(仅改 type), 统计 dict)。

    不写盘——调用方决定持久化（测试直接传内存数据）。
    """
    stats = {"total": len(entries), "changed": 0, "by_reason": {}, "by_type": {}}
    out = []
    for e in entries:
        new_type, reason = migrate_entry_type(e)
        if new_type != e.get("type"):
            e = dict(e)  # 浅拷贝，不动原对象（信号分/内容/时间戳原样）
            e["type"] = new_type
            stats["changed"] += 1
        stats["by_reason"][reason] = stats["by_reason"].get(reason, 0) + 1
        stats["by_type"][new_type] = stats["by_type"].get(new_type, 0) + 1
        out.append(e)
    return out, stats


def run_migration(db_path: Path, dry_run: bool = True) -> dict:
    """对 knowledge_base.json 执行迁移。dry_run=True 只统计不写盘。

    返回 {stats, samples: [前 5 条变更样本]}。
    """
    data = json.loads(Path(db_path).read_text(encoding="utf-8"))
    entries = data.get("entries", [])
    new_entries, stats = migrate_entries(entries)
    if not dry_run and stats["changed"] > 0:
        data["entries"] = new_entries
        Path(db_path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    old_by_id = {e.get("id"): e.get("type") for e in entries}
    samples = [
        {"id": e.get("id"), "from": old_by_id.get(e.get("id")), "to": e.get("type"),
         "text": (e.get("text", "") or "")[:60]}
        for e in new_entries
        if e.get("type") != old_by_id.get(e.get("id"))
    ][:5]
    return {"stats": stats, "samples": samples, "dry_run": dry_run}


if __name__ == "__main__":
    import sys
    db = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "data" / "knowledge_base.json"
    res = run_migration(db, dry_run="--write" not in sys.argv)
    print(json.dumps(res, ensure_ascii=False, indent=2))
