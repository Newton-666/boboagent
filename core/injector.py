"""injector.py — Prompt 注入管道：将 engine 状态组装成完整的 messages 列表。

从 engine.py 的 _call_llm 方法提取。纯注入逻辑，不含 API 调用。
注入顺序必须与原 _call_llm 完全一致。
"""

import json
import os as _os
import logging

logger = logging.getLogger(__name__)


class PromptInjector:
    """从 engine 状态构建完整的 messages 列表（system prompt + 所有注入 + history）。

    注入顺序：
    1. pending diff（代码审查）
    2. 推荐技能
    3. 自定义 API
    4. 用户资料 + 记忆
    5. AGENTS.md（项目规则）
    6. 改动日志（tracker.recent_changes）
    7. 已读文件（tracker.recent_reads）
    8. 主动连接（proactive.inject_context）
    9. 技能标准（skill_loader.load_standards）
    """

    def __init__(self, engine_ref):
        """初始化注入器。

        Args:
            engine_ref: Engine 实例引用，只读访问其状态。
        """
        self._engine = engine_ref

    def build_messages(
        self,
        system_prompt: str,
        user_input: str,
        tools_schema: list,
        extra_categories: set,
        session_id: str = "",
    ) -> list:
        """构建完整的 messages 列表。

        Returns:
            messages 列表，可直接传给 LLM caller。
        """
        engine = self._engine

        messages = [{"role": "system", "content": system_prompt}] + engine.history

        # ── 1. pending diff ──
        if engine._pending_diff:
            diff_preview = engine._pending_diff[:4000]
            messages.insert(1, {
                "role": "system",
                "content": (
                    f"[代码变更 — 请审查以下 diff 是否有 bug、安全风险或性能问题:]\n"
                    f"{diff_preview}\n\n"
                    f"审查要点:\n"
                    f"1. 逻辑错误（拼写错误、条件反转、off-by-one）\n"
                    f"2. 安全风险（注入、硬编码密钥、权限问题）\n"
                    f"3. 性能问题（不必要的循环、重复计算、N+1 查询）\n"
                    f"4. 代码风格（与项目其他部分不一致的命名/格式）\n\n"
                    f"发现问题后如实报告，使用 review_diff 工具可查看完整 diff。"
                )
            })
            engine._pending_diff = ""

        # ── 2. 推荐技能 ──
        try:
            from tools import _skill_mgr
            skill_refs = _skill_mgr.get_skill_tools()
            if skill_refs:
                user_text = (engine.current_user_input or "").lower()
                matched = []
                others = []
                for s in skill_refs:
                    name = s["function"]["name"].replace("run_skill:", "")
                    desc = s["function"]["description"]
                    triggers = s.get("triggers", [])
                    if triggers and any(t.lower() in user_text for t in triggers):
                        matched.append(f"  ▶ {name}: {desc}")
                        # 注入匹配 skill 的完整步骤 → LLM 直接可见，不需调工具
                        try:
                            skill_data = _skill_mgr.get_skill(name)
                            if skill_data and skill_data.get("steps"):
                                step_lines = []
                                for st in skill_data["steps"]:
                                    sn = st.get("name", "")
                                    sa = st.get("action", "")
                                    si = st.get("step", "")
                                    if sn or sa:
                                        step_lines.append(f"    {si}. {sn}: {sa[:200]}")
                                if step_lines:
                                    matched.append("\n".join(step_lines))
                        except Exception as e:
                            logger.debug("注入技能步骤失败 (%s): %s", name, e)
                    else:
                        others.append(f"  {name}: {desc[:100]}")
                lines = []
                if matched:
                    lines.append("[推荐技能 — 当前场景可用]:")
                    lines.extend(matched)
                    if others:
                        lines.append("")
                        lines.append("[其他技能]:")
                        lines.extend(others)
                else:
                    lines.append("[可参考的技能工作流]:")
                    lines.extend(others)
                messages.insert(1, {
                    "role": "system",
                    "content": "\n".join(lines)
                })
        except Exception as e:
            logger.debug("注入技能工作流失败: %s", e)

        # ── 3. 自定义 API ──
        apis_dir = _os.path.expanduser("~/.bobo/apis")
        if _os.path.isdir(apis_dir):
            apis = []
            for fname in sorted(_os.listdir(apis_dir)):
                if fname.endswith(".json"):
                    try:
                        with open(_os.path.join(apis_dir, fname)) as f:
                            cfg = json.load(f)
                        eps = [ep.get("name", "?") for ep in cfg.get("endpoints", [])]
                        apis.append(f"{cfg.get('name', fname)} ({', '.join(eps)})")
                    except Exception as e:
                        logger.debug("解析自定义 API 配置失败 (%s): %s", fname, e)
            if apis:
                messages.insert(1, {
                    "role": "system",
                    "content": "[已注册的自定义 API]:\n" + "\n".join(apis)
                })

        # ── 4. 用户资料 + 记忆 ──
        try:
            from tools.v5_memory import format_user_profile, format_all_memory
            user_profile = format_user_profile()
            if user_profile:
                messages.insert(1, {
                    "role": "system",
                    "content": user_profile
                })
            # 注入全部记忆（最新 5000 字符，类似 Hermes 的快照方式）
            if not engine._compressing:
                all_mem = format_all_memory(max_chars=5000)
                if all_mem and "记忆 (0/0" not in all_mem:
                    messages.insert(1, {
                        "role": "system",
                        "content": all_mem
                    })
        except Exception as e:
            logger.debug("注入用户资料/记忆失败: %s", e)

        # ── 5. AGENTS.md ──
        try:
            vault = _os.environ.get("OBSIDIAN_VAULT", "")
            if vault:
                agents_path = _os.path.join(vault, "AGENTS.md")
                if _os.path.isfile(agents_path):
                    with open(agents_path, encoding="utf-8") as _f:
                        agents_content = _f.read(4000)
                    if agents_content.strip():
                        messages.insert(1, {
                            "role": "system",
                            "content": f"[项目规则 (AGENTS.md)]:\n{agents_content}"
                        })
        except Exception as e:
            logger.debug("注入 AGENTS.md 失败: %s", e)

        # ── 6. 改动日志 ──
        if engine.tracker._change_log:
            items = engine.tracker._change_log[-5:]
            lines = ["[本会话的改动记录]:", ""]
            for it in items:
                lines.append(f"  {it['desc']}")
            if len(engine.tracker._change_log) > 5:
                lines.append(f"  ...（共 {len(engine.tracker._change_log)} 次改动）")
            messages.insert(1, {"role": "system", "content": "\n".join(lines)})

        # ── 7. 已读文件 ──
        if engine.tracker._read_files:
            items = list(engine.tracker._read_files.items())[-3:]
            lines = ["[最近读过的文件]:", ""]
            for fpath, preview in items:
                short = preview[:120].replace('\n', ' ').strip()
                lines.append(f"  {fpath}: {short}...")
            messages.insert(1, {"role": "system", "content": "\n".join(lines)})

        # ── 8. 主动连接 ──
        messages = engine.proactive.inject_context(messages)

        # ── 9. 技能标准 ──
        skill_stds = engine.skill_loader.load_standards()
        if skill_stds:
            combined = "\n\n---\n\n".join(skill_stds)
            messages.append({
                "role": "system",
                "content": (
                    "## 项目标准 — 以下规则优先级高于一切，违反即不合格\n\n"
                    + combined
                ),
            })
        else:
            # 没有命中任何标准时，仍然告知可用标准列表（让 Bobo 知道自己的技能）
            available = engine.skill_loader.list_available()
            if available:
                messages.append({
                    "role": "system",
                    "content": (
                        "## 可用的项目标准（当前未命中，以下仅供参考）\n\n"
                        + available
                    ),
                })

        return messages
