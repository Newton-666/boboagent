"""skill_loader.py — 技能标准加载器：扫描 data/skill-standards/ 并注入 system prompt。

从 engine.py 提取，原为 Engine 类的 _load_skill_standards / _list_available_standards。

自动发现：往 data/skill-standards/ 下新增一个文件夹、放入 standard.md 即生效。
不需要改任何代码、不需要注册、不需要更新索引。

每个 standard.md 通过元数据行声明自己的行为：
- keywords: 触发词（逗号分隔）
- excludes: 排除词（话题含这些词时跳过本 skill）
- requires: 依赖 skill 名（本 skill 注入时连带加载）
"""

import logging
import os as _os
import re as _sre
import json

logger = logging.getLogger(__name__)

# ── 票 TICKET-SKILL-PANEL：skill 治理开关（COST-2 注入链白名单内追加，
# COST-3 特批标记）──
# data/skills/enabled.json：{"<skill 目录名>": true/false}，默认 true。
# 关掉的 skill 不注入（用户可关、可开，治理先行——自动沉淀 B 票的 skill
# 一出生就在治理之下）。文件缺失/损坏 → 全 true（不破坏现有注入）。
_ENABLED_FILE = _os.path.join(
    _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
    "data", "skills", "enabled.json",
)


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


class SkillLoader:
    """扫描技能标准目录，匹配触发词后注入标准到 system prompt。两遍评分 + 依赖链解析。"""

    def __init__(self, get_history):
        """初始化技能加载器。

        Args:
            get_history: 可调用对象，返回 self.history 列表（用于提取用户消息匹配触发词）
        """
        self._get_history = get_history

    def load_standards(self) -> list[str]:
        """扫描 data/skill-standards/*/standard.md，返回所有匹配的标准内容（按匹配度降序）。"""
        try:
            std_dir = _os.path.join(_os.path.dirname(_os.path.dirname(
                _os.path.abspath(__file__))), "data", "skill-standards")
            if not _os.path.isdir(std_dir):
                return []
            history = self._get_history()
            user_msgs = [m.get("content", "") for m in history[-4:]
                         if m.get("role") == "user" and m.get("content")]
            topic = " ".join(user_msgs[-1:]).lower() if user_msgs else ""

            # 第一遍：加载所有 skill 的元数据（不评分）
            entries = {}  # entry_name -> {content, trigger_words, exclude_words, requires}
            for entry in _os.listdir(std_dir):
                path = _os.path.join(std_dir, entry, "standard.md")
                if not _os.path.isfile(path):
                    continue
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                # keywords
                kw = _sre.search(r'keywords:\s*(.+)', content, _sre.IGNORECASE)
                trigger_words = [w.strip().lower() for w in (kw.group(1).split(",") if kw else [])]
                if not trigger_words:
                    trigger_words = (entry + " " + content.split("\n")[0]).lower().split()
                # excludes（可选）
                ex = _sre.search(r'excludes:\s*(.+)', content, _sre.IGNORECASE)
                exclude_words = [w.strip().lower() for w in (ex.group(1).split(",") if ex else [])]
                # requires（可选）
                req = _sre.search(r'requires:\s*(.+)', content, _sre.IGNORECASE)
                require_names = [w.strip() for w in (req.group(1).split(",") if req else [])]
                entries[entry] = {
                    "content": content,
                    "trigger_words": trigger_words,
                    "exclude_words": exclude_words,
                    "require_names": require_names,
                }

            # 第二遍：评分 + 排除过滤
            scored = []
            for name, info in entries.items():
                if info["exclude_words"] and any(ew in topic for ew in info["exclude_words"]):
                    continue
                score = sum(1 for tw in info["trigger_words"] if tw and tw in topic)
                if score > 0:
                    scored.append((score, name))

            scored.sort(key=lambda x: x[0], reverse=True)
            top_names = [name for _, name in scored[:3]]
            top_set = set(top_names)

            # 解析 requires：连带加载依赖 skill（跳过 excludes 检查——被拉进来的不受排除影响）
            for name in list(top_names):
                for req_name in entries.get(name, {}).get("require_names", []):
                    if req_name not in top_set and req_name in entries:
                        top_set.add(req_name)
                        top_names.append(req_name)

            # ── 票 TICKET-SKILL-PANEL：治理开关——关掉的 skill 不注入（含
            # requires 连带拉入的：用户关了就是关了，一视同仁）──
            enabled = _load_enabled()
            if enabled:
                top_names = [n for n in top_names if enabled.get(n, True)]

            return [entries[name]["content"] for name in top_names]
        except Exception:
            return []
