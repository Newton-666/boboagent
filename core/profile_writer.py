"""profile_writer.py — USER.md 用户模型画像的引擎侧唯一写入入口（票 TICKET-PROFILE-2）。

职责：
1. write_user_profile(new_entry, category)：写入前过"行为模板过滤"
   （偏好模板"偏好/喜欢 X 方式" / 禁忌模板"不要/别/禁止 X" / 工作流模板"先 X 再 Y"），
   纯事实（如"喜欢冰美式"）→ 拒绝并返回 reason="not_behavioral"；
2. 写入时自动追加版本快照 data/profile_versions.jsonl
   （{"ts", "category", "entry", "diff", "reason", "signal_source"}，与 events.jsonl 同构追加式）；
3. 写入动作 emit profile.update 事件（payload: category/entry/diff，后端事件先行，
   前端工具卡展示是下一票）。

边界：本模块只写 data/knowledge_base.json 的 profile 段与版本快照 jsonl；
USER.md 由迁移流程生成，本模块不改 USER.md。
"""

import json
import logging
import re
import threading
import time
from pathlib import Path

from config import BOBO_DATA_DIR

# 模块属性访问（不绑定 import 时单例：测试 monkeypatch core.event_bus.event_bus 生效）
import core.event_bus as _event_bus_mod

logger = logging.getLogger(__name__)

# 数据文件路径（测试可 monkeypatch 重定向）
_KB_PATH = Path(BOBO_DATA_DIR) / "knowledge_base.json"
_VERSIONS_FILE = Path(BOBO_DATA_DIR) / "profile_versions.jsonl"

_lock = threading.Lock()

# ── 行为模板（票面口径：偏好/禁忌/工作流 三类）──
# 偏好模板："偏好 X" 或 "喜欢 X 方式"（必须落到行为方式，纯事物如"喜欢冰美式"不匹配）
_PREF_PAT = re.compile(r"(偏好|喜欢.{0,16}方式)")
# 禁忌模板："不要/别/禁止 X"
_TABOO_PAT = re.compile(r"(不要|别|禁止)")
# 工作流模板："先 X 再 Y"
_WORKFLOW_PAT = re.compile(r"先.{1,48}再.{1,48}")


def classify_behavioral(new_entry: str) -> str | None:
    """行为模板过滤：命中返回类别（preference/taboo/workflow），未命中返回 None。

    优先级：偏好 → 禁忌 → 工作流（取首个命中）。
    """
    if not new_entry or not isinstance(new_entry, str):
        return None
    if _PREF_PAT.search(new_entry):
        return "preference"
    if _TABOO_PAT.search(new_entry):
        return "taboo"
    if _WORKFLOW_PAT.search(new_entry):
        return "workflow"
    return None


def _read_kb_profile() -> dict:
    """读 knowledge_base.json 的 profile 段。文件缺失/损坏返回空 dict。"""
    try:
        with open(_KB_PATH, encoding="utf-8") as f:
            kb = json.load(f)
        prof = kb.get("profile", {})
        return prof if isinstance(prof, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_kb_profile(profile: dict) -> bool:
    """回写 knowledge_base.json（保留 entries/folders 等其它键）。"""
    try:
        with open(_KB_PATH, encoding="utf-8") as f:
            kb = json.load(f)
        if not isinstance(kb, dict):
            kb = {}
        kb["profile"] = profile
        tmp = _KB_PATH.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(kb, f, ensure_ascii=False, indent=1)
        tmp.replace(_KB_PATH)
        return True
    except (OSError, ValueError) as e:
        logger.warning("profile_writer: 回写 knowledge_base.json 失败: %s", e)
        return False


def _append_version_snapshot(record: dict) -> bool:
    """追加版本快照到 profile_versions.jsonl（追加式，失败静默返回 False）。"""
    try:
        _VERSIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_VERSIONS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        return True
    except OSError as e:
        logger.warning("profile_writer: 追加版本快照失败: %s", e)
        return False


def _last_snapshot_entry(category: str) -> str | None:
    """读版本快照最后一条同 category 的 entry（去重用）。"""
    try:
        if not _VERSIONS_FILE.exists():
            return None
        last = None
        with open(_VERSIONS_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if rec.get("category") == category:
                    last = rec
        return last.get("entry") if last else None
    except OSError:
        return None


def write_user_profile(
    new_entry: str,
    category: str,
    signal_source: str = "user",
) -> dict:
    """引擎侧唯一写入入口。

    Args:
        new_entry: 画像文本（一句）。
        category: 归属类别（preference/taboo/workflow）。
        signal_source: 信号来源（默认 user；知识迁移等场景可传迁移源）。

    Returns:
        {"ok": bool, "reason": str|None, "version": dict|None}
        - ok=False + reason="not_behavioral"：模板不过（纯事实）
        - ok=False + reason="duplicate"：同 category 同内容已存在（去重，不重复追加）
        - ok=True + reason=None：写入成功，version 为本次快照记录
    """
    if not isinstance(new_entry, str) or not new_entry.strip():
        return {"ok": False, "reason": "not_behavioral", "version": None}

    # ── 行为模板过滤 ──
    matched = classify_behavioral(new_entry)
    if matched is None:
        return {"ok": False, "reason": "not_behavioral", "version": None}
    # 调用方 category 未指定时用模板命中的类别；指定了以模板为准（模板是闸门）
    if category not in ("preference", "taboo", "workflow"):
        category = matched

    with _lock:
        profile = _read_kb_profile()

        # ── 去重：同 category 同内容不重复追加 ──
        old = profile.get(category)
        old_value = old.get("value") if isinstance(old, dict) else None
        if old_value == new_entry:
            return {"ok": False, "reason": "duplicate", "version": None}
        last_snap = _last_snapshot_entry(category)
        if last_snap == new_entry:
            return {"ok": False, "reason": "duplicate", "version": None}

        # ── diff（版本快照用）──
        diff = f"+ {new_entry}" if not old_value else f"{old_value} → {new_entry}"

        # ── 写入 knowledge_base.json profile 段 ──
        profile[category] = {
            "value": new_entry,
            "updated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        written = _write_kb_profile(profile)
        if not written:
            return {"ok": False, "reason": "write_failed", "version": None}

        # ── 版本快照（追加式，与 events.jsonl 同构）──
        snapshot = {
            "ts": time.time(),
            "category": category,
            "entry": new_entry,
            "diff": diff,
            "reason": "behavioral",
            "signal_source": signal_source,
        }
        _append_version_snapshot(snapshot)

        # ── emit profile.update 事件（后端事件先行）──
        _event_bus_mod.event_bus.write("profile.update", {
            "category": category,
            "entry": new_entry,
            "diff": diff,
        })

        return {"ok": True, "reason": None, "version": snapshot}
