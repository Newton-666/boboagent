# v5_memory.py — 知识库记忆系统（增强版：容量限制 + 原子写入 + 线程安全）
# 数据存储在 {BOBO_DATA_DIR}/ 下，不在项目目录中

import json
import os
import tempfile
import shutil
import threading
from datetime import datetime
from pathlib import Path

from config import BOBO_DATA_DIR

_MEMORY_DIR = BOBO_DATA_DIR
_MEMORY_DIR.mkdir(parents=True, exist_ok=True)


def _memory_db() -> str:
    """记忆库 JSON 路径：调用时从 BOBO_DATA_DIR 动态解析（TICKET-D2）。

    废除 import 时快照常量 MEMORY_DB——快照在测试 patch 目录后与
    实际读写裂脑（读 tmp、写真实 knowledge_base.json）。
    """
    return str(BOBO_DATA_DIR / "knowledge_base.json")


def _memory_backup() -> str:
    """记忆库备份路径：随 _memory_db() 动态派生。"""
    return _memory_db() + ".bak"

MAX_TOTAL_CHARS = 100000  # 总记忆字符限制（约 36k tokens）
MAX_SINGLE_ENTRY_CHARS = 5000  # 单条记忆字符限制

# ── 票 P0-1：记忆六类（v5_memory entry_type 规范化）────────────────────
# USER_PREF：用户画像（偏好/喜欢/习惯）——最高权重，注入优先级最高
# RULES：约束（要求/必须/禁止）——最高权重，不轻易淘汰
# FACT：事实决策（含 KEY_DECISION 归并）——默认兜底类
# ACHIEVEMENT：成果（完成/交付，存指针指向产物）
# LESSON：经验教训（教训/坑/原因）
# GOAL：用户目标（D1 定案：目标≠画像≠事实，Hermes 21.2）
MEMORY_TYPES = ("USER_PREF", "RULES", "FACT", "ACHIEVEMENT", "LESSON", "GOAL")

# 旧枚举 → 六类映射（KEY_DECISION 归并 FACT；OBSERVATION 属事实观察）
_LEGACY_TYPE_MAP = {
    "KEY_DECISION": "FACT",
    "OBSERVATION": "FACT",
    "GENERAL": "FACT",
    "KNOWLEDGE": "FACT",
    "MEMORY": "FACT",
}


def normalize_type(entry_type) -> str:
    """票 P0-1：任意 entry_type 收敛到六类枚举之一。

    规则：六类直接命中；旧枚举（KEY_DECISION/OBSERVATION/GENERAL/KNOWLEDGE/
    MEMORY）走 _LEGACY_TYPE_MAP；其余未知值兜底 FACT（不拒绝——LLM 乱传
    type 是常态，拒绝会丢记忆）。
    """
    t = str(entry_type or "").strip().upper().replace(" ", "_")
    if not t:
        return "FACT"
    if t in MEMORY_TYPES:
        return t
    if t in _LEGACY_TYPE_MAP:
        return _LEGACY_TYPE_MAP[t]
    # 模糊匹配：以合法类为前缀的变体（如 "USER_PREFERENCE" → USER_PREF）
    for m in MEMORY_TYPES:
        if m.startswith(t) or t.startswith(m):
            return m
    return "FACT"


# 读改写操作锁：并行 save_memory 调用时防止 lost-update（审计 #14）
_write_lock = threading.Lock()


def _atomic_save(data):
    """原子写入 JSON 文件（防止写入中断导致损坏）。同时保留 .bak 副本。"""
    dirname = os.path.dirname(_memory_db())
    if dirname:
        os.makedirs(dirname, exist_ok=True)
    # 写入前先备份现有数据，防止损坏后无恢复路径（审计 #14）
    if os.path.exists(_memory_db()):
        try:
            shutil.copy2(_memory_db(), _memory_backup())
        except Exception:
            pass
    fd, tmp_path = tempfile.mkstemp(dir=dirname or '.', suffix='.tmp', prefix='.mem_')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        shutil.move(tmp_path, _memory_db())
    except Exception:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
        raise
    # 票 LN-1：JSON 写成功后幂等重生成 MEMORY.md 镜像（失败静默降级，绝不影响主流程）
    try:
        from tools.memory_mirror import sync_mirror
        sync_mirror()
    except Exception:
        pass


