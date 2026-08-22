"""TICKET-COMPUTER-USE-BACKGROUND 专项测试 — 目标 pid 机制 + 指定窗口截图 + 元素身份防漂移。

覆盖（票验收）：
1. open_app 后 target_pid 记录，capture/click 用 target_pid（非前台也能操作）。
2. 指定窗口截图（mock screencapture -R 区域截 / AX window frame）。
3. 元素身份：element_id 身份校验（树重排后仍点对，不漂移）+ 坐标优先。
4. 零尺寸/屏幕外元素被过滤。
5. type/key 焦点验证（防静默丢失）。
6. 无 target_pid 回退前台（兼容）。

依据 docs/DISCUSSION-SELF-EVOLVING.md 第 34/35/36 节 + owner 定稿
（用户在 bobo 聊天框/前台用别的 APP 时，bobo 能"看到并操作非前台目标应用"后台并行）。
"""

import pytest
from types import SimpleNamespace

import tools.computer_use as cu


@pytest.fixture(autouse=True)
def _reset_targetpid():
    """每个测试前重置全局 _target_pid（避免跨用例污染）。"""
    cu._target_pid = 0
    yield
    cu._target_pid = 0


# ── 任务 A：目标 pid 机制 ───────────────────────────────────────────────
def test_open_app_records_target_pid(monkeypatch):
    """open_app 成功后记录 _target_pid（非前台也能操作目标应用）。"""
    monkeypatch.setattr(cu, "_require_permission", lambda: None)

    class FakeRA:
        def __init__(s, name, pid):
            s.nm, s.pid = name, pid

        def localizedName(s):
            return s.nm

        def processIdentifier(s):
            return s.pid

    class FakeWS:
        def launchApplication(s, n):
            return True

        def runningApplications(s):
            return [FakeRA("Safari", 1234)]

    class FakeNS:
        @staticmethod
        def sharedWorkspace():
            return FakeWS()

    monkeypatch.setattr(cu, "NSWorkspace", FakeNS)
    r = cu.execute("open_app", app_name="Safari")
    assert "目标 pid=1234" in r
    assert cu._target_pid == 1234


def test_capture_uses_target_pid(monkeypatch):
    """capture 用 target_pid 遍历目标应用（后台并行，非前台）。"""
    cu._target_pid = 1234
    used = []
    monkeypatch.setattr(cu, "_capture_png",
                        lambda pid: (used.append(pid), "/tmp/x.png")[1])
    monkeypatch.setattr(cu, "_collect_elements",
                        lambda pid: (used.append(pid), [
                            {"role": "AXButton", "title": "Go", "frame": (10, 10, 50, 30),
                             "element_id": "ab12cd34", "interactive": True}])[1])
    monkeypatch.setattr(cu, "_describe", lambda p: "desc")
    r = cu.action_capture(describe=False)
    assert "[目标应用] pid=1234" in r
    assert used and used[0] == 1234  # 遍历的是 target_pid 而非前台


def test_capture_fallback_front_when_no_target(monkeypatch):
    """无 target_pid（未 open_app）→ 回退前台 pid（向后兼容）。"""
    cu._target_pid = 0
    monkeypatch.setattr(cu, "_front_pid", lambda: 999)
    monkeypatch.setattr(cu, "_capture_png", lambda pid: "/tmp/x.png")
    monkeypatch.setattr(cu, "_collect_elements", lambda pid: [])
    monkeypatch.setattr(cu, "_describe", lambda p: "d")
    r = cu.action_capture(describe=False)
    assert "[前台应用] pid=999" in r


# ── 任务 C：元素身份防漂移 ──────────────────────────────────────────────
def test_click_element_id_match(monkeypatch):
    """element_id 身份匹配 → 点其当前 frame 中心（树重排后仍点对）。"""
    clicked = []
    monkeypatch.setattr(cu, "_collect_elements", lambda pid: [
        {"role": "AXButton", "title": "Go", "frame": (10, 10, 50, 30),
         "element_id": "ab12cd34", "interactive": True}])
    monkeypatch.setattr(cu, "_click_at", lambda x, y: clicked.append((x, y)))
    r = cu.action_click(element_id="ab12cd34")
    assert "ab12cd34" in r
    assert clicked == [(35.0, 25.0)]  # frame 中心


def test_click_element_id_not_found(monkeypatch):
    """element_id 不存在（树重排）→ 报错提示重新 capture，不盲目点击。"""
    monkeypatch.setattr(cu, "_collect_elements", lambda pid: [])
    r = cu.action_click(element_id="nonexist")
    assert "不存在" in r and "重新" in r


def test_click_coordinate_priority(monkeypatch):
    """coordinate 坐标（稳定）优先于 element=N 位置号。"""
    clicked = []
    monkeypatch.setattr(cu, "_collect_elements", lambda pid: [])
    monkeypatch.setattr(cu, "_click_at", lambda x, y: clicked.append((x, y)))
    r = cu.action_click(coordinate=[100, 200])
    assert clicked == [(100.0, 200.0)]
    assert "已点击 坐标" in r


# ── 任务 D：缺陷修复 ─────────────────────────────────────────────────────
def test_zero_size_elements_filtered(monkeypatch):
    """零尺寸元素被过滤（缺陷3：capture 不失明）。"""
    monkeypatch.setattr(cu, "AS", SimpleNamespace(AXUIElementCreateApplication=lambda pid: None))
    monkeypatch.setattr(cu, "_iter_elements", lambda app, depth=0: iter([
        (None, "AXButton", "zero", (10, 10, 0, 0), 0),
        (None, "AXButton", "go", (10, 10, 50, 30), 0),
    ]))
    items = cu._collect_elements(999)
    assert len(items) == 1
    assert items[0]["title"] == "go"


def test_element_id_stable_hash(monkeypatch):
    """element_id 是 role+title+frame 的稳定身份 hash（多次计算一致，可身份匹配）。"""
    f1 = (10, 10, 50, 30)
    assert cu._element_id("AXButton", "Go", f1) == cu._element_id("AXButton", "Go", f1)
    assert cu._element_id("AXButton", "Go", f1) != cu._element_id("AXButton", "Back", f1)


def test_type_key_validates_target(monkeypatch):
    """type/key 前验证目标焦点（缺陷4：无目标时拒绝，防静默丢输入）。"""
    monkeypatch.setattr(cu, "_front_pid", lambda: 0)
    cu._target_pid = 0
    assert "无操作目标" in cu.action_type("hi")
    assert "无操作目标" in cu.action_key("cmd+s")


def test_window_region_capture(monkeypatch):
    """指定窗口截图：有目标 AXWindow frame → screencapture -R 区域截（后台可见）。"""
    cmds = []
    monkeypatch.setattr(cu, "_collect_elements", lambda pid: [
        {"role": "AXWindow", "title": "Safari", "frame": (100, 50, 800, 600),
         "element_id": "w1", "interactive": True}])
    monkeypatch.setattr(cu.subprocess, "run",
                        lambda cmd, **k: (cmds.append(cmd), SimpleNamespace(returncode=0))[1])
    monkeypatch.setattr(cu.tempfile, "mkstemp", lambda *a, **k: (3, "/tmp/f.png"))
    monkeypatch.setattr(cu.os, "close", lambda fd: None)
    monkeypatch.setattr(cu.os.path, "exists", lambda p: True)
    monkeypatch.setattr(cu.os.path, "getsize", lambda p: 100)
    cu._target_pid = 123
    cu._capture_png(123)
    assert cmds
    assert "-R" in cmds[0]
    assert "100 50 800 600" in " ".join(cmds[0])  # 目标窗口 frame 区域（后台可见）
