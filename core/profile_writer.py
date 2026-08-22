"""profile_writer.py — USER.md 用户模型画像的引擎侧唯一写入入口（票 TICKET-PROFILE-2/2b）。

职责：
1. write_user_profile(new_entry, category)：写入前过"行为模板过滤"
   （偏好模板"偏好/喜欢 X 方式" / 禁忌模板"不要/别/禁止 X" / 工作流模板"先 X 再 Y"），
   纯事实（如"喜欢冰美式"）→ 拒绝并返回 reason="not_behavioral"；
2. 写入成功后同步 docs/USER.md（权威载体）：新增追加 / "（暂无）"替换 / 更新替换
   对应行（不追加重复），原子写（tmp + replace），手动初始条目保留；
3. 写入时自动追加版本快照 data/profile_versions.jsonl
   （{"ts", "category", "entry", "diff", "reason", "signal_source"}，与 events.jsonl 同构追加式）；
4. 写入动作 emit profile.update 事件（payload: category/entry/diff，后端事件先行，
   前端工具卡展示是下一票）。

权威关系（票 TICKET-PROFILE-2b）：docs/USER.md 是行为影响型画像的权威载体
（常驻 prompt），data/knowledge_base.json 的 profile 段是影子。
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
# USER.md 权威载体（与 core/injector.py 的 _USER_PROFILE_PATH 同文件）
_USER_MD_PATH = Path(__file__).resolve().parent.parent / "docs" / "USER.md"

# category → USER.md 分区标题
_SECTION_TITLES = {
    "preference": "## 偏好",
    "taboo": "## 禁忌",
    "workflow": "## 工作流",
}

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


# 最近一次写入的会话 id（signal_detector 异步线程调用前设置；广播 profile.update
# 时带 session_id，前端 isForeignSession 过滤依赖它）。线程安全：仅原子赋值。
_last_sid = ""
_last_sid_lock = threading.Lock()


def set_last_sid(sid: str) -> None:
    global _last_sid
    with _last_sid_lock:
        _last_sid = sid or ""


def _get_last_sid() -> str:
    with _last_sid_lock:
        return _last_sid


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


def _atomic_write_user_md(lines: list[str]) -> bool:
    """原子写 USER.md（tmp + replace，绝不允许半写状态）。"""
    try:
        tmp = _USER_MD_PATH.with_suffix(".md.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
            if lines:
                f.write("\n")
        tmp.replace(_USER_MD_PATH)
        return True
    except OSError as e:
        logger.warning("profile_writer: 原子写 USER.md 失败: %s", e)
        return False


def _sync_user_md(category: str, new_entry: str, last_entry: str | None,
                  replace_entry: str | None = None) -> bool:
    """同步 docs/USER.md：USER.md 是行为影响型画像的权威载体。

    规则（票 TICKET-PROFILE-2b）：
    - 分区已含 `- {new_entry}` → 不追加（去重）
    - 分区当前为"（暂无）" → 替换为实际条目
    - 修正（replace_entry 非 None，纠正信号）→ 替换对应的旧条目，不新增覆盖（TICKET-PROFILE-PARADIGM-IMPLEMENT）
    - 更新（同 category 旧值 = last_entry 存在且分区含该行）→ 替换对应行，不追加重复
    - 新增 → 分区末尾追加一行
    - USER.md 缺失/分区缺失 → 跳过同步（返回 True，不失败）

    Returns:
        bool：写入成功或跳过返回 True；IO 失败返回 False（调用方整体失败）。
    """
    try:
        if not _USER_MD_PATH.exists():
            return True  # 权威载体缺失：跳过同步（profile 影子照写）
        with open(_USER_MD_PATH, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError as e:
        logger.warning("profile_writer: 读 USER.md 失败: %s", e)
        return False

    title = _SECTION_TITLES.get(category)
    if title is None:
        return True

    # 定位分区：[sec_start+1, sec_end)
    sec_start = None
    sec_end = len(lines)
    for i, ln in enumerate(lines):
        if sec_start is None:
            if ln.strip() == title:
                sec_start = i
        elif ln.startswith("## "):
            sec_end = i
            break
    if sec_start is None:
        return True  # 分区缺失：跳过

    body = lines[sec_start + 1:sec_end]

    # 去重：分区已含同文本条目
    if any(ln.strip() == f"- {new_entry}" for ln in body):
        return True

    # 修正（replace_entry 非 None，纠正信号 TICKET-PROFILE-PARADIGM-IMPLEMENT）：
    # 找到对应旧条目行 → 替换为 new_entry（不新增覆盖），保持权威结构。
    # 容错匹配：忽略结尾标点差异（如句号），reference 为旧条目的子串或相等。
    if replace_entry:
        for i in range(sec_start + 1, sec_end):
            entry_text = lines[i].strip()
            if entry_text.startswith("- "):
                entry_text = entry_text[2:].strip()
            if replace_entry in entry_text or (entry_text and entry_text in replace_entry):
                lines[i] = f"- {new_entry}"
                return _atomic_write_user_md(lines)

    # （暂无）→ 替换
    for i in range(sec_start + 1, sec_end):
        if lines[i].strip() == "（暂无）":
            lines[i] = f"- {new_entry}"
            return _atomic_write_user_md(lines)

    # 更新：last_entry（上次写入的快照末条）行 → 替换
    if last_entry:
        for i in range(sec_start + 1, sec_end):
            if lines[i].strip() == f"- {last_entry}":
                lines[i] = f"- {new_entry}"
                return _atomic_write_user_md(lines)

    # 新增：分区末尾追加（跳过尾部空行，插在最后一个非空行后）
    insert_at = sec_end
    j = sec_end - 1
    while j > sec_start and lines[j].strip() == "":
        j -= 1
    insert_at = j + 1
    lines.insert(insert_at, f"- {new_entry}")
    return _atomic_write_user_md(lines)


def write_user_profile(
    new_entry: str,
    category: str,
    signal_source: str = "user",
    replace_entry: str | None = None,
    bypass_template: bool = False,
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
    # bypass_template（instruction 显式指令）：用户明确说"记住/以后都"等指令，
    # 豁免模板闸门直接写 USER.md（TICKET-PROFILE-PARADIGM-IMPLEMENT）。
    if bypass_template:
        if category not in ("preference", "taboo", "workflow"):
            category = "workflow"
    else:
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

        # ── 权威载体 USER.md 先写（票 TICKET-PROFILE-2b：USER.md 是权威，profile 是影子）──
        # last_entry = 上次写入的快照末条：同 category 更新时替换对应行（不追加重复）；
        # 手动初始条目（无快照记录）永不替换 → 保留。
        # replace_entry（纠正信号）→ 对应旧条目替换，不新增覆盖（TICKET-PROFILE-PARADIGM-IMPLEMENT）
        synced = _sync_user_md(category, new_entry, last_snap, replace_entry)
        if not synced:
            return {"ok": False, "reason": "user_md_write_failed", "version": None}

        # ── 写入 knowledge_base.json profile 段（影子）──
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
        # 【COST-3 特批标记】PROFILE 系列（PROFILE-2/2b/5）授权：双通道——
        # ① event_bus 落盘（审计账本，只写不读）；② gateway socket 广播
        # （前端工具卡实时展示）。② 用延迟 import + 容错——core 层不硬依赖
        # gateway；gateway 进程内（signal_detector 由 engine_adapter 触发）可广播，
        # 纯 core 环境（测试/CLI）静默跳过。修复 PROFILE-3 死代码缺口：此前只写
        # event_bus（仅审计），前端 on('profile.update') 从未收到真实事件。
        _event_bus_mod.event_bus.write("profile.update", {
            "category": category,
            "entry": new_entry,
            "diff": diff,
        })
        try:
            from bobo_tui_gateway.transport import write_json
            write_json({
                "jsonrpc": "2.0", "method": "event",
                "params": {
                    "type": "profile.update",
                    "payload": {"category": category, "entry": new_entry, "diff": diff},
                    "session_id": _get_last_sid(),
                },
            })
        except Exception:
            # gateway 不可用（纯 core/测试环境）→ 静默跳过，审计仍完整
            pass

        return {"ok": True, "reason": None, "version": snapshot}


# ── TICKET-PROFILE-PARADIGM-IMPLEMENT：memory 写入 + 污染清理（可回滚）──
# 【COST-3/P0-1 特批标记】PROFILE 系列授权：加 memory（topic 级）写入入口 + USER.md
# 污染清理逻辑（识别话题级/一次性条目移出，保留真范式，快照可回滚）。


def write_memory_entry(new_entry: str, signal_source: str = "auto_detect") -> dict:
    """写 topic 级记忆到 knowledge_base.json 的 entries 数组（不进 USER.md）。

    TICKET-PROFILE-PARADIGM-IMPLEMENT：memory（话题级）分流不写 USER.md，存 KB 记忆；
    带版本快照（category=memory）。去重：同内容不重复追加。
    """
    if not isinstance(new_entry, str) or not new_entry.strip():
        return {"ok": False, "reason": "empty", "version": None}
    try:
        with open(_KB_PATH, encoding="utf-8") as f:
            kb = json.load(f)
    except (OSError, ValueError):
        kb = {}
    if not isinstance(kb, dict):
        kb = {}
    entries = kb.get("entries", [])
    if not isinstance(entries, list):
        entries = []
    for e in entries:
        if isinstance(e, dict) and e.get("content") == new_entry:
            return {"ok": False, "reason": "duplicate", "version": None}
    entries.append({"content": new_entry, "ts": time.time(),
                    "signal_source": signal_source, "type": "USER_PREF"})
    kb["entries"] = entries
    try:
        tmp = _KB_PATH.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(kb, f, ensure_ascii=False, indent=1)
        tmp.replace(_KB_PATH)
    except OSError as e:
        logger.warning("profile_writer: 写 KB memory 失败: %s", e)
        return {"ok": False, "reason": "write_failed", "version": None}
    snap = {"ts": time.time(), "category": "memory", "entry": new_entry,
            "diff": f"+ {new_entry}", "reason": "topic_memory", "signal_source": signal_source}
    _append_version_snapshot(snap)
    return {"ok": True, "reason": None, "version": snap}


def snapshot_user_md() -> dict:
    """备份当前 docs/USER.md（清理前快照，可回滚）。返回 {ok, backup_path, ts}。"""
    try:
        if not _USER_MD_PATH.exists():
            return {"ok": False, "reason": "missing", "backup_path": None, "ts": None}
        with open(_USER_MD_PATH, encoding="utf-8") as f:
            content = f.read()
        backup_dir = Path(BOBO_DATA_DIR) / "profile_versions"
        backup_dir.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        bp = backup_dir / f"user_md_{ts}.md"
        bp.write_text(content, encoding="utf-8")
        return {"ok": True, "backup_path": str(bp), "ts": ts}
    except OSError as e:
        logger.warning("profile_writer: 备份 USER.md 失败: %s", e)
        return {"ok": False, "reason": "io_error", "backup_path": None, "ts": None}


def _section_of(lines: list[str], idx: int) -> str:
    """返回 lines[idx] 所在分区的标题（不含 '## ' 前缀）。"""
    for j in range(idx, -1, -1):
        if lines[j].strip().startswith("## "):
            return lines[j].strip()[3:]
    return ""


def clean_user_md_pollution(judge_fn=None) -> dict:
    """清理 docs/USER.md 污染条目（话题级/一次性），保留真范式。

    TICKET-PROFILE-PARADIGM-IMPLEMENT：识别被词眼误写的 topic-level/一次性条目，
    移出 USER.md（保留 profile/instruction）。清理前 snapshot_user_md 备份（可回滚）；
    被清理条目记入版本快照（category=cleanup, reason=cleanup_pollution）——动作有据可查。

    judge_fn：单条 → {"classify": ...}；默认 _judge_by_constraints（延迟 import 防循环）。
    """
    if judge_fn is None:
        from core.signal_detector import _judge_by_constraints
        judge_fn = _judge_by_constraints
    snap = snapshot_user_md()
    if not snap.get("ok"):
        return {"ok": False, "reason": snap.get("reason"), "removed": [], "backup": None, "kept": []}
    try:
        with open(_USER_MD_PATH, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError as e:
        logger.warning("profile_writer: 读 USER.md 失败: %s", e)
        return {"ok": False, "reason": "io_error", "removed": [], "backup": None, "kept": []}
    removed = []
    keep = []
    for i, ln in enumerate(lines):
        stripped = ln.strip()
        if stripped.startswith("- "):
            entry = stripped[2:].strip()
            try:
                res = judge_fn(entry)
                classify = res.get("classify", "") if isinstance(res, dict) else ""
            except Exception:
                classify = "profile"  # 判断异常 → 保守保留，不误删
            if classify in ("memory", "discard", "correction"):
                removed.append({"entry": entry, "classify": classify, "section": _section_of(lines, i)})
                continue  # 污染条目，删除
        keep.append(ln)
    if removed:
        if not _atomic_write_user_md(keep):
            return {"ok": False, "reason": "write_failed", "removed": removed,
                    "backup": snap.get("backup_path"), "kept": []}
        for r in removed:
            _append_version_snapshot({"ts": time.time(), "category": "cleanup",
                                      "entry": r["entry"], "diff": f"- {r['entry']}",
                                      "reason": "cleanup_pollution", "signal_source": "auto_detect"})
    kept_entries = [ln.strip()[2:] for ln in keep if ln.strip().startswith("- ")]
    return {"ok": True, "removed": removed, "kept": kept_entries, "backup": snap.get("backup_path")}
