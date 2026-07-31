# tools/memory_mirror.py — MEMORY.md 双向镜像（票 LN-1）
#
# 给 knowledge_base.json 配一个活人可读写的镜像 <项目根>/library/MEMORY.md。
# JSON 仍是运行时真源，md 是用户入口：bobo 记住的一切，用户翻开就能读、动手就能改。
#
# 同步规则（照抄 LIVING_NOTES_DESIGN.md Q3 补，不得走样）：
#   1. JSON→md：add_entry / 覆盖 / 删除 / 信号分变动后，幂等全量重生成镜像
#      （禁增量 patch）。写失败静默降级记 WARNING，不得影响记忆主流程。
#   2. md→JSON：bobo 启动时（engine_adapter 初始化处）比对 mtime，
#      md 比 JSON 新 → 解析回 JSON。导入前自动备份 knowledge_base.json.bak。
#   3. 保守降级：md 解析失败 → 跳过导入 + logger.warning +
#      事件 memory.mirror_import_failed，JSON 原样不动。
#   4. 人手标记：从 md 导入或 md 中新增的条目打 human_edited: true，
#      镜像行尾标 · 人手；信号分自动衰减、草稿自动归档对这类条目豁免。
#   5. md 中用户新增的条目（无 #id 的行）→ 分配新 id 导入，
#      时间/信号字段缺省给默认值（时间=导入时刻，信号=100）。
#
# 只做镜像层。主题笔记、index.md、蒸馏晋升（LN-2/3）不在此文件。
# 库址铁律：library/ 必须在项目根目录一级，禁止嵌套进 data/、docs/ 等子目录。

import json
import logging
import os
import re
import shutil
import tempfile
import threading
from datetime import datetime
from pathlib import Path

from config import BOBO_DATA_DIR

logger = logging.getLogger("bobo.memory_mirror")

# ── 路径 ──
# JSON 真源（与 tools/v5_memory.py 的 MEMORY_DB 保持一致）
MEMORY_DB = str(BOBO_DATA_DIR / "knowledge_base.json")
_MEMORY_BACKUP = MEMORY_DB + ".bak"

# 镜像库址：项目根一级（用户铁律）
_REPO_ROOT = Path(__file__).resolve().parent.parent
LIBRARY_DIR = _REPO_ROOT / "library"
MIRROR_PATH = LIBRARY_DIR / "MEMORY.md"

_IMPORT_LOCK = threading.Lock()

# ── 行格式 ──
# 带 id：   - [#12] 用户偏好用中文交流 (2026-07-20 · 信号 85 · 草稿 · 人手)
# 无 id：   - 我手写的记忆（用户新增，分配新 id 导入）
_LINE_WITH_ID = re.compile(
    r"^\s*-\s*\[#(\d+)\]\s*(.+?)\s*(?:\((.*)\))?\s*$"
)
_LINE_WITHOUT_ID = re.compile(r"^\s*-\s*(.+?)\s*$")
_HEADING_RE = re.compile(r"^\s*#")
_COMMENT_RE = re.compile(r"^\s*<!--")


# ── 渲染（JSON → md）──────────────────────────────

def _render_md(data: dict) -> str:
    """把 JSON 全量渲染为 MEMORY.md（幂等：同输入必同输出）。

    按 type 分小节，每条一行，锚点 = JSON 的 id。
    已归档（archived）条目不渲染——归档即不再注入，镜像也不展示。
    """
    entries = data.get("entries", [])
    active = [e for e in entries if not e.get("archived", False)]
    # 按 type 分组；空值归 general
    groups: dict[str, list] = {}
    for e in active:
        t = e.get("type", "general") or "general"
        groups.setdefault(t, []).append(e)

    lines = [
        "# MEMORY.md — bobo 的记忆（可手改，下次启动生效）",
        "<!-- AUTO-SYNC: 本文件与 knowledge_base.json 双向同步 -->",
        "",
    ]
    for t in sorted(groups.keys()):
        lines.append(f"## {t}")
        for e in sorted(groups[t], key=lambda x: x.get("id", 0)):
            lines.append(_format_entry_line(e))
        lines.append("")
    return "\n".join(lines)


