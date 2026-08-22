"""TICKET-COMPUTER-USE-CORE 专项测试 — computer_use 工具。

覆盖（票验收）：
1. 权限首用弹窗：未授权 → 返回引导提示（系统设置→屏幕录制+辅助功能），拒绝一切操作（连 capture）。
2. capture：返回屏幕 + AX 树元素索引（role/name/坐标），可附视觉描述。
3. click：按 element=N（AX 索引）或 coordinate=[x,y] 点击。
4. type / key：输入文字 / 组合键。
5. 未知 action → 明确报错。
"""

import pytest

import tools.computer_use as cu


def _authorize_off(monkeypatch):
    monkeypatch.setattr(cu.AS, "AXIsProcessTrusted", lambda: False)
    monkeypatch.setattr(cu.Quartz, "CGPreflightScreenCaptureAccess", lambda: False)


def _authorize_on(monkeypatch):
    monkeypatch.setattr(cu.AS, "AXIsProcessTrusted", lambda: True)
    monkeypatch.setattr(cu.Quartz, "CGPreflightScreenCaptureAccess", lambda: True)


def test_unauthorized_returns_prompt_for_all_actions(monkeypatch):
    """未授权 → 所有 action（含 capture）都返回系统设置引导，拒绝操作。"""
    _authorize_off(monkeypatch)
    for act, kw in [("capture", {}), ("click", {"element": 1}),
                    ("type", {"text": "x"}), ("key", {"key": "cmd+s"})]:
        r = cu.execute(act, **kw)
        assert "⛔" in r and "屏幕录制" in r and "辅助功能" in r, r
        assert "拒绝" in r, r


def test_capture_returns_screen_and_ax_tree(monkeypatch):
    """已授权 capture：返回屏幕 + AX 树索引（role/name/坐标）+（可选）视觉描述。"""
    _authorize_on(monkeypatch)
    monkeypatch.setattr(cu, "_front_pid", lambda: 42)
    monkeypatch.setattr(cu, "_capture_png", lambda: "/tmp/cu_test.png")
    monkeypatch.setattr(cu, "_describe", lambda p: "[视觉描述] 这是测试屏")
    monkeypatch.setattr(cu, "_collect_elements", lambda pid: [
        {"el": "el1", "role": "AXButton", "title": "确定", "frame": (10, 20, 80, 30),
         "depth": 2, "interactive": True},
    ])
    r = cu.execute("capture", describe=False)
    assert "[屏幕快照] /tmp/cu_test.png" in r, r
    assert "共 1 个元素" in r, r
    assert "AXButton" in r and "确定" in r, r
    assert "(10,20 80x30)" in r, r
    # describe=True 走视觉描述
    r2 = cu.execute("capture", describe=True)
    assert "[视觉描述] 这是测试屏" in r2, r2


def test_click_by_element_index(monkeypatch):
    """click element=N：按 AX 索引取中心坐标点击。"""
    _authorize_on(monkeypatch)
    calls = []
    monkeypatch.setattr(cu, "_front_pid", lambda: 42)
    monkeypatch.setattr(cu, "_collect_elements", lambda pid: [
        {"el": "e0", "role": "AXButton", "title": "A", "frame": (100, 100, 20, 40),
         "depth": 1, "interactive": True},
    ])
    monkeypatch.setattr(cu, "_click_at", lambda x, y: calls.append((x, y)))
    r = cu.execute("click", element=1)
    assert "已点击 元素#1" in r and "AXButton" in r, r
    assert calls and abs(calls[0][0] - 110) < 0.1 and abs(calls[0][1] - 120) < 0.1, calls
    # 越界报错
    r2 = cu.execute("click", element=5)
    assert "越界" in r2, r2


def test_click_by_coordinate(monkeypatch):
    """click coordinate=[x,y]：直接像素坐标点击。"""
    _authorize_on(monkeypatch)
    calls = []
    monkeypatch.setattr(cu, "_front_pid", lambda: 42)
    monkeypatch.setattr(cu, "_collect_elements", lambda pid: [])
    monkeypatch.setattr(cu, "_click_at", lambda x, y: calls.append((x, y)))
    r = cu.execute("click", coordinate=[5, 6])
    assert "已点击 坐标" in r, r
    assert calls[0] == (5.0, 6.0), calls


def test_type_and_key(monkeypatch):
    """type 输入文字；key 组合键。"""
    _authorize_on(monkeypatch)
    monkeypatch.setattr(cu, "_post_key_combo", lambda k: True)
    r = cu.execute("type", text="bobo")
    assert "已输入文字（4 字符）" in r, r
    r2 = cu.execute("key", key="cmd+s")
    assert "已发送组合键 cmd+s" in r2, r2
    r3 = cu.execute("key", key="")
    assert "错误" in r3, r3


def test_unknown_action(monkeypatch):
    _authorize_on(monkeypatch)
    r = cu.execute("foobar")
    assert "未知 action" in r and "capture" in r, r