def _load():
    """加载知识库。JSON 损坏时不静默返回空结构，避免下次 _save 覆写清空（审计 #14）。"""
    if not os.path.exists(_memory_db()):
        return {'entries': [], 'folders': []}
    try:
        with open(_memory_db(), 'r', encoding='utf-8') as f:
            data = json.load(f)
            if 'entries' not in data:
                data = {'entries': [], 'folders': []}
            return data
    except Exception:
        # 损坏了 → 移到 .broken，尝试从 .bak 恢复
        broken_path = _memory_db() + ".broken." + datetime.now().strftime("%Y%m%d_%H%M%S")
        try:
            shutil.move(_memory_db(), broken_path)
            import sys
            print(f"  知识库文件损坏，已备份至 {broken_path}", file=sys.stderr)
        except Exception:
            pass
        if os.path.exists(_memory_backup()):
            try:
                with open(_memory_backup(), 'r', encoding='utf-8') as f:
                    data = json.load(f)
                shutil.copy2(_memory_backup(), _memory_db())
                import sys
                print(f"  已从备份恢复记忆", file=sys.stderr)
                if 'entries' not in data:
                    data = {'entries': [], 'folders': []}
                return data
            except Exception:
                pass
        return {'entries': [], 'folders': []}


def _get_total_chars(entries):
    """计算所有记忆的总字符数"""
    total = 0
    for entry in entries:
        total += len(entry.get("text", ""))
    return total


def _save(data):
    _atomic_save(data)


def _entry_age_days(entry):
    """计算条目自 last_matched（无则 timestamp）以来的墙钟天数。"""
    ref_str = entry.get("last_matched") or entry.get("timestamp", "")
    if not ref_str:
        return 0
    try:
        ref_dt = datetime.strptime(ref_str[:16], "%Y-%m-%d %H:%M")
        return (datetime.now() - ref_dt).days
    except (ValueError, TypeError):
        return 0


# ── 票 P0-5：偏好变更替换（确定性规则，零 LLM 淘汰判断）────────────────
# DISCUSSION 174-177 红线：淘汰判据不能纯 LLM（无锚点）。本票判据全部为
# 确定性字符串规则——同主题（共享显著子串）+ 语义反转关键词，可测试可复现。
_REVERSE_KEYWORDS = (
    "改为", "改成", "不再是", "不再", "不喜欢", "不喝", "不爱",
    "不要", "以后不",
)
# 停用词：两文本共享这些通用词不算同主题证据（防误替换）。
_STOPWORDS = (
    "用户", "偏好", "喜欢", "记忆", "知识", "我", "你", "他", "她", "它",
    "的", "了", "要", "是", "在", "从", "到", "对", "和", "与", "以及",
    "现在", "以后", "之前", "以前", "最后", "最终", "一直", "曾经",
    "这个", "那个", "一个", "一种", "一些", "东西", "内容", "信息",
    "方式", "风格", "模式", "设置", "希望", "需要", "要求", "觉得",
    "认为", "比较", "非常", "特别", "希望", "继续", "保持", "变成",
    "开始", "选择", "使用", "采用", "采取", "进行", "完成", "实现",
)


def _shared_salient_token(text_a: str, text_b: str):
    """确定性同主题判定：两文本共享 ≥3 字符的非停用词连续子串。

    规则（可测试，零 LLM）：
      1. 短文本取 3..8 字符滑动窗口，全部子串入 set；
      2. 与长文本做包含匹配（子串 in 长文本），按长度降序取第一个；
      3. 排除停用词 / 反转关键词（"改为""不喜"等碎片不算主题证据）；
      4. 纯数字子串不算。
    返回显著子串（None = 不同主题）。专有名词（冰美式/dirty/emoji）天然命中，
    通用词（用户/偏好/喜欢）被停用词排除——"同主题但不反转"不会误判。
    """
    if not text_a or not text_b:
        return None
    short, long_text = (text_a, text_b) if len(text_a) <= len(text_b) else (text_b, text_a)
    n = len(short)
    max_w = min(8, n)
    for wlen in range(max_w, 2, -1):  # 8→3，取最长匹配
        for i in range(n - wlen + 1):
            sub = short[i:i + wlen]
            if sub in long_text and sub not in _STOPWORDS:
                if sub.isdigit():
                    continue
                if any(k in sub for k in _REVERSE_KEYWORDS):
                    continue  # 反转关键词碎片（"不喜"/"改为"）不算主题词
                return sub
    return None


