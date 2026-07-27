"""Duo 商讨模式代码编排器 — 确定性流程，模型只负责出观点。

用法：run_deliberation(question, emit, sid)
- emit: engine_adapter 的事件发射函数
- sid: 会话 ID
"""

import os
import re
import subprocess
import threading
import time
import logging

logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ── Phase 0: 现状简报（纯代码，零 LLM）──────────────────────────────

def _briefing() -> str:
    """扫描项目现状，拼成 ≤10 行简报。任何一步失败跳过，不阻断。"""
    lines = []

    # git log
    try:
        r = subprocess.run(
            ["git", "log", "--oneline", "-15"],
            capture_output=True, text=True, cwd=_PROJECT_ROOT, timeout=5,
        )
        if r.returncode == 0 and r.stdout.strip():
            lines.append("## 最近提交（git log -15）")
            for ln in r.stdout.strip().split("\n")[:12]:
                lines.append(f"  {ln}")
    except Exception:
        pass

    # README 前 100 行
    readme_path = os.path.join(_PROJECT_ROOT, "README.md")
    try:
        with open(readme_path, "r", encoding="utf-8") as f:
            head = "".join(f.readlines()[:100])
        lines.append("## README（章节标题）")
        for ln in head.split("\n"):
            if ln.startswith("##"):
                lines.append(f"  {ln.strip()}")
        if len(lines) > 20:
            lines = lines[:20]
    except Exception:
        pass

    # 限制行数
    if len([l for l in lines if not l.startswith("##") and not l.startswith("  ")]) == 0:
        return ""

    return "\n".join(lines[:15])


# ── 汇总（Phase 3）───────────────────────────────────────────────────

def _summarize(question: str, a_text: str, b_text: str) -> str:
    """用 LLM 生成决策清单（纯文本，无工具 schema）。"""
    try:
        from core.provider import resolve_provider
        from core.llm_caller import create_llm_caller as _create_caller

        cfg = resolve_provider()
        llm_caller = _create_caller(cfg["api_key"], cfg["base_url"], cfg["model"])

        prompt = (
            "你是决策汇总者。根据以下 A/B 两方观点，生成决策清单。\n\n"
            f"## 问题\n{question}\n\n"
            f"## A 的方案\n{a_text}\n\n"
            f"## B 的挑刺\n{b_text}\n\n"
            "请按以下格式输出：\n"
            "### 共识\n- ...\n"
            "### 分歧\n- A 认为：...  /  B 认为：...\n"
            "### 建议\n- ...\n"
            "### 待用户拍板\n1. ...\n2. ...\n"
        )
        response = llm_caller(
            [{"role": "user", "content": prompt}],
            use_tools=False,
        )
        if isinstance(response, dict) and "error" in response:
            return f"（汇总失败: {response['error']}）"
        content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
        return content.strip() or "（汇总生成空内容）"
    except Exception as e:
        return f"（汇总失败: {e}）"


# ── 转播辅助 ─────────────────────────────────────────────────────────

def _emit_assistant(emit, sid: str, content: str):
    """向 TUI 发射一条 assistant 消息。"""
    try:
        emit("message.delta", sid, {"text": content, "session_id": sid})
    except Exception:
        pass


# ── 主编排 ───────────────────────────────────────────────────────────

def run_deliberation(question: str, emit, sid: str):
    """执行 /duo 商讨流程（后台线程）。"""

    # Phase 0: 现状简报
    briefing = _briefing()
    if briefing:
        _emit_assistant(emit, sid, f"▎现状简报\n{briefing}\n")

    # Phase 1: A
    _emit_assistant(emit, sid, "▸ 正在派 A 出方案 …")
    try:
        from tools.spawn_worker import execute as spawn
        a_result = spawn(
            instruction=f"就以下问题提出你的方案。给出观点、理由、风险。\n\n问题：{question}",
            name="duo-A-propose",
            context=briefing,
            allow_tools=False,
            timeout=90,
        )
    except Exception as e:
        _emit_assistant(emit, sid, f"❌ A 执行失败: {e}")
        return
    if a_result.startswith("[WORKER_TIMEOUT]") or a_result.startswith("[WORKER_ERROR]"):
        _emit_assistant(emit, sid, f"❌ A 失败: {a_result}")
        return
    _emit_assistant(emit, sid, f"▶ A 的方案原文\n\n{a_result}")

    # Phase 2: B
    _emit_assistant(emit, sid, "▸ 正在派 B 挑刺 …")
    b_instruction = (
        f"有人提出以下方案：\n---\n{a_result}\n---\n"
        f"你的任务是挑刺：找出假设漏洞、遗漏场景、更优替代。"
        f"只输出问题清单，不需要重述方案。"
    )
    try:
        b_result = spawn(
            instruction=b_instruction,
            name="duo-B-critique",
            context=briefing,
            allow_tools=False,
            timeout=90,
        )
    except Exception as e:
        _emit_assistant(emit, sid, f"❌ B 执行失败: {e}")
        return
    if b_result.startswith("[WORKER_TIMEOUT]") or b_result.startswith("[WORKER_ERROR]"):
        _emit_assistant(emit, sid, f"❌ B 失败: {b_result}")
        return
    _emit_assistant(emit, sid, f"▶ B 的挑刺原文\n\n{b_result}")

    # Phase 3: 汇总
    _emit_assistant(emit, sid, "▸ 正在生成决策清单 …")
    summary = _summarize(question, a_result, b_result)
    _emit_assistant(emit, sid, f"## /duo 商讨结论：{question}\n\n{summary}")