def _format_entry_line(e: dict) -> str:
    """单条记忆 → 一行镜像文本。

    格式：- [#id] text (YYYY-MM-DD · 信号 N [· 草稿] [· 人手])
    text 内换行替换为空格（镜像一行一条的固有约束）。
    """
    eid = e.get("id", 0)
    text = (e.get("text", "") or "").replace("\n", " ").strip()
    date = (e.get("timestamp", "") or "")[:10]
    signal = e.get("signal_score", 100)
    meta = []
    if date:
        meta.append(date)
    meta.append(f"信号 {signal}")
    if e.get("is_draft", False):
        meta.append("草稿")
    if e.get("human_edited", False):
        meta.append("人手")
    meta_str = f" ({' · '.join(meta)})" if meta else ""
    return f"- [#{eid}] {text}{meta_str}"


# ── 解析（md → JSON）──────────────────────────────

def _parse_meta(meta_raw: str):
    """解析 (2026-07-20 · 信号 85 · 草稿 · 人手) → (signal, draft, human)。"""
    signal = None
    draft = False
    human = False
    for seg in [s.strip() for s in meta_raw.split("·") if s.strip()]:
        if seg == "草稿":
            draft = True
        elif seg == "人手":
            human = True
        elif seg.startswith("信号"):
            try:
                signal = int(seg.replace("信号", "").strip())
            except ValueError:
                pass
    return signal, draft, human


def _parse_md(content: str) -> list[dict]:
    """解析 MEMORY.md → 条目变更列表。

    返回 [{"id": int|None, "text": str, "type": str,
            "signal": int|None, "draft": bool, "human": bool}, ...]

    格式被改坏（乱格式）→ 抛 ValueError，调用方保守降级（JSON 原样不动）。
    """
    result = []
    current_type = "general"
    for raw in content.splitlines():
        line = raw.rstrip("\n").strip()
        if not line:
            continue
        if _COMMENT_RE.match(line):
            continue
        if _HEADING_RE.match(line):
            if line.startswith("##"):
                current_type = line[2:].strip() or "general"
            continue
        m = _LINE_WITH_ID.match(line)
        if m:
            eid = int(m.group(1))
            text = m.group(2).strip()
            signal, draft, human = _parse_meta(m.group(3) or "")
            result.append({
                "id": eid, "text": text, "type": current_type,
                "signal": signal, "draft": draft, "human": human,
            })
            continue
        if "[#" in line:
            # 带 [# 却匹配不上（id 非数字 / 括号不闭合 / 锚点损坏）→ 乱格式
            raise ValueError(f"bad mirror line: {line!r}")
        m2 = _LINE_WITHOUT_ID.match(line)
        if m2:
            text = m2.group(1).strip()
            result.append({
                "id": None, "text": text, "type": current_type,
                "signal": None, "draft": False, "human": True,
            })
            continue
        # 其他无法识别的行 → 乱格式
        raise ValueError(f"unrecognized mirror line: {line!r}")
    return result


def _apply_changes(data: dict, changes: list) -> int:
    """把解析出的变更应用到 JSON 数据，返回变更条目数。

    - 有 id → 按 #id 精确匹配，更新 text + 打 human_edited: true。
      id 不存在 → 跳过该行（保守：不新增不报错，记 WARNING）。
    - 无 id → 分配新 id 导入（信号缺省 100，时间=导入时刻，human_edited）。
    """
    entries = data.setdefault("entries", [])
    by_id = {e.get("id"): e for e in entries}
    n = 0
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    for c in changes:
        if c["id"] is not None:
            e = by_id.get(c["id"])
            if e is None:
                logger.warning(
                    "memory mirror import: id %s not in JSON, line skipped", c["id"]
                )
                continue
            if e.get("text", "") != c["text"]:
                e["text"] = c["text"]
                e["human_edited"] = True
                n += 1
        else:
            new_id = max((x.get("id", 0) for x in entries), default=0) + 1
            entries.append({
                "id": new_id,
                "text": c["text"],
                "type": c["type"],
                "tags": [],
                "folder": "",
                "timestamp": now,
                "signal_score": c["signal"] if c["signal"] is not None else 100,
                "last_matched": now,
                "last_time_decay": "",
                "archived": False,
                "is_draft": c["draft"],
                "human_edited": True,
            })
            n += 1
    return n


