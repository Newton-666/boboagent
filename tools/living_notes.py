# tools/living_notes.py — 主题笔记 MVP（票 LN-2）
#
# 收工时（RESPONDING，takeaways 非空才触发）自动把本轮要点写进
# library/<领域>/<主题>.md 主题笔记，并维护 library/index.md 目录。
#
# MVP 铁律：
#   - 只做追加式记录：新信息永远追加 `## YYYY-MM-DD 会话` 小节，旧内容一字不动。
#     旧小节改写 / 蒸馏晋升 / 反向注入是 LN-3/4 的活，本文件不碰。
#   - 全程最多 1 次额外 LLM 调用（主题判定+成文合并为一次）。
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

    排除 MEMORY.md / index.md（非主题笔记）。
    """
    result = []
    if not LIBRARY_DIR.exists():
        return result
    for domain_dir in sorted(p for p in LIBRARY_DIR.iterdir() if p.is_dir()):
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


def _format_section(section: str, sid: str) -> str:
    """LLM 返回的 section → 落盘小节正文。

    每条非空行末尾带出处（源自会话 {sid}）。已是列表项则挂在行尾；
    无出处标记的普通行同样追加。空行保留。
    """
    lines = []
    for raw in section.split("\n"):
        line = raw.rstrip()
        if not line.strip():
            lines.append("")
            continue
        if "（源自会话" in line:
            lines.append(line)
        else:
            lines.append(f"{line}（源自会话 {sid}）")
    return "\n".join(lines)


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


def _write_note(domain: str, topic: str, section_body: str, sid: str, is_new: bool) -> Path:
    """落盘主题笔记（非破坏性）。

    - 新笔记：frontmatter + 首个 `## YYYY-MM-DD 会话` 小节。
    - 已有笔记：更新 frontmatter（last_touched / source_sessions），
      文末追加 `## YYYY-MM-DD 会话` 小节，旧内容一字不动。
    """
    today = datetime.now().strftime("%Y-%m-%d")
    domain_dir = LIBRARY_DIR / domain
    domain_dir.mkdir(parents=True, exist_ok=True)
    path = domain_dir / f"{topic}.md"
    now_ts = datetime.now().strftime("%Y-%m-%d %H:%M")

    if is_new:
        fm = (
            "---\n"
            f"topic: {topic}\n"
            f"domain: {domain}\n"
            f"created: {today}\n"
            f"last_touched: {today}\n"
            f"source_sessions: [{sid}]\n"
            "---\n\n"
        )
        body = f"## {today} 会话\n\n{section_body}\n"
        path.write_text(fm + body, encoding="utf-8")
        return path

    # 已有笔记：读全文，改 frontmatter，正文追加
    old_text = path.read_text(encoding="utf-8")
    fm = _read_frontmatter(path)
    # 更新 last_touched / source_sessions
    sessions = fm.get("source_sessions", "")
    sessions = sessions.strip("[]").replace(" ", "")
    sid_list = [s for s in sessions.split(",") if s] if sessions else []
    if sid not in sid_list:
        sid_list.append(sid)
    new_fm = (
        "---\n"
        f"topic: {fm.get('topic', topic)}\n"
        f"domain: {fm.get('domain', domain)}\n"
        f"created: {fm.get('created', today)}\n"
        f"last_touched: {today}\n"
        f"source_sessions: [{', '.join(sid_list)}]\n"
        "---\n"
    )
    # 替换旧 frontmatter（只动 frontmatter 块，正文一字不动）
    if old_text.startswith("---"):
        end = old_text.find("\n---", 3)
        if end != -1:
            old_text = new_fm + old_text[end + 4:]
        else:
            old_text = new_fm + old_text
    else:
        old_text = new_fm + old_text
    # 文末追加小节（确保以换行结尾再接）
    if not old_text.endswith("\n"):
        old_text += "\n"
    old_text += f"\n## {today} 会话\n\n{section_body}\n"
    path.write_text(old_text, encoding="utf-8")
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

def write_living_notes(takeaways: list[str], user_msg: str, sid: str, llm_call) -> dict:
    """RESPONDING 收工钩子入口（engine.py 调用，try/except 包裹）。

    参数：
      takeaways: 本轮提取的要点（非空才触发本函数）
      user_msg: 最近一条用户消息
      sid: 会话 id（小节出处 + frontmatter source_sessions）
      llm_call: 可调用对象，签名 llm_call(prompt, use_tools=False) → dict

    返回：
      {"written": bool, "path": str|None, "is_new": bool|None,
       "error": str|None}  用于日志/测试断言；失败永不抛异常。
    """
    # 总开关
    if os.environ.get(_ENV_OFF, "").lower() == "off":
        return {"written": False, "error": "disabled"}
    if not takeaways:
        return {"written": False, "error": None}

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
        section_body = _format_section(judge["section"], sid)

        # match 命中 → 找对应已有笔记文件
        match_topic = None
        if judge["match"]:
            match_topic = _sanitize_name(judge["match"])
        # 规范化主题名完全相同（净化后文件名已存在）
        is_new = True
        target_domain = domain
        for t in existing:
            if t["topic"] == topic:
                target_domain = t["domain"]
                is_new = False
                break
            if match_topic and t["topic"] == match_topic:
                target_domain = t["domain"]
                topic = t["topic"]
                is_new = False
                break

        # 3. 落盘（非破坏性）
        path = _write_note(target_domain, topic, section_body, sid, is_new)

        # 4. index.md 幂等重生成
        _rebuild_index()

        _emit("notes.written", {
            "path": str(path), "topic": topic, "is_new": is_new,
        })
        return {"written": True, "path": str(path), "is_new": is_new, "error": None}
    except Exception as e:
        logger.warning("living notes write failed (silent degrade): %s", e)
        _emit("notes.error", {"error": str(e)})
        return {"written": False, "error": str(e)}