def _detect_replace(data: dict, new_text: str):
    """偏好变更替换检测：新文本含反转关键词 + 与某非归档旧条同主题。

    确定性：按 id 升序遍历，取**最后一个**匹配（= 最近写入的旧条）。
    返回旧条 id（None = 不替换）。
    """
    if not any(k in new_text for k in _REVERSE_KEYWORDS):
        return None
    replaced = None
    for e in data.get("entries", []):
        if e.get("archived", False):
            continue
        old_text = e.get("text", "") or ""
        if not old_text.strip() or old_text.strip() == new_text.strip():
            continue
        if _shared_salient_token(old_text, new_text):
            replaced = e.get("id")
    return replaced


def _emit_changed(action: str, entry_id, extra: dict | None = None):
    """票 P0-5：记忆变更事件 → event_bus（引擎日志总线，可观测）。

    living_notes._emit 同款注入模式：失败静默降级，记忆写入是主路径、
    事件是旁路。前端实时广播由 gateway handler 层（server_utils.emit）负责。
    """
    try:
        from core.event_bus import event_bus as _ebus
        data = {
            "action": action,
            "entry_id": entry_id,
            "changed_at": datetime.now().isoformat(timespec="seconds"),
        }
        if extra:
            data.update(extra)
        _ebus.write("memory.changed", data)
    except Exception:
        pass


