# tools/living_notes.py — 主题笔记（票 LN-2 + LN-2R 重写机制）
#
# 收工时（RESPONDING，takeaways 非空才触发）自动把本轮要点写进
# library/<领域>/<主题>.md 主题笔记，并维护 library/index.md 目录。
#
# 铁律：
#   - 新主题：建骨架笔记（frontmatter + 五章节骨架）。
#   - 已有主题：骨架重写式——旧版快照进 library/.history/，拿【旧笔记全文 + 本轮要点】
#     让 LLM 输出整篇新笔记（合并/去重/重构/删旧结论，新信息进对应章节）。
#     时间线小节保留追加性（每轮一行 `- HH:MM 要点`），其余章节全量进化。
#   - 结构校验三拒（缺 frontmatter / 正文空 / 新 < 旧 30%）→ 拒写、保留旧版、发 notes.error。
#   - 人手段落（`· 人手` 行 / `> 用户修订` 引用块）逐字保护，重写后硬校验。
#   - 全程最多 2 次 LLM 调用（主题判定 1 次 + 重写 1 次，成本闸保留）。
#   - 总开关 BOBO_LIVING_NOTES=off 整体关闭，零动作。
#   - 所有失败静默降级记 WARNING + notes.error 事件，绝不阻塞收工。
#
# 命名铁律（Q2）：主题 ≤12 字人话，禁日期/session 前缀；文件名净化 /\:*?"<>|。
# 误判代价：误并 > 误分（误分体检能发现，误并毁笔记）→ match 拿不准必须 null。

import json
import logging
import os
import re
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("bobo.living_notes")

# ── 库址（用户铁律：项目根一级，禁止嵌套）──
_REPO_ROOT = Path(__file__).resolve().parent.parent
LIBRARY_DIR = _REPO_ROOT / "library"
INDEX_PATH = LIBRARY_DIR / "index.md"

# 总开关
_ENV_OFF = "BOBO_LIVING_NOTES"

# 固定骨架章节（LN-2R：所有主题笔记统一）
_SKELETON_SECTIONS = ["概述", "关键结论", "决策与原因", "待办与未决", "时间线"]

# 人手段落保护（LN-2R：逐字保留，不许改）
_HUMAN_MARK = re.compile(r"^.*·\s*人手\s*$")
_USER_REV_START = re.compile(r"^>\s*用户修订")

# 重写 LLM 的 system prompt（LN-2S：改吃完整回复全文 + 密度铁律）
_REWRITE_SYSTEM = """你是活体知识库的笔记重写器。把【旧笔记全文】与【本轮完整回复】合并为整篇新笔记。

固定骨架（所有主题笔记统一）：
---
topic: <主题>
domain: <领域>
created: YYYY-MM-DD
last_touched: YYYY-MM-DD
version: <int>
source_sessions: [<session_id>...]
---

## 概述
## 关键结论
## 决策与原因
## 待办与未决
## 时间线

规则：
1. 新内容与旧结论冲突 → 用新结论替换旧表述，不要两句并列。
2. 旧章节缺少新内容相关信息 → 追加进对应章节（不是文末堆）。
3. 与本轮无关的旧内容 → 原样保留。
4. 标有「· 人手」后缀的行 / 「> 用户修订」引用块 → 逐字保留，不许改。
5. ## 时间线 保留追加性质：旧时间线行原样保留，本轮追加一行「- HH:MM 要点」。
6. 空章节直接删掉，不留空标题。
7. frontmatter 只输出 topic/domain/created 三项；version/last_touched/source_sessions 由系统维护，不要输出。

密度铁律（LN-2S，最高优先级）：
- 笔记的信息量必须 ≥ 本轮回复。回复中的公式、代码、参数、结论、推理链、待办，
  一个都不许丢——你的任务是**组织**它们进骨架章节，不是缩略它们。
- 宁多勿少：拿不准是否该记的，记进对应章节。
- 过程花絮（如"Bobo承认表述混淆"这类元对话）→ 进时间线或丢弃，不进正文。
只输出整篇 markdown 笔记，不要任何其他文字。"""

