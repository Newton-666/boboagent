"""与 pi 讨论工具（tmux 双 TUI 版）— 真实界面互传对话。

原理：
    搭建 tmux 分屏舞台：左 pane 跑 bobo TUI，右 pane 跑 pi TUI，
    底部 pane 显示 relay 状态。relay 用 capture-pane 检测一方回复完成后，
    用 send-keys 把回复敲进另一方输入框，循环 N 轮，结束后截屏存档。

两种用法：
    1) 自动模式（本工具）：用户在当前 bobo 界面说"跟 pi 讨论XX"，
       bobo 调用本工具 → 自动搭舞台 + 注入话题 → 等 N 轮结束 → 返回截屏内容。
    2) 手动模式：直接运行 pi_chat.sh [轮数] 进入舞台，
       在左侧 bobo pane 输入话题，relay 自动接管对话。
"""
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STAGE = os.path.join(ROOT, "pi_chat.sh")
LOG = os.path.join(ROOT, "data", "pi_relay.log")
DONE_LABEL = "对话结束"


def _run(cmd, timeout=20, **kw):
    try:
        return subprocess.run(cmd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              timeout=timeout, **kw)
    except subprocess.TimeoutExpired:
        return None


def _tmux(args, timeout=15):
    return _run(["tmux"] + args, timeout=timeout)


def _stage_running() -> bool:
    r = _tmux(["has-session", "-t", "bobo-pi-chat"])
    return r is not None and r.returncode == 0


def _inject_topic(topic: str):
    """把话题敲进 bobo pane 输入框并回车（消息与 Enter 必须分开）。
    附加约束：直接陈述观点、不要调用工具，避免触发授权弹窗卡住流程。"""
    pane = "bobo-pi-chat:0.0"
    text = f"{topic}（注意：请直接陈述你的观点，不要调用任何工具、不要执行命令）"
    _tmux(["send-keys", "-t", pane, text])
    time.sleep(0.5)
    _tmux(["send-keys", "-t", pane, "Enter"])


def _wait_finished(rounds: int, timeout: float) -> str:
    """等 relay 完成（LOG 出现 DONE_LABEL），返回截屏文件路径或空串。"""
    deadline = time.time() + timeout
    last_size = -1
    while time.time() < deadline:
        if os.path.exists(LOG):
            size = os.path.getsize(LOG)
            if size != last_size:
                last_size = size
                try:
                    with open(LOG, encoding="utf-8") as f:
                        content = f.read()
                    m = re.search(r"对话结束.*?截屏：(\S+)", content)
                    if m and os.path.exists(m.group(1)):
                        return m.group(1)
                except Exception:
                    pass
        time.sleep(5)
    return ""


def _latest_snapshot(since: float) -> str:
    """兜底：找 mtime 晚于 since 的最新截屏文件（避免返回旧讨论）。"""
    d = os.path.join(ROOT, "data")
    if not os.path.isdir(d):
        return ""
    files = [os.path.join(d, f) for f in os.listdir(d)
             if f.startswith("pi_discuss_") and f.endswith(".txt")
             and os.path.getmtime(os.path.join(d, f)) > since]
    return max(files, key=os.path.getmtime) if files else ""


def discuss_with_pi(topic: str, rounds: int = 5) -> str:
    """与 pi 在 tmux 双 TUI 舞台中辩论 N 轮，返回截屏内容摘要。"""
    rounds = max(1, min(int(rounds), 10))
    start = time.time()

    # 若舞台已在跑：提醒用户在左侧 pane 直接输入即可，避免递归
    if _stage_running():
        return ("tmux 舞台（bobo-pi-chat）已在运行。"
                "请在舞台左侧 bobo pane 直接输入话题，relay 会自动接管对话。")

    # 1) 启动舞台
    r = _run(["bash", STAGE, str(rounds)], timeout=60)
    if r is None or r.returncode != 0:
        return f"舞台启动失败：{r.stderr if r else '超时'}"
    time.sleep(16)  # 等两个 TUI 起来

    # 2) 注入话题
    _inject_topic(topic)

    # 3) 等 N 轮结束（预算：每轮 150s + 启动 90s；bobo 可能弹授权框、调工具）
    timeout = rounds * 150 + 90
    snap = _wait_finished(rounds, timeout)
    if not snap:
        snap = _latest_snapshot(start)

    # 4) 读截屏，返回讨论内容（控制长度）
    if snap and os.path.exists(snap):
        try:
            with open(snap, encoding="utf-8") as f:
                body = f.read()
        except Exception:
            body = ""
        head = (f"[tmux 双 TUI 讨论完成] {rounds} 轮，截屏存档：{snap}\n"
                f"（完整记录可打开该文件；下方为截屏内容，可能截断）\n\n")
        return head + body[-12000:]
    return ("讨论仍在进行中（relay 尚未输出完成标记），"
            "可运行 tmux attach -t bobo-pi-chat 实时查看，或稍后读取 "
            "data/pi_discuss_*.txt。relay 日志：" + LOG)


def register(reg):
    reg("discuss_with_pi", discuss_with_pi, {
        "type": "function",
        "function": {
            "name": "discuss_with_pi",
            "description": (
                "让 Bobo 与 pi agent 在 tmux 双 TUI 舞台中辩论 N 轮（默认 5 轮）："
                "左侧 pane 是 bobo 真实聊天界面，右侧 pane 是 pi 界面，"
                "relay 自动把双方回复互相传递，结束后截屏存档并返回讨论内容。"
                "适用场景：用户说'跟 pi 讨论一下XX'、'让 pi 和你就XX辩论'、"
                "'开个双 agent 讨论'、'和 pi 聊聊XX'。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "讨论话题，如 'AI 会取代程序员吗'"},
                    "rounds": {"type": "integer", "description": "讨论轮数，默认 5，最大 10"}
                },
                "required": ["topic"]
            }
        }
    })
