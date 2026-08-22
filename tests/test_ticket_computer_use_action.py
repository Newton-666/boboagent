"""TICKET-COMPUTER-USE-ACTION 专项测试 — computer_use 原子能力补全 + 降级机制。

覆盖（票验收）：
1. open_app/scroll 原子调用（mock AX/CGEvent，不碰真实系统）。
2. 降级 detection：computer use 模式想用非 computer_use 工具 → 拦/排查。
3. 先排查逻辑：工具 bug vs 网络问题（分情况走不同分支）。
4. normal 降级 → 必须用户确认（不自动）；auto 降级 → 自动。
5. 意图（goal）在降级时仍常驻（防漂移）。

依据 docs/DISCUSSION-SELF-EVOLVING.md 第 34/35/36 节：在用户指定系统上操作、
工具配合、降级先排查、意图是决策的根。
"""

import tools.computer_use as cu
from core import engine as eng


def _make_engine(cu=True, auto=False, confirm=None, test_mode=False):
    return eng.Engine(
        lambda *a, **k: {}, tool_executor=lambda *a, **k: None,
        computer_use_mode_getter=(lambda: cu),
        auto_mode_getter=(lambda: auto),
        confirm_callback=confirm, test_mode=test_mode,
    )


# ── 任务 A：open_app/scroll 原子调用 ──────────────────────────────────
def test_execute_open_app(monkeypatch):
    monkeypatch.setattr(cu, "_require_permission", lambda: None)
    calls = []

    class FakeWS:
        def launchApplication(self, name):
            calls.append(name)
            return True

    class FakeNS:
        @staticmethod
        def sharedWorkspace():
            return FakeWS()

    monkeypatch.setattr(cu, "NSWorkspace", FakeNS)
    r = cu.execute("open_app", app_name="Safari")
    assert "已打开应用 Safari" in r
    assert calls == ["Safari"]


def test_execute_scroll(monkeypatch):
    monkeypatch.setattr(cu, "_require_permission", lambda: None)
    posts = []
    monkeypatch.setattr(cu.Quartz, "CGEventPost", lambda tap, ev: posts.append(ev))
    monkeypatch.setattr(cu.Quartz, "CGEventCreateScrollWheelEvent",
                        lambda *a, **k: f"scroll:{a[2]}:{a[3]}")
    r = cu.execute("scroll", direction="down", amount=5)
    assert "已滚动 down 5 行" in r
    assert posts == ["scroll:1:5"]  # CGEventCreateScrollWheelEvent(None, unit, 1, val=5)


def test_schema_has_open_app_scroll():
    """TOOL_SCHEMA 注册 open_app/scroll action + app_name/direction/amount 参数。"""
    acts = cu.TOOL_SCHEMA["function"]["parameters"]["properties"]["action"]["enum"]
    assert "open_app" in acts and "scroll" in acts
    props = cu.TOOL_SCHEMA["function"]["parameters"]["properties"]
    assert "app_name" in props and "direction" in props and "amount" in props
    assert "打开应用（open_app）" in cu.TOOL_SCHEMA["function"]["description"] or "open_app" in cu.TOOL_SCHEMA["function"]["description"]


# ── 任务 B：降级机制（先排查 → normal 问用户 / auto 自动）──────────────
def test_degrade_deny_when_cu_not_tried():
    """computer use 模式还没用 computer_use 就想换工具（bash/curl）→ 拦。"""
    e = _make_engine(cu=True)
    # 未试 computer_use（_last_cu_result=None）→ deny
    assert e._degrade_decide("execute_terminal", {}, "x") == "deny"
    e.test_mode = False  # 绕过 pytest 注入的 test_mode（否则 _confirm 提前 return True）
    assert e._confirm("execute_terminal", {}, "reason") is False


def test_degrade_deny_tool_bug():
    """工具 bug（权限/未授权）→ 不靠降级糊弄，deny。"""
    e = _make_engine(cu=True)
    e._last_cu_result = "⛔ computer_use 需要系统权限"
    assert e._degrade_decide("execute_terminal", {}, "x") == "deny"
    assert e._cu_error_is_tool_bug(e._last_cu_result) is True
    # 截屏失败也属工具 bug
    e2 = _make_engine(cu=True)
    e2._last_cu_result = "错误: 截屏失败（大小异常）"
    assert e2._degrade_decide("execute_terminal", {}, "x") == "deny"


def test_degrade_allow_on_success_flexible():
    """computer_use 成功 → 换其他工具是"灵活配合"（34节），放行。"""
    e = _make_engine(cu=True)
    e._last_cu_result = "已点击 元素#3（AXButton）"
    assert e._degrade_decide("writefiles", {}, "x") == "allow"
    assert e._cu_error(e._last_cu_result) is False


def test_degrade_ask_normal():
    """网络/环境问题 + normal 模式 → 降级前必须先问用户（confirm_callback），不自动。"""
    records = []

    def cb(name, args, reason):
        records.append((name, reason))
        return True  # 用户允许

    e = _make_engine(cu=True, auto=False, confirm=cb)
    e._last_cu_result = "错误: 网络连接失败"
    assert e._degrade_decide("execute_terminal", {}, "x") == "ask"
    # _confirm 走降级 ask 分支 → 必须经 confirm_callback（不自动放行）
    e.test_mode = False  # 绕过 pytest 注入的 test_mode
    assert e._confirm("execute_terminal", {}, "reason") is True
    assert records  # 用户确认弹窗被调用
    assert e._cu_error_is_tool_bug("错误: 网络连接失败") is False  # 网络非工具bug


def test_degrade_auto_allow():
    """网络/环境问题 + auto 模式 → 自动降级（allow，不询问）。"""
    e = _make_engine(cu=True, auto=True)
    e._last_cu_result = "错误: 网络连接失败"
    assert e._degrade_decide("execute_terminal", {}, "x") == "allow"


def test_goal_resident_on_degrade():
    """意图（goal）在降级时仍常驻（防手段漂移：手段换了 GOAL 仍在）。"""
    e = _make_engine(cu=True, auto=True)
    e._current_intent = {"goal": "找DeepSeek视觉模型新闻", "target": "谷歌",
                          "means": ["谷歌搜索"]}
    e._last_cu_result = "错误: 网络连接失败"
    _dg = e._degrade_decide("execute_terminal", {}, "x")
    assert _dg == "allow"
    # 降级/换手段不丢 GOAL
    assert e._current_intent["goal"] == "找DeepSeek视觉模型新闻"