# 新主题成文 LLM 的 system prompt（LN-2S：首轮笔记也要 1 次 LLM 成文，不做免成文捷径）
_NEW_NOTE_SYSTEM = """你是活体知识库的笔记起草器。把【本轮完整回复】组织为整篇骨架笔记。

固定骨架（所有主题笔记统一）：
---
topic: <主题>
domain: <领域>
created: YYYY-MM-DD
---

## 概述
## 关键结论
## 决策与原因
## 待办与未决
## 时间线

规则：
1. 概述：把回复的核心内容展开成多句完整表述，不是单行要点。
2. 关键结论/决策与原因/待办与未决：按内容归位，回复里的结论、决策、参数、待办一个都不许丢。
3. 时间线：写一行「- HH:MM 本轮主题一句话」。
4. 空章节直接删掉，不留空标题。
5. frontmatter 只输出 topic/domain/created 三项；version/last_touched/source_sessions 由系统维护，不要输出。

密度铁律（LN-2S，最高优先级）：
- 笔记的信息量必须 ≥ 本轮回复。回复中的公式、代码、参数、结论、推理链、待办，
  一个都不许丢——你的任务是**组织**它们进骨架章节，不是缩略它们。
- 宁多勿少：拿不准是否该记的，记进对应章节。
- 过程花絮（如"Bobo承认表述混淆"这类元对话）→ 进时间线或丢弃，不进正文。
只输出整篇 markdown 笔记，不要任何其他文字。"""

# 防爆 token：完整回复超过此长度才截断（记 notes.error truncated=true）
_MAX_REPLY_CHARS = 32000

# 主题名净化：非法字符 + 首尾空格
_ILLEGAL_CHARS = re.compile(r'[/\\:*?"<>|]')
_WHITESPACE = re.compile(r"\s+")

# 主题判定的 system prompt
_JUDGE_SYSTEM = """你是活体知识库的图书管理员。给你：本轮要点、用户最近消息、现有主题清单。
任务：决定这些要点该写进哪个主题笔记，并写成 markdown 小节。

规则：
1. topic：≤12 字主题短语，人话（中文对话起中文名），禁日期/session id/下划线机翻风。
2. domain：领域文件夹名（如 agent开发、电商调研、生活），≤8 字。
3. section：markdown 正文，1-3 条要点，每条 ≤80 字，用 "- " 列表。只写要点本身，
   不要写标题、不要写日期（日期由系统自动加）。
4. match：这些要点属于已有主题吗？拿不准必须返回 null（误分 > 误并）。

只输出 JSON，不要任何其他文字：
{"topic": "主题", "domain": "领域", "section": "- 要点1\\n- 要点2", "match": "已有主题名或null"}"""


def _emit(event_type: str, data: dict):
    """事件埋点。写失败静默，绝不影响主流程。"""
    try:
        from core.event_bus import event_bus as _ebus
        _ebus.write(event_type, data)
    except Exception:
        pass


def _sanitize_name(name: str) -> str:
    """净化主题/领域名：去非法字符 + 压缩空白 + 去首尾空格。"""
    cleaned = _ILLEGAL_CHARS.sub("", name or "")
    cleaned = _WHITESPACE.sub(" ", cleaned).strip()
    return cleaned


def _existing_topics() -> list[dict]:
    """扫描 library/<domain>/<topic>.md，返回 [{"domain", "topic", "path"}]。

    排除 MEMORY.md / index.md / 健康日报目录（非讨论主题）。
    """
    result = []
    if not LIBRARY_DIR.exists():
        return result
    for domain_dir in sorted(p for p in LIBRARY_DIR.iterdir() if p.is_dir()):
        if domain_dir.name == "健康日报":
            continue
        for f in sorted(domain_dir.glob("*.md")):
            stem = f.stem
            if stem in ("MEMORY", "index"):
                continue
            result.append({"domain": domain_dir.name, "topic": stem, "path": f})
    return result


