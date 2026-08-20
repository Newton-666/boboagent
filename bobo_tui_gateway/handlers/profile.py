"""handlers/profile.py — 设置页 Profile 仪表盘 RPC（票 TICKET-PROFILE-4，P0-1 特批登记）。

profile.get：读 docs/USER.md（mtime 缓存，与 core/injector._load_user_profile
  同模式）+ data/profile_versions.jsonl 倒序（最新在前，限 20 条）→ 返回
  {user_md, versions, count}。只读不写。

profile.rollback：按 ts 找版本快照 → 恢复 docs/USER.md 对应分区行 +
  data/knowledge_base.json profile 段（影子）→ 追加一条 reason="rollback" 记录
  → 返回新状态。回滚逻辑对齐 core/profile_writer._sync_user_md（复用同一函数，
  不重写一套）；回滚后 USER.md mtime 变化 → 本模块与 injector 的 mtime 缓存
  下轮自动重读。

profile.save：用户手动编辑 USER.md 后保存（signal_source=user_edit，绝对权威）。

【P0-1 特批标记】本模块为 RPC handler（同 memory.py 模式），改动经
TICKET-PROFILE-4 owner 授权，守卫白名单已登记（desk_v4/v4b/tel）。
"""

import json
import os
import time
from pathlib import Path

from config import BOBO_DATA_DIR
from bobo_tui_gateway.server_utils import ok, err

# 路径（与 core/injector._USER_PROFILE_PATH / core/profile_writer 同源约定）
_USER_MD_PATH = Path(__file__).resolve().parent.parent.parent / "docs" / "USER.md"
_VERSIONS_FILE = Path(BOBO_DATA_DIR) / "profile_versions.jsonl"
_KB_PATH = Path(BOBO_DATA_DIR) / "knowledge_base.json"

# mtime 缓存（与 injector._load_user_profile 同模式：mtime 变化才重读）
_USER_MD_CACHE: dict = {"mtime": -1, "content": None}

_HISTORY_LIMIT = 20


def _read_user_md() -> str:
    """mtime 缓存读 docs/USER.md，缺失返回空串。"""
    try:
        st = os.stat(_USER_MD_PATH)
    except OSError:
        _USER_MD_CACHE["content"] = None
        _USER_MD_CACHE["mtime"] = -1
        return ""
    if st.st_mtime != _USER_MD_CACHE.get("mtime"):
        try:
            with open(_USER_MD_PATH, encoding="utf-8") as f:
                _USER_MD_CACHE["content"] = f.read()
            _USER_MD_CACHE["mtime"] = st.st_mtime
        except OSError:
            _USER_MD_CACHE["content"] = None
            _USER_MD_CACHE["mtime"] = -1
            return ""
    return _USER_MD_CACHE["content"] or ""


