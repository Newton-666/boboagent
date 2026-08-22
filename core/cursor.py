"""虚拟光标（TICKET-COMPUTER-USE-CURSOR，COST-3 特批标记）。

owner 定稿（docs 第 37 节）：虚拟光标是"透明性"的钥匙——bobo 操作电脑时，
用户能看到它的光标在屏幕上移动/点击（透明），而不是黑箱。

实现：NSPanel 悬浮窗（透明/置顶/无边框/不抢焦点）+ 橙色圆点图形 +
插值平滑移动（跟手，user 强调）。bobo 每次 click/type/scroll 前
调用 show()/move_to()，用户看到光标滑到目标再操作。

⚠️ 关键（v3，COST-3 特批标记）：AppKit NSWindow 只能主线程实例化。
bobo 的 computer_use 在 worker 线程执行 → 直接创建 NSPanel 会抛
"NSWindow should only be instantiated on the main thread"。
→ 本模块内部起一个【专用光标线程】（跑 NSApplication runloop），
  所有 NSPanel 创建/移动/隐藏都 dispatch 到该线程执行，
  worker 线程只发请求（线程安全，不阻塞调用方）。

依赖：pyobjc（已在 bobo .venv）。
"""

import queue
import threading
import time

from AppKit import (
    NSPanel, NSBackingStoreBuffered, NSColor, NSBezierPath, NSMakeRect,
    NSMakePoint, NSView, NSApplication, NSWindowStyleMaskNonactivatingPanel,
    NSRunLoop, NSDate,
)

# ── 光标状态 ──
_cursor_panel = None
_visible = False
_lock = threading.Lock()
_cmd_queue: "queue.Queue" = queue.Queue()
_cursor_thread = None


class _CursorView(NSView):
    """画虚拟光标：橙色实心圆 + 白心 + 外圈描边（醒目）。"""

    def drawRect_(self, rect):
        NSColor.clearColor().setFill()
        NSBezierPath.fillRect_(rect)
        w, h = self.bounds().size.width, self.bounds().size.height
        cx, cy = w / 2, h / 2
        NSColor.colorWithCalibratedRed_green_blue_alpha_(0.95, 0.5, 0.1, 0.95).setFill()
        NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(cx - 14, cy - 14, 28, 28)).fill()
        NSColor.whiteColor().setFill()
        NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(cx - 4, cy - 4, 8, 8)).fill()
        NSColor.colorWithCalibratedRed_green_blue_alpha_(1.0, 0.4, 0.0, 0.8).setStroke()
        NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(cx - 17, cy - 17, 34, 34)).stroke()


def _make_panel():
    """（光标线程内）创建 NSPanel 悬浮窗。"""
    panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
        NSMakeRect(0, 0, 36, 36),
        NSWindowStyleMaskNonactivatingPanel,  # 不激活（不抢焦点）
        NSBackingStoreBuffered, False,
    )
    panel.setOpaque_(False)
    panel.setBackgroundColor_(NSColor.clearColor())
    panel.setHasShadow_(False)
    panel.setLevel_(300)  # 悬浮顶层
    panel.setIgnoresMouseEvents_(True)  # 不拦截鼠标（用户真光标照常用）
    view = _CursorView.alloc().initWithFrame_(NSMakeRect(0, 0, 36, 36))
    panel.setContentView_(view)
    return panel


def _cursor_loop():
    """光标专用线程：跑 NSApplication runloop，处理命令队列。"""
    global _cursor_panel
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(3)  # NSAccessory：不显示 dock，不抢激活
    while True:
        try:
            cmd = _cmd_queue.get(timeout=0.05)
        except queue.Empty:
            # 空闲时也跑 runloop（让 NSPanel 响应）
            NSRunLoop.currentRunLoop().runMode_beforeDate_(
                "kCFRunLoopDefaultMode", NSDate.dateWithTimeIntervalSinceNow_(0.02))
            continue
        try:
            kind = cmd.get("kind")
            if kind == "show":
                if _cursor_panel is None:
                    _cursor_panel = _make_panel()
                _cursor_panel.setFrameOrigin_(NSMakePoint(cmd["x"], cmd["y"]))
                _cursor_panel.orderFront_(None)
                _cursor_panel.display()
            elif kind == "move":
                if _cursor_panel is None:
                    _cursor_panel = _make_panel()
                    _cursor_panel.orderFront_(None)
                _cursor_panel.orderFront_(None)
                sx, sy = _cursor_panel.frame().origin.x, _cursor_panel.frame().origin.y
                steps = max(8, int(cmd.get("duration", 0.25) * 40))
                for i in range(1, steps + 1):
                    t = i / steps
                    e = t * t * (3 - 2 * t)  # ease-in-out 缓动
                    cx = sx + (cmd["x"] - sx) * e
                    cy = sy + (cmd["y"] - sy) * e
                    _cursor_panel.setFrameOrigin_(NSMakePoint(cx, cy))
                    _cursor_panel.display()
                    NSRunLoop.currentRunLoop().runMode_beforeDate_(
                        "kCFRunLoopDefaultMode",
                        NSDate.dateWithTimeIntervalSinceNow_(cmd.get("duration", 0.25) / steps))
            elif kind == "hide":
                if _cursor_panel is not None:
                    _cursor_panel.orderOut_(None)
        except Exception:
            pass  # 光标失败不影响主流程


def _ensure_thread():
    """确保光标线程在跑（惰性启动）。"""
    global _cursor_thread
    if _cursor_thread is None or not _cursor_thread.is_alive():
        _cursor_thread = threading.Thread(target=_cursor_loop, daemon=True)
        _cursor_thread.start()


def show(x: float, y: float, duration: float = 0.25):
    """显示虚拟光标并平滑移动到 (x, y)。线程安全（dispatch 到光标线程）。"""
    global _visible
    _ensure_thread()
    _cmd_queue.put({"kind": "show", "x": float(x), "y": float(y)})
    with _lock:
        _visible = True


def move_to(x: float, y: float, duration: float = 0.25):
    """平滑移动光标到 (x, y)（插值动画，跟手）。线程安全。"""
    global _visible
    _ensure_thread()
    _cmd_queue.put({"kind": "move", "x": float(x), "y": float(y),
                    "duration": float(duration)})
    with _lock:
        _visible = True


def hide():
    """隐藏虚拟光标。线程安全。"""
    global _visible
    _ensure_thread()
    _cmd_queue.put({"kind": "hide"})
    with _lock:
        _visible = False


def is_visible() -> bool:
    return _visible