def _parse_judge_response(content: str) -> dict | None:
    """解析 LLM 返回的 JSON。容忍 ```json 围栏与前后杂质。

    解析失败返回 None（调用方保守降级：跳过本轮，记 WARNING + 事件）。
    """
    if not content:
        return None
    text = content.strip()
    # 去 ```json ... ``` 围栏
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    # 找第一个 { 到最后一个 }
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(text[start:end + 1])
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    topic = (data.get("topic") or "").strip()
    section = (data.get("section") or "").strip()
    if not topic or not section:
        return None
    domain = (data.get("domain") or "general").strip()
    match = data.get("match") or None
    if match is not None:
        match = str(match).strip() or None
    return {"topic": topic, "domain": domain, "section": section, "match": match}


def _read_frontmatter(path: Path) -> dict:
    """读取已有笔记 frontmatter（失败返回空 dict，保守不炸）。"""
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return {}
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    fm_text = text[3:end]
    fm = {}
    for line in fm_text.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip()
    return fm


def _merge_sessions(raw: str, sid: str) -> list[str]:
    """frontmatter source_sessions 追加 sid（去重，保序）。"""
    sessions = raw.strip("[]").replace(" ", "")
    lst = [s for s in sessions.split(",") if s] if sessions else []
    if sid not in lst:
        lst.append(sid)
    return lst


def _snapshot(domain: str, topic: str, version: int, old_text: str) -> Path:
    """旧版整篇快照 → library/.history/<domain>/<topic>/v{N}.md（无限保留，永不删）。"""
    hist = LIBRARY_DIR / ".history" / domain / topic
    hist.mkdir(parents=True, exist_ok=True)
    p = hist / f"v{version}.md"
    p.write_text(old_text, encoding="utf-8")
    return p


def _protected_lines(old_text: str) -> set[str]:
    """提取需逐字保护的行：`· 人手` 后缀行、`> 用户修订` 引用块、时间线旧行。"""
    protected: set[str] = set()
    lines = old_text.split("\n")
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        if _HUMAN_MARK.search(line):
            protected.add(line.rstrip())
            i += 1
            continue
        if _USER_REV_START.match(line):
            # 引用块：起始行 + 后续连续 > 行整体保护
            protected.add(line.rstrip())
            i += 1
            while i < n and lines[i].startswith(">"):
                protected.add(lines[i].rstrip())
                i += 1
            continue
        i += 1
    # 时间线旧行（## 时间线 小节内的 - 行）
    in_tl = False
    for line in lines:
        if line.startswith("## 时间线"):
            in_tl = True
            continue
        if in_tl:
            if line.startswith("## "):
                break
            if line.strip().startswith("- "):
                protected.add(line.rstrip())
    return protected


def _structure_check(new_text: str, old_text: str,
                     protected: set[str]) -> tuple[bool, str]:
    """结构校验三拒 + 人手/时间线保护硬校验。返回 (ok, reason)。"""
    # 拒 1：缺 frontmatter
    if not new_text.startswith("---"):
        return False, "missing frontmatter"
    sep = new_text.find("\n---", 3)
    if sep == -1:
        return False, "missing frontmatter"
    body = new_text[sep + 4:].strip()
    # 拒 2：正文为空
    if not body:
        return False, "empty body"
    # 拒 3：新笔记长度 < 旧版 30%（防 LLM 截断毁灭笔记）
    if len(new_text) < len(old_text) * 0.3:
        return False, "too short (<30% of old)"
    # 人手/时间线保护行逐字保留
    for pl in sorted(protected):
        if pl not in new_text:
            return False, f"protected line lost: {pl[:40]!r}"
    return True, ""