def _read_versions(limit: int = _HISTORY_LIMIT) -> list:
    """读版本快照 jsonl，倒序（最新在前），限 limit 条；损坏行跳过。"""
    if not _VERSIONS_FILE.exists():
        return []
    rows = []
    try:
        with open(_VERSIONS_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                rows.append(rec)
    except OSError:
        return []
    rows.sort(key=lambda r: r.get("ts", 0), reverse=True)
    return rows[:limit]


def _find_snapshot(ts) -> dict | None:
    """按 ts 找快照（含回滚记录）。"""
    if not _VERSIONS_FILE.exists():
        return None
    try:
        with open(_VERSIONS_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if rec.get("ts") == ts:
                    return rec
    except OSError:
        return None
    return None


def _read_kb_profile() -> dict:
    """读 knowledge_base.json 的 profile 段（影子）。"""
    try:
        data = json.loads(_KB_PATH.read_text(encoding="utf-8"))
        return data.get("profile", {}) or {}
    except (OSError, ValueError):
        return {}


def _snapshot_state() -> dict:
    """返回回滚后的新状态（profile.get 同构）。"""
    return {"user_md": _read_user_md(), "versions": _read_versions(), "count": 0}


def handle_profile_get(params: dict, rid: str) -> dict:
    """profile.get：读 USER.md + 版本历史倒序。"""
    versions = _read_versions()
    return ok(rid, {"user_md": _read_user_md(), "versions": versions, "count": len(versions)})


def handle_profile_rollback(params: dict, rid: str) -> dict:
    """profile.rollback：按 ts 恢复 USER.md + profile 段，追加回滚记录。"""
    ts = params.get("ts")
    if ts is None:
        return err(rid, -32602, "缺 ts 参数")
    snap = _find_snapshot(ts)
    if not snap:
        return err(rid, -32000, f"未找到 ts={ts} 的快照")
    category = snap.get("category") or "preference"
    entry = snap.get("entry") or ""
    if not entry:
        return err(rid, -32000, "快照缺 entry，无法回滚")

    try:
        # 复用 profile_writer 的 USER.md 同步函数（对齐，不重写一套）
        from core.profile_writer import _sync_user_md, _write_kb_profile
    except ImportError as e:
        return err(rid, -32000, f"profile_writer 不可用: {e}")

    # 当前值（knowledge_base profile 段，影子）
    cur = _read_kb_profile().get(category, {}).get("value")

    # 恢复 USER.md（权威载体）：当前值行 → 快照 entry 行
    if not _sync_user_md(category, entry, cur):
        return err(rid, -32000, "USER.md 回滚写入失败")

    # 恢复 knowledge_base profile 段（影子）
    profile = _read_kb_profile()
    profile[category] = {
        "value": entry,
        "updated": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    if not _write_kb_profile(profile):
        return err(rid, -32000, "knowledge_base 回滚写入失败")

    # 追加回滚记录
    rec = {
        "ts": time.time(),
        "category": category,
        "entry": entry,
        "diff": f"{cur or '∅'} → {entry}",
        "reason": "rollback",
        "signal_source": "profile.rollback",
    }
    try:
        with open(_VERSIONS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError as e:
        return err(rid, -32000, f"回滚记录追加失败: {e}")

    versions = _read_versions()
    return ok(rid, {"user_md": _read_user_md(), "versions": versions, "count": len(versions)})


def _diff_md(old_md: str, new_md: str) -> str:
    """用户手动编辑的 diff 摘要：按行 diff，取首处变化（新增/删除/修改）。"""
    if old_md == new_md:
        return ""
    old_lines = [l for l in old_md.splitlines() if l.strip()]
    new_lines = [l for l in new_md.splitlines() if l.strip()]
    # 逐行对比（简单 LCS 风格：找首处不匹配）
    i = 0
    while i < len(old_lines) and i < len(new_lines) and old_lines[i] == new_lines[i]:
        i += 1
    if i < len(new_lines) and (i >= len(old_lines) or new_lines[i] != old_lines[i]):
        _ent = new_lines[i].strip()
        if _ent.startswith("- "):
            _ent = _ent[2:].strip()
        return "+ " + _ent
    if i < len(old_lines):
        return "- " + old_lines[i].strip()
    return "~ 用户手动编辑"


def handle_profile_save(params: dict, rid: str) -> dict:
    """profile.save：用户手动编辑 USER.md 后保存。

    与 write_user_profile 同构：USER.md 权威载体先写（原子）→ knowledge_base
    profile 段影子 → 版本快照（signal_source="user_edit"）→ 返回新状态。
    不调用 write_user_profile 的模板过滤（用户手动编辑不受行为模板限制——
    用户对自己的模型有绝对权威，24.9 手动条目保留机制）。
    """
    new_md = params.get("user_md")
    if new_md is None or not isinstance(new_md, str):
        return err(rid, -32602, "缺 user_md 参数")
    try:
        from core.profile_writer import _write_kb_profile
        old_md = _read_user_md()
        if not new_md.strip():
            return err(rid, -32000, "USER.md 不能为空")
        # USER.md 权威载体先写（原子）
        tmp = _USER_MD_PATH.with_suffix(".md.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(new_md)
            if not new_md.endswith("\n"):
                f.write("\n")
        tmp.replace(_USER_MD_PATH)
        # 刷新 mtime 缓存（本模块 + injector 下轮自动重读）
        _USER_MD_CACHE["mtime"] = -1
        # 影子：diff 识别新增/修改行 → 更新 knowledge_base profile 段对应分区
        # （USER.md 权威存全部，影子单值镜像"本次变更的条目"）
        diff = _diff_md(old_md, new_md)
        if diff.startswith("+ "):
            new_entry = diff[2:].strip()
            # 从新 USER.md 定位该条目所属分区
            current_sec = None
            profile = _read_kb_profile()
            for line in new_md.splitlines():
                t = line.strip()
                if t in ("## \u504f\u597d", "## \u7981\u5fcc", "## \u5de5\u4f5c\u6d41"):
                    current_sec = {
                        "## \u504f\u597d": "preference",
                        "## \u7981\u5fcc": "taboo",
                        "## \u5de5\u4f5c\u6d41": "workflow",
                    }[t]
                elif current_sec and t.startswith("- ") and t[2:].strip() == new_entry:
                    profile[current_sec] = {
                        "value": new_entry,
                        "updated": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    }
            _write_kb_profile(profile)
        # 版本快照（signal_source=user_edit，diff 对比）
        rec = {
            "ts": time.time(),
            "category": "user_edit",
            "entry": diff or "~ 用户手动编辑",
            "diff": diff or "~ 用户手动编辑",
            "reason": "user_edit",
            "signal_source": "user_edit",
        }
        try:
            with open(_VERSIONS_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except OSError as e:
            return err(rid, -32000, f"快照追加失败: {e}")
    except OSError as e:
        return err(rid, -32000, f"USER.md 写入失败: {e}")
    except ImportError as e:
        return err(rid, -32000, f"profile_writer 不可用: {e}")
    versions = _read_versions()
    return ok(rid, {"user_md": _read_user_md(), "versions": versions, "count": len(versions)})


def register(reg_method, ctx):
    reg_method("profile.get")(handle_profile_get)
    reg_method("profile.rollback")(handle_profile_rollback)
    reg_method("profile.save")(handle_profile_save)