def add_entry(text, entry_type="general", tags=None, folder=""):
    """添加记忆条目（带容量检查 + 票 P0-5 偏好变更替换）。

    票 P0-1：entry_type 经 normalize_type 收敛到六类枚举（USER_PREF/RULES/
    FACT/ACHIEVEMENT/LESSON/GOAL），旧枚举与未知值不再原样入库。
    票 P0-5：同主题 + 反转关键词 → 旧条 archived+signal_score 归零（物理
    不删，可回溯）+ 新条写入 + 审计 REPLACE + memory.changed 事件。
    """
    if not text or not text.strip():
        return None
    
    entry_type = normalize_type(entry_type)
    # 单条记忆长度检查
    if len(text) > MAX_SINGLE_ENTRY_CHARS:
        print(f"⚠️ 记忆太长 ({len(text)} 字符)，已截断至 {MAX_SINGLE_ENTRY_CHARS}")
        text = text[:MAX_SINGLE_ENTRY_CHARS] + "\n...[截断]"
    
    data = _load()
    entries = data.get('entries', [])
    
    # 检查是否已存在相同内容
    for e in entries:
        if e.get("text", "").strip() == text.strip():
            return e
    
    # 容量检查
    current_chars = _get_total_chars(entries)
    new_chars = current_chars + len(text)
    
    if new_chars > MAX_TOTAL_CHARS:
        print(f"⚠️ 记忆已满 ({current_chars}/{MAX_TOTAL_CHARS} 字符)，无法添加新记忆")
        print(f"   💡 请删除一些旧记忆后再试")
        return None
    
    # ID 用当前最大值 +1，避免删除后重复（审计 #14）
    entry_id = max((e.get("id", 0) for e in entries), default=0) + 1
    entry = {
        "id": entry_id,
        "text": text,
        "type": entry_type,
        "tags": tags or [],
        "folder": folder,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "signal_score": 100,  # 信号分：初始 100，引用 +10，忽略 -5，< 20 不再注入
        "last_matched": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "last_time_decay": "",  # 上次时间衰减日期（YYYY-MM-DD），幂等控制
        "archived": False,      # 归档后不再注入（不删除，可回溯）
        "is_draft": False,      # 草稿条目，满足条件时自动归档
    }
    # 票 P0-5：偏好变更替换检测（确定性规则，零 LLM）——旧条归档 + 新条写入
    replaced_id = _detect_replace(data, text)
    if replaced_id is not None:
        old_text = ""
        for e in entries:
            if e.get("id") == replaced_id:
                old_text = e.get("text", "") or ""
                e["archived"] = True
                e["signal_score"] = 0  # 偏好反转 = 彻底失效，一次到位（非 5 分小降）
                e["replaced_by"] = entry_id
                e["replaced_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                break
        _audit_log("REPLACE", replaced_id,
                   f"from_id={replaced_id} to_id={entry_id} "
                   f"text={old_text[:60]!r} → {text[:60]!r}")
    entries.append(entry)
    data['entries'] = entries
    _save(data)
    if replaced_id is not None:
        _emit_changed("replace", entry_id, {"from_id": replaced_id})
    else:
        _emit_changed("add", entry_id)
    return entry


def delete_entry(entry_id, reason=None):
    """删除记忆条目（要求说明原因）"""
    if reason not in ["absorbed", "stale", "user_request"]:
        return {"error": "请说明删除原因: absorbed/stale/user_request"}
    with _write_lock:
        data = _load()
        entries = data.get('entries', [])
        for i, e in enumerate(entries):
            if e.get('id') == entry_id:
                removed = entries.pop(i)
                data['entries'] = entries
                _save(data)
                return {"success": True, "removed": removed, "reason": reason}
        return {"error": f"未找到 ID: {entry_id}"}


def get_memory_stats():
    """获取记忆统计信息"""
    data = _load()
    entries = data.get('entries', [])
    total_chars = _get_total_chars(entries)
    return {
        "total_entries": len(entries),
        "total_chars": total_chars,
        "max_chars": MAX_TOTAL_CHARS,
        "usage_percent": round(total_chars / MAX_TOTAL_CHARS * 100, 1) if MAX_TOTAL_CHARS > 0 else 0,
        "max_entry_chars": MAX_SINGLE_ENTRY_CHARS
    }


def get_all():
    return _load()


def get_entries():
    return _load()['entries']


def get_folders():
    return _load().get('folders', [])


def add_folder(name):
    data = _load()
    if name not in data.get('folders', []):
        data['folders'].append(name)
        _save(data)
    return name


def rename_folder(old_name, new_name):
    data = _load()
    if old_name in data.get('folders', []):
        data['folders'].remove(old_name)
        data['folders'].append(new_name)
    for e in data['entries']:
        if e.get('folder') == old_name:
            e['folder'] = new_name
    _save(data)
    return new_name


def delete_folder(name):
    data = _load()
    if name in data.get('folders', []):
        data['folders'].remove(name)
    for e in data['entries']:
        if e.get('folder') == name:
            e['folder'] = ""
    _save(data)


def move_to_folder(entry_id, folder_name):
    with _write_lock:
        data = _load()
        for e in data['entries']:
            if e.get('id') == entry_id:
                e['folder'] = folder_name
                _save(data)
                return True
        return False


def update_entry(entry_id, new_text):
    """更新条目内容（带容量检查）"""
    if len(new_text) > MAX_SINGLE_ENTRY_CHARS:
        return {"error": f"更新内容太长 ({len(new_text)} 字符)，超过限制 {MAX_SINGLE_ENTRY_CHARS}"}
    with _write_lock:
        data = _load()
        for e in data['entries']:
            if e.get('id') == entry_id:
                old_text = e['text']
                e['text'] = new_text
                e['timestamp'] = datetime.now().strftime("%Y-%m-%d %H:%M")
                # 重新计算总字符数
                total = _get_total_chars(data['entries'])
                if total > MAX_TOTAL_CHARS:
                    e['text'] = old_text
                    return {"error": f"更新后记忆总容量 ({total}) 超过限制 ({MAX_TOTAL_CHARS})"}
                _save(data)
                return {"success": True, "entry": e}
        return {"error": f"未找到 ID: {entry_id}"}


def search_knowledge_base(query):
    """搜索知识库"""
    data = _load()
    entries = data.get('entries', [])
    query_lower = query.lower()
    
    results = []
    for e in entries:
        text = e.get("text", "")
        if query_lower in text.lower():
            results.append(e)
    
    if not results:
        return "未找到相关记忆"
    
    output = f"找到 {len(results)} 条相关记忆:\n"
    for e in results:
        text = e['text'][:100]
        output += f"  [{e['id']}] {text}\n"
    return output


def save_to_knowledge_base(content, entry_type="general", **kwargs):
    """保存内容到知识库（供工具调用）。

    支持 target="profile" 路由到用户资料（kwargs 中可含 memory_type 作为 profile key）。
    """
    target = kwargs.get("target", "memory")
    if target == "profile":
        key = kwargs.get("memory_type", "") or "unnamed"
        return save_user_profile(key, content)
    with _write_lock:
        entry = add_entry(content, entry_type)
        if entry:
            return f"已保存到知识库 (ID: {entry['id']})"
        return "保存失败"


def save_user_profile(key: str, value: str) -> str:
    """Save or update a user profile entry."""
    data = _load()
    if "profile" not in data:
        data["profile"] = {}
    data["profile"][key] = {"value": value, "updated": datetime.now().isoformat()}
    _save(data)
    return f"用户资料已更新: {key} = {value}"


def get_user_profile() -> dict:
    """Return all user profile entries."""
    data = _load()
    return data.get("profile", {})


def format_user_profile() -> str:
    """Format user profile for system prompt injection."""
    profile = get_user_profile()
    if not profile:
        return ""
    lines = []
    for key, entry in sorted(profile.items()):
        lines.append(f"  {key}: {entry['value']}")
    return "用户资料:\n" + "\n".join(lines)


def format_all_memory(max_chars: int = 5000) -> str:
    """Format all memory entries for system prompt injection (up to max_chars)."""
    data = _load()
    entries = data.get("entries", [])
    if not entries:
        return ""
    # Sort by recency (newest first): 写入键是 timestamp 不是 created_at
    sorted_entries = sorted(entries, key=lambda e: e.get("timestamp", ""), reverse=True)
    lines = []
    total = 0
    for e in sorted_entries:
        text = e.get("text", "").strip()
        if not text:
            continue
        text_truncated = text[:200] + ("..." if len(text) > 200 else "")
        entry = f"  - {text_truncated}"
        if total + len(entry) + 1 > max_chars:
            break
        lines.append(entry)
        total += len(entry) + 1
    if not lines:
        return ""
    total_all = len(entries)
    shown = len(lines)
    header = f"记忆 ({shown}/{total_all} 条, {total:,}/{max_chars:,} 字符)"
    return header + "\n" + "\n".join(lines)


def format_memory_by_signal(max_chars: int = 2500, min_chars: int = 1000) -> tuple[str, dict]:
    """票 LN-4：按信号分降序注入记忆（分段保底 + 信号淘汰）。

    与 format_all_memory 的区别：
      - 排序键是 signal_score（降序，同分按时间新→旧），不是纯时间
      - 已归档 / 信号分 < 20 的条目永不注入（自然下沉语义，同 get_top_memories）
      - 返回 (text, stats)，stats 供 prompt.budget 监控事件使用：
          {"entries": 注入条数, "total_entries": 总条数, "evicted": 信号合格但超预算被淘汰数}
      - max_chars 上限（天花板 2500）；min_chars 保底语义：记忆充足时至少注入
        min_chars 字符（由独立段落 + 上限控制自然满足，参数保留供调用方文档化）
    """
    data = _load()
    entries = data.get("entries", [])
    if not entries:
        return "", {"entries": 0, "total_entries": 0, "evicted": 0}
    total_all = len(entries)
    # 过滤：归档 + 低信号永不注入
    eligible = [
        e for e in entries
        if not e.get("archived", False)
        and e.get("signal_score", 100) >= 20
        and (e.get("text") or "").strip()
    ]
    if not eligible:
        return "", {"entries": 0, "total_entries": total_all, "evicted": 0}
    # 信号降序，同分按时间新→旧
    eligible.sort(
        key=lambda e: (e.get("signal_score", 100), e.get("timestamp", "")),
        reverse=True,
    )
    lines = []
    total = 0
    evicted = 0
    for e in eligible:
        text = e.get("text", "").strip()
        text_truncated = text[:200] + ("..." if len(text) > 200 else "")
        entry = f"  - {text_truncated}"
        if total + len(entry) + 1 > max_chars:
            # 剩余合格条目因超预算被淘汰
            evicted = len(eligible) - len(lines)
            break
        lines.append(entry)
        total += len(entry) + 1
    shown = len(lines)
    if not lines:
        return "", {"entries": 0, "total_entries": total_all,
                    "evicted": len(eligible)}
    header = f"记忆 ({shown}/{total_all} 条, {total:,}/{max_chars:,} 字符)"
    return header + "\n" + "\n".join(lines), {
        "entries": shown, "total_entries": total_all, "evicted": evicted}


# ── 信号分系统：引用强化 + 忽略衰减 + 自然下沉 ──────────────────

def bump_signal(entry_id: int, delta: int = 10):
    """记忆被 LLM 引用时加分；被注入但未引用时减分（传负值）。"""
    with _write_lock:
        data = _load()
        for e in data.get("entries", []):
            if e.get("id") == entry_id:
                e["signal_score"] = max(0, min(200, e.get("signal_score", 100) + delta))
                e["last_matched"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                _save(data)
                return e["signal_score"]
    return None


def get_top_memories(query: str = "", limit: int = 3) -> list:
    """返回信号分最高的记忆条目（可选 query 过滤），用于 Top-N 注入。"""
    data = _load()
    entries = data.get("entries", [])
    query_lower = query.lower() if query else ""
    scored = []
    for e in entries:
        if e.get("archived", False):
            continue  # 已归档：不再注入
        score = e.get("signal_score", 100)
        if score < 20:
            continue  # 自然下沉：低分的永不注入
        relevance = 1.0
        if query_lower:
            text_lower = e.get("text", "").lower()
            if query_lower in text_lower:
                relevance = 2.0  # 关键词匹配加权
            else:
                words = set(query_lower.split())
                text_words = set(text_lower.split())
                overlap = len(words & text_words)
                if overlap > 0:
                    relevance = 1.0 + overlap * 0.5  # 词重叠加权
                else:
                    relevance = 0.0  # 完全不相关 → 跳过
        if relevance <= 0:
            continue
        scored.append((e, score * relevance))
    scored.sort(key=lambda x: x[1], reverse=True)
    # 附加墙钟年龄元数据，供调用方（如 proactive）做时效标注
    for e, _ in scored[:limit]:
        e["_age_days"] = _entry_age_days(e)
    return [e for e, _ in scored[:limit]]


def decay_all(decay: int = -5):
    """对所有未被最近匹配到的记忆做信号衰减（每次 LLM 调用后运行）。"""
    with _write_lock:
        data = _load()
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        for e in data.get("entries", []):
            # 票 LN-1：人手编辑条目豁免轮次衰减（用户手写记忆不随时间贬值）
            if e.get("human_edited", False):
                continue
            last = e.get("last_matched", e.get("timestamp", ""))
            if last < now[:16]:  # 本轮未被匹配到（last_matched 没更新）
                e["signal_score"] = max(0, e.get("signal_score", 100) + decay)
        _save(data)


def time_decay():
    """时间衰减：基于墙钟年龄扣分，与轮次衰减 decay_all 并存。

    档位（理由见 commit message）：
    - < 7 天：不衰减（一周内的知识视为新鲜）
    - 7-29 天：-5/次（每天最多一次，温和下坡）
    - ≥ 30 天：-10/次（加速遗忘，一个月未引用的知识大概率过时）

    幂等：同日重复调用不重复扣分（last_time_decay 记录日期）。
    下限保护：signal_score 不低于 0，且 < 20 的条目本就不注入（语义一致）。

    副作用：自动归档满足条件的草稿（is_draft + ≥7 天未被 bump + 分 ≤30）。
    """
    today = datetime.now().strftime("%Y-%m-%d")
    with _write_lock:
        data = _load()
        for e in data.get("entries", []):
            if e.get("archived", False):
                continue
            # 票 LN-1：人手编辑条目豁免时间衰减与草稿自动归档
            if e.get("human_edited", False):
                continue

            # ── 时间衰减 ──
            lt = e.get("last_time_decay", "")
            if lt == today:
                continue  # 幂等：今天已处理过

            age = _entry_age_days(e)
            penalty = 0
            if age >= 30:
                penalty = -10
            elif age >= 7:
                penalty = -5

            if penalty < 0:
                e["signal_score"] = max(0, e.get("signal_score", 100) + penalty)
                e["last_time_decay"] = today

            # ── 草稿生命周期 ──
            if e.get("is_draft", False):
                draft_age = _entry_age_days(e)
                if draft_age >= 7 and e.get("signal_score", 100) <= 30:
                    e["archived"] = True

        _save(data)


def memory_stats() -> dict:
    """返回记忆系统的统计指标。"""
    data = _load()
    entries = data.get("entries", [])
    total = len(entries)
    if total == 0:
        return {"total": 0, "high_signal_pct": 0, "avg_score": 0}
    high = sum(1 for e in entries if e.get("signal_score", 100) >= 50)
    avg = sum(e.get("signal_score", 100) for e in entries) / total
    return {
        "total": total,
        "high_signal_pct": round(high / total * 100, 1),
        "avg_score": round(avg, 1),
    }


# ── 票 P0-1：Memory 模块 RPC 支撑（六类分组 / 删除审计 / 改 type / 指针校验）────

_AUDIT_LOG = BOBO_DATA_DIR / "logs" / "memory_audit.log"


def _audit_log(action: str, entry_id, detail: str):
    """记忆变更审计日志（负面通道，P0-5 衔接）。写 data/logs/memory_audit.log。

    每次删除/改 type 都留痕：时间戳 + 动作 + 条目 id + 详情。
    """
    try:
        _AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(_AUDIT_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().isoformat(timespec='seconds')}] {action} id={entry_id} {detail}\n")
    except Exception:
        pass  # 审计失败静默降级，不阻塞主流程


def list_memories() -> dict:
    """票 P0-1：memory.list —— 六类分组 + 统计。

    返回结构：
      {"groups": {类名: {"count": n, "chars": c, "entries": [条目(不含全文?)]}},
       "stats": {"total_entries": n, "total_chars": c, "total_tokens_est": n,
                 "usage_percent": n}}
    token 估算 = chars / 4（中英混合经验值，精确预算 P2-3 另票）。
    """
    data = _load()
    entries = data.get("entries", [])
    groups = {t: {"count": 0, "chars": 0, "entries": []} for t in MEMORY_TYPES}
    total_chars = 0
    active_entries = 0
    for e in entries:
        # 票 P0-5：归档条目不进面板（REPLACE 旧条 archived → 前端快照对比
        # 自然显示红色删除；活记忆视图不含归档残留）
        if e.get("archived", False):
            continue
        active_entries += 1
        t = normalize_type(e.get("type"))
        txt = e.get("text", "") or ""
        total_chars += len(txt)
        g = groups[t]
        g["count"] += 1
        g["chars"] += len(txt)
        g["entries"].append({
            "id": e.get("id"),
            "text": txt[:120] + ("…" if len(txt) > 120 else ""),
            "full_len": len(txt),
            "signal_score": e.get("signal_score", 100),
            "archived": bool(e.get("archived", False)),
            "timestamp": e.get("timestamp", ""),
        })
    return {
        "groups": groups,
        "stats": {
            "total_entries": active_entries,
            "total_chars": total_chars,
            "total_tokens_est": round(total_chars / 4),
            "usage_percent": round(total_chars / MAX_TOTAL_CHARS * 100, 1) if MAX_TOTAL_CHARS > 0 else 0,
        },
    }


def delete_memory(entry_id, reason="user_request", source="gui") -> dict:
    """票 P0-1：memory.delete —— 删除条目 + 审计日志。

    复用 delete_entry 的删除语义（absorbed/stale/user_request 三原因校验），
    追加审计留痕。P0-5 负面通道衔接点。
    """
    if reason not in ("absorbed", "stale", "user_request"):
        return {"error": f"非法删除原因: {reason!r}（允许: absorbed/stale/user_request）"}
    with _write_lock:
        data = _load()
        entries = data.get("entries", [])
        for i, e in enumerate(entries):
            if e.get("id") == entry_id:
                removed = entries.pop(i)
                data["entries"] = entries
                _save(data)
                _audit_log("DELETE", entry_id,
                           f"reason={reason} source={source} text={removed.get('text','')[:80]!r}")
                _emit_changed("delete", entry_id, {"reason": reason, "source": source})
                return {"success": True, "removed": {"id": removed.get("id"), "type": removed.get("type")}}
        return {"error": f"未找到 ID: {entry_id}"}


def update_memory_type(entry_id, new_type, source="gui") -> dict:
    """票 P0-1：改条目 type（六类枚举校验）+ 审计日志。

    验收 d 需要（改 type 重新分组）。仅允许改 type，文本改动留给 P0-5。
    """
    new_type = normalize_type(new_type)
    with _write_lock:
        data = _load()
        for e in data.get("entries", []):
            if e.get("id") == entry_id:
                old_type = e.get("type")
                if old_type == new_type:
                    return {"success": True, "entry": {"id": entry_id, "type": new_type, "changed": False}}
                e["type"] = new_type
                _save(data)
                _audit_log("RETYPE", entry_id, f"from={old_type} to={new_type} source={source}")
                _emit_changed("retype", entry_id, {"from": old_type, "to": new_type})
                return {"success": True, "entry": {"id": entry_id, "type": new_type, "changed": True}}
        return {"error": f"未找到 ID: {entry_id}"}


def verify_memory_links() -> dict:
    """票 P0-1：指针可达性校验 —— 引用本地路径的条目定期校验，失效降权/标记。

    规则：text 中含绝对路径（/Users/...）或相对项目路径（library/、docs/、
    apps/ 等）的条目，取第一个路径校验 os.path.exists；失效 → 标记
    link_broken=True + signal_score 降 5（不低于 0，注入优先级下沉）。
    """
    import re
    data = _load()
    entries = data.get("entries", [])
    broken = []
    checked = 0
    changed = False
    path_re = re.compile(r"(?:/Users/[^\s,，;；）)]+|[A-Za-z0-9_./-]+/library/[^\s,，;；）)]+|library/[^\s,，;；）)]+|docs/[^\s,，;；）)]+)")
    for e in entries:
        txt = e.get("text", "") or ""
        m = path_re.search(txt)
        if not m:
            continue
        p = m.group(0).rstrip(".,:：;；")
        # 仅校验存在性；网络 URL 与模糊路径跳过
        if p.startswith(("http://", "https://", "~/")):
            continue
        if p.endswith((".py", ".js", ".md", ".json", ".html", ".cjs")) or "/" in p:
            checked += 1
            if not os.path.exists(p):
                broken.append({"id": e.get("id"), "path": p, "text": txt[:80]})
                if not e.get("link_broken", False):
                    e["link_broken"] = True
                    e["signal_score"] = max(0, e.get("signal_score", 100) - 5)
                    changed = True
    if changed:
        _save(data)
    return {"checked": checked, "broken": len(broken), "broken_entries": broken[:20]}


def register(reg):
    reg("save_memory", save_to_knowledge_base, {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": "Save info to memory (target=memory) or user profile (target=profile, memory_type=key).\nExamples:\n- save fact -> target=memory\n- save user name -> target=profile, memory_type=name",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string"},
                    "memory_type": {"type": "string", "description": "memory type or profile key name"},
                    "target": {"type": "string", "enum": ["memory", "profile"], "default": "memory"}
                },
                "required": ["content"]
            }
        }
    })

    reg("search_memory", search_knowledge_base, {
        "type": "function",
        "function": {
            "name": "search_memory",
            "description": "Search saved memories or user profile.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"]
            }
        }
    })
