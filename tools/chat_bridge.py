#!/usr/bin/env python3
"""Bobo <-> pi 双 agent 对话桥。

用法:
    python3 tools/chat_bridge.py [轮数] ["开场话题"]

架构:
    Bobo 侧: headless Engine（tools_schema=[] 纯对话，不触发工具调用）
    pi   侧: `pi -p --session-id <固定id>` 非交互模式，复用同一会话保持记忆

流程（每轮）:
    话题 -> Bobo 回复 -> 传给 pi -> pi 回复 -> 传给 Bobo -> 下一轮
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

PI_SESSION_ID = "bobo-pi-bridge"

# 行缓冲：后台重定向到文件时也能实时看到对话进度
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)


def build_bobo_engine():
    """装配 headless Bobo（与 TUI 同款管道，但禁用工具 -> 纯对话）。"""
    from dotenv import load_dotenv
    load_dotenv(os.path.expanduser("~/.bobo/.env"))
    from config import API_KEY, API_BASE_URL, API_MODEL_NAME
    from core.provider import resolve_provider
    from core.llm_caller import create_llm_caller
    from core.tool_executor import execute_tool
    from core.engine import Engine

    prov = resolve_provider("deepseek")
    key = prov["api_key"] or API_KEY
    base = prov["base_url"] or API_BASE_URL
    model = prov["model"] or API_MODEL_NAME
    caller = create_llm_caller(key, base, model, tools_schema=[])  # 无工具定义 -> 纯对话
    engine = Engine(caller, execute_tool)
    print(f"[init] Bobo engine ready (model={model})", file=sys.stderr)
    return engine


def bobo_chat(engine, msg: str) -> str:
    """让 Bobo 回复一条消息，返回纯文本回复。"""
    engine.run(msg, stream=False)
    # 取 history 中最后一条 assistant 消息
    for m in reversed(engine.history):
        if m.get("role") == "assistant":
            content = m.get("content") or ""
            if content:
                return content.strip()
    pending = getattr(engine, "_pending_content", None)
    return (pending or "").strip()


def pi_chat(msg: str) -> str:
    """让 pi 回复一条消息（非交互模式，复用会话保持记忆）。"""
    cmd = ["pi", "-p", "--session-id", PI_SESSION_ID, msg]
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=180,
            cwd=os.path.expanduser("~"),
        )
    except subprocess.TimeoutExpired:
        return "[pi 超时]"
    out = (r.stdout or "").strip()
    if out:
        return out
    err = (r.stderr or "").strip()
    return err if err else "[pi 无输出]"


def main() -> int:
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    topic = sys.argv[2] if len(sys.argv) > 2 else (
        "用两三句话聊聊：人类是否应该让 AI 替自己做重要决定？"
    )
    engine = build_bobo_engine()
    print("=" * 64)
    print("话题:", topic)
    print("轮数:", rounds)
    print("=" * 64)

    msg = topic
    for i in range(1, rounds + 1):
        print(f"\n── 第 {i} 轮 ──")
        # Bobo 先开口
        bobo_out = bobo_chat(engine, msg)
        print(f"\n[Bobo] {bobo_out}")
        # pi 接话
        pi_out = pi_chat(bobo_out)
        print(f"\n[Pi]   {pi_out}")
        msg = pi_out  # pi 的最后一句成为 Bobo 下一轮的输入

    print("\n" + "=" * 64)
    print(f"对话结束，共 {rounds} 轮。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
