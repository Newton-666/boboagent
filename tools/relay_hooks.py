#!/usr/bin/env python3
"""relay_hooks — TICKET-SCAN-L3b：relay 内部数据通道（API 直采）。

bobo 不在 tmux 时（owner 实弹场景），relay 的"自己侧"不再依赖
capture-pane 看屏幕，改从内部事件直取：
  - 用户话题  ← prompt.submit 的 text（handle_prompt_submit 调用 push_user_input）
  - bobo 回复 ← engine complete 事件（engine_adapter on_event 调用 push_bobo_reply）

对方侧（pi）不变：仍走 tmux capture-pane + send-keys + 发送前复核。

线程安全：全局注册表 + Lock；每 sid 两个 Queue（user / bobo）。
"""
import threading
from queue import Empty, Queue

_hooks: dict[str, dict] = {}
_lock = threading.Lock()


def register(sid: str) -> dict:
    """为 sid 创建数据通道（幂等：重复注册返回既有通道）。"""
    with _lock:
        if sid not in _hooks:
            _hooks[sid] = {"user": Queue(), "bobo": Queue()}
        return _hooks[sid]


def unregister(sid: str):
    """释放 sid 的数据通道。"""
    with _lock:
        _hooks.pop(sid, None)


def is_active(sid: str) -> bool:
    """sid 是否有活跃数据通道（relay 是否在等内部事件）。"""
    with _lock:
        return sid in _hooks


def push_user_input(sid: str, text: str):
    """用户话题直取：handle_prompt_submit 在启动 engine 前调用。"""
    with _lock:
        hook = _hooks.get(sid)
    if hook:
        hook["user"].put(text)


def push_bobo_reply(sid: str, text: str):
    """bobo 回复直取：engine_adapter on_event complete 分支调用。"""
    with _lock:
        hook = _hooks.get(sid)
    if hook:
        hook["bobo"].put(text)


def poll_user_input(sid: str, timeout: float) -> str | None:
    """取用户话题；超时返回 None。"""
    with _lock:
        hook = _hooks.get(sid)
    if not hook:
        return None
    try:
        return hook["user"].get(timeout=timeout)
    except Empty:
        return None


def poll_bobo_reply(sid: str, timeout: float) -> str | None:
    """取 bobo 完整回复；超时返回 None。"""
    with _lock:
        hook = _hooks.get(sid)
    if not hook:
        return None
    try:
        return hook["bobo"].get(timeout=timeout)
    except Empty:
        return None


def drain(sid: str) -> tuple:
    """清空 sid 通道，返回 (剩余用户话题数, 剩余回复数)。"""
    with _lock:
        hook = _hooks.get(sid)
    if not hook:
        return (0, 0)
    nu = nr = 0
    while True:
        try:
            hook["user"].get_nowait()
            nu += 1
        except Empty:
            break
    while True:
        try:
            hook["bobo"].get_nowait()
            nr += 1
        except Empty:
            break
    return (nu, nr)