def _write_json(data: dict):
    """原子写 JSON（导入专用，不调 v5_memory._save，避免嵌套 sync_mirror）。"""
    dirname = os.path.dirname(MEMORY_DB)
    if dirname:
        os.makedirs(dirname, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=dirname or ".", suffix=".tmp", prefix=".mir_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        shutil.move(tmp_path, MEMORY_DB)
    except Exception:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
        raise


def _align_mtime():
    """导入完成后把 md 的 mtime 对齐到 JSON 写入时刻。

    防止下次启动时 md 仍比 JSON 新 → 重复导入（幂等前提：镜像收敛）。
    """
    try:
        if os.path.exists(MEMORY_DB) and MIRROR_PATH.exists():
            t = os.stat(MEMORY_DB).st_mtime
            os.utime(MIRROR_PATH, (t, t))
    except Exception:
        pass


def _emit(event_type: str, data: dict):
    """事件埋点。写失败静默，绝不影响主流程。"""
    try:
        from core.event_bus import event_bus as _ebus
        _ebus.write(event_type, data)
    except Exception:
        pass


# ── 对外 API ─────────────────────────────────────

def sync_mirror() -> bool:
    """JSON → md：幂等全量重生成镜像。

    写失败静默降级记 WARNING，不影响记忆主流程。
    幂等关键：内容未变时跳过写入、不刷新 mtime（防止启动导入误判 md 更新）。
    返回 True=写入成功或内容未变；False=降级失败。
    """
    try:
        if not os.path.exists(MEMORY_DB):
            return True
        with open(MEMORY_DB, "r", encoding="utf-8") as f:
            data = json.load(f)
        content = _render_md(data)
        LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
        if MIRROR_PATH.exists():
            try:
                if MIRROR_PATH.read_text(encoding="utf-8") == content:
                    return True  # 幂等：内容相同不刷新 mtime
            except Exception:
                pass
        MIRROR_PATH.write_text(content, encoding="utf-8")
        active = [e for e in data.get("entries", []) if not e.get("archived", False)]
        _emit("memory.mirror_write", {"entry_count": len(active)})
        return True
    except Exception:
        logger.warning("memory mirror write failed (silent degrade)", exc_info=True)
        return False


def import_from_md() -> int:
    """md → JSON：bobo 启动时调用（engine_adapter 初始化处）。

    触发条件：md 比 JSON 新（用户手改过）。
    - 解析成功 → 更新/新增条目（human_edited: true），导入前备份 .bak，
      事件 memory.mirror_import（带变更条目数）。
    - 解析失败（乱格式）→ 跳过导入 + logger.warning +
      事件 memory.mirror_import_failed，JSON 原样不动（保守降级）。

    返回变更条目数；0=未触发；-1=失败降级。
    """
    with _IMPORT_LOCK:
        try:
            if not MIRROR_PATH.exists():
                return 0
            md_mtime = MIRROR_PATH.stat().st_mtime
            if os.path.exists(MEMORY_DB):
                json_mtime = os.stat(MEMORY_DB).st_mtime
                if md_mtime <= json_mtime:
                    return 0  # md 不比 JSON 新 → 无用户手改
            # 导入前自动备份（保留最近一次）
            if os.path.exists(MEMORY_DB):
                try:
                    shutil.copy2(MEMORY_DB, _MEMORY_BACKUP)
                except Exception:
                    pass
            with open(MEMORY_DB, "r", encoding="utf-8") as f:
                data = json.load(f)
            try:
                with open(MIRROR_PATH, "r", encoding="utf-8") as f:
                    changes = _parse_md(f.read())
            except ValueError:
                logger.warning(
                    "memory mirror import failed: 解析失败，JSON 原样不动（保守降级）",
                    exc_info=True,
                )
                _emit("memory.mirror_import_failed", {"reason": "parse_error"})
                return -1
            n = _apply_changes(data, changes)
            # 写回 JSON（不调 v5_memory._save，避免嵌套 sync_mirror）
            _write_json(data)
            # 重生成镜像：让 md 与 JSON 收敛；随后对齐 mtime 防重复导入
            sync_mirror()
            _align_mtime()
            _emit("memory.mirror_import", {"changed": n})
            return n
        except Exception:
            logger.warning("memory mirror import error (silent)", exc_info=True)
            return -1