def _write_new_note(domain: str, topic: str, material: str, sid: str, llm_call) -> Path:
    """新主题 → LLM 成文骨架笔记（LN-2S：首轮也 1 次 LLM 调用，不吃免成文捷径）。

    material: 本轮完整回复全文（超长已在外层截断）。
    流程：LLM 按 _NEW_NOTE_SYSTEM 组织全文 → 校验（缺 frontmatter/正文空 → 拒）
    → 程序维护 frontmatter（version 1 / last_touched / source_sessions）→ 原子写。
    """
    today = datetime.now().strftime("%Y-%m-%d")
    now_hm = datetime.now().strftime("%H:%M")
    domain_dir = LIBRARY_DIR / domain
    domain_dir.mkdir(parents=True, exist_ok=True)
    path = domain_dir / f"{topic}.md"

    # 1. LLM 成文：完整回复 → 整篇骨架笔记
    prompt = [
        {"role": "system", "content": _NEW_NOTE_SYSTEM},
        {"role": "user", "content": (
            f"当前时间：{now_hm}（时间线新行用这个时间）\n\n"
            f"本轮完整回复：\n{material}"
        )},
    ]
    response = llm_call(prompt, use_tools=False)
    if isinstance(response, dict) and "error" in response:
        raise ValueError(f"llm error: {response.get('error')}")
    content = (response.get("choices", [{}])[0]
               .get("message", {}).get("content", ""))
    new_text = (content or "").strip()
    if not new_text:
        raise ValueError("new note returned empty")

    # 2. 校验：缺 frontmatter / 正文空 → 拒（新主题无旧版可对比 30%）
    ok, reason = _structure_check(new_text, "", set())
    if not ok:
        raise ValueError(f"new note structure check failed: {reason}")

    # 3. 程序维护 frontmatter：正文取 LLM 输出第一个 --- 之后全部
    sep = new_text.find("\n---", 3)
    body = new_text[sep + 4:].strip("\n") if sep != -1 else new_text
    new_fm = (
        "---\n"
        f"topic: {topic}\n"
        f"domain: {domain}\n"
        f"created: {today}\n"
        f"last_touched: {today}\n"
        "version: 1\n"
        f"source_sessions: [{sid}]\n"
        "---\n"
    )
    final = new_fm + "\n" + body + "\n"

    # 4. 原子写
    fd, tmp = tempfile.mkstemp(dir=domain_dir, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(final)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise

    # 5. notes.written 事件（票 TICKET-022：补 sid，供 injector 按会话过滤）
    _emit("notes.written", {
        "path": str(path), "topic": topic, "is_new": True, "version": 1,
        "sid": sid,
    })
    return path


def _rewrite_note(domain: str, topic: str, path: Path,
                  material: str, sid: str, llm_call) -> Path:
    """骨架重写式：快照 → LLM 输出整篇新笔记 → 校验三拒 → 原子写。

    material: 本轮完整回复全文（LN-2S：重写原料从要点升级为全文，超长已在外层截断）。
    校验不过 → 抛 ValueError（调用方记 WARNING + notes.error），
    旧版已快照进 .history、笔记文件保持原样。
    """
    today = datetime.now().strftime("%Y-%m-%d")
    now_hm = datetime.now().strftime("%H:%M")
    old_text = path.read_text(encoding="utf-8")
    fm = _read_frontmatter(path)
    try:
        version = int(fm.get("version", 1) or 1)
    except (TypeError, ValueError):
        version = 1

    # 1. 旧版整篇快照（v{version}，无限保留）
    _snapshot(domain, topic, version, old_text)

    # 2. LLM 重写：旧笔记全文 + 本轮完整回复 → 整篇新笔记
    prompt = [
        {"role": "system", "content": _REWRITE_SYSTEM},
        {"role": "user", "content": (
            f"当前时间：{now_hm}（时间线新行用这个时间）\n\n"
            f"旧笔记全文：\n{old_text}\n\n"
            f"本轮完整回复：\n{material}"
        )},
    ]
    response = llm_call(prompt, use_tools=False)
    if isinstance(response, dict) and "error" in response:
        raise ValueError(f"llm error: {response.get('error')}")
    content = (response.get("choices", [{}])[0]
               .get("message", {}).get("content", ""))
    new_text = (content or "").strip()
    if not new_text:
        raise ValueError("rewrite returned empty")

    # 3. 结构校验三拒 + 人手/时间线保护
    protected = _protected_lines(old_text)
    ok, reason = _structure_check(new_text, old_text, protected)
    if not ok:
        raise ValueError(f"rewrite structure check failed: {reason}")

    # 4. 程序维护 frontmatter：正文取 LLM 输出第一个 --- 之后全部
    sep = new_text.find("\n---", 3)
    body = new_text[sep + 4:].strip("\n") if sep != -1 else new_text
    sessions = _merge_sessions(fm.get("source_sessions", ""), sid)
    new_fm = (
        "---\n"
        f"topic: {fm.get('topic', topic)}\n"
        f"domain: {fm.get('domain', domain)}\n"
        f"created: {fm.get('created', today)}\n"
        f"last_touched: {today}\n"
        f"version: {version + 1}\n"
        f"source_sessions: [{', '.join(sessions)}]\n"
        "---\n"
    )
    final = new_fm + "\n" + body + "\n"

    # 5. 原子写（临时文件 + os.replace，与 memory_mirror 同款）
    domain_dir = LIBRARY_DIR / domain
    domain_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=domain_dir, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(final)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise

    # 6. notes.updated 事件（票 TICKET-022：补 sid，供 injector 按会话过滤）
    _emit("notes.updated", {
        "path": str(path), "topic": topic, "version": version + 1,
        "old_len": len(old_text), "new_len": len(final),
        "sid": sid,
    })
    return path


def _rebuild_index():
    """幂等全量重生成 library/index.md：按领域分组列出主题笔记。

    格式：- [[主题]] — 最后更新 YYYY-MM-DD（N 篇会话）
    N = source_sessions 去重数（取不到则按正文 ## 会话 小节数兜底）。
    """
    topics = _existing_topics()
    lines = [
        "# 活体知识库索引",
        "<!-- AUTO-GENERATED: 由 tools/living_notes.py 维护，请勿手改 -->",
        "",
    ]
    by_domain: dict[str, list] = {}
    for t in topics:
        by_domain.setdefault(t["domain"], []).append(t)
    for domain in sorted(by_domain.keys()):
        lines.append(f"## {domain}")
        for t in sorted(by_domain[domain], key=lambda x: x["topic"]):
            fm = _read_frontmatter(t["path"])
            last = fm.get("last_touched", "未知")
            sessions = fm.get("source_sessions", "[]").strip("[]").replace(" ", "")
            n = len([s for s in sessions.split(",") if s]) if sessions else 1
            lines.append(f"- [[{t['topic']}]] — 最后更新 {last}（{n} 篇会话）")
        lines.append("")
    LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text("\n".join(lines), encoding="utf-8")


# ── 对外 API ─────────────────────────────────────

def write_living_notes(takeaways: list[str], user_msg: str, sid: str, llm_call,
                       full_reply: str = "") -> dict:
    """RESPONDING 收工钩子入口（engine.py 调用，try/except 包裹）。

    参数：
      takeaways: 本轮提取的要点（非空才触发本函数；仅作主题判定廉价信号）
      user_msg: 最近一条用户消息
      sid: 会话 id（小节出处 + frontmatter source_sessions）
      llm_call: 可调用对象，签名 llm_call(prompt, use_tools=False) → dict
      full_reply: 本轮 assistant 完整回复全文（LN-2S：成文/重写的唯一原料，
        不截断传入；空则回退用 takeaways 拼列表，保旧调用兼容）

    返回：
      {"written": bool, "path": str|None, "is_new": bool|None,
       "error": str|None}  用于日志/测试断言；失败永不抛异常。
    """
    # 总开关
    if os.environ.get(_ENV_OFF, "").lower() == "off":
        return {"written": False, "error": "disabled"}
    if not takeaways:
        return {"written": False, "error": None}

    # LN-2S：成文/重写原料 = 完整回复全文（超 32000 才截断 + notes.error truncated）
    material = full_reply if full_reply else "\n".join(f"- {t}" for t in takeaways)
    if len(material) > _MAX_REPLY_CHARS:
        material = material[:_MAX_REPLY_CHARS]
        _emit("notes.error", {
            "truncated": True, "reason": "reply too long",
            "full_len": len(full_reply), "kept_len": len(material),
        })

    try:
        # 1. 主题判定（唯一一次 LLM 调用）
        existing = _existing_topics()
        topic_names = "\n".join(
            f"- {t['topic']}（{t['domain']}）" for t in existing
        ) or "（空库，无已有主题）"
        prompt = [
            {"role": "system", "content": _JUDGE_SYSTEM},
            {"role": "user", "content": (
                f"本轮要点：\n{chr(10).join('- ' + t for t in takeaways)}\n\n"
                f"用户最近消息：{user_msg[:200]}\n\n"
                f"现有主题清单：\n{topic_names}"
            )},
        ]
        response = llm_call(prompt, use_tools=False)
        if isinstance(response, dict) and "error" in response:
            raise ValueError(f"llm error: {response.get('error')}")
        content = (response.get("choices", [{}])[0]
                   .get("message", {}).get("content", ""))
        judge = _parse_judge_response(content)
        if judge is None:
            raise ValueError("judge response unparseable")

        # 2. 决定新/旧 + 净化命名
        topic = _sanitize_name(judge["topic"])
        domain = _sanitize_name(judge["domain"]) or "general"
        if not topic:
            raise ValueError("empty topic after sanitize")

        # match 命中 → 找对应已有笔记文件
        match_topic = None
        if judge["match"]:
            match_topic = _sanitize_name(judge["match"])
        # 规范化主题名完全相同（净化后文件名已存在）
        is_new = True
        target_domain = domain
        target_path = None
        for t in existing:
            if t["topic"] == topic:
                target_domain = t["domain"]
                target_path = t["path"]
                is_new = False
                break
            if match_topic and t["topic"] == match_topic:
                target_domain = t["domain"]
                topic = t["topic"]
                target_path = t["path"]
                is_new = False
                break

        # 3. 落盘（骨架式：新主题 LLM 成文，已有主题快照+LLM 重写+校验三拒）
        if is_new:
            path = _write_new_note(target_domain, topic, material, sid, llm_call)
        else:
            path = _rewrite_note(target_domain, topic, target_path,
                                 material, sid, llm_call)

        # 4. index.md 幂等重生成
        _rebuild_index()

        # 4.5 版本化保底：library 独立仓库自动提交（票 G1：_rebuild_index 后、镜像前；
        #     只 add/commit，无变更跳过；失败静默降级 notes.error，绝不阻塞主流程；
        #     library_dir 传本模块 LIBRARY_DIR——测试 monkeypatch 后自动指向 tmp 库）
        try:
            from tools.library_git import auto_commit
            result = auto_commit(library_dir=LIBRARY_DIR,
                                 action="write" if is_new else "update",
                                 topic=topic, sid=sid)
            if result.get("error"):
                _emit("notes.error", {"error": f"library_git: {result['error']}"})
        except Exception as e:
            logger.warning("library git auto-commit failed (silent degrade): %s", e)
            _emit("notes.error", {"error": f"library_git: {e}"})

        # 5. 单向镜像：主库 → Obsidian vault 展示层（失败静默降级，纪律同 E4a）
        #    R2b 铁律：挂钩永远不许传 allow_mass_delete（闸 2 熔断在自动场景常开）；
        #    闸 1/闸 2 触发 blocked 时降级记 notes.error，不阻塞主流程。
        try:
            from tools.library_mirror import sync_library_to_obsidian
            result = sync_library_to_obsidian(sid=sid, allow_mass_delete=False)
            if result.get("blocked"):
                _emit("notes.error", {"error": f"mirror_blocked: {result['blocked']}"})
        except Exception as e:
            logger.warning("library mirror sync failed (silent degrade): %s", e)
            _emit("notes.error", {"error": f"mirror_sync: {e}"})

        # notes.written / notes.updated 已在 _write_new_note / _rewrite_note 内部发射（带 sid）
        return {"written": True, "path": str(path), "is_new": is_new, "error": None}
    except Exception as e:
        logger.warning("living notes write failed (silent degrade): %s", e)
        _emit("notes.error", {"error": str(e)})
        return {"written": False, "error": str(e)}
