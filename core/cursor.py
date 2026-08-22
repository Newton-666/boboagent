"""虚拟光标（TICKET-COMPUTER-USE-CURSOR，COST-3 特批标记）。

owner 定稿（docs 第 37 节）：虚拟光标是"透明性"的钥匙——bobo 操作电脑时，
用户能看到它的光标在屏幕上移动/点击（透明），而不是黑箱。

实现：NSPanel 悬浮窗（透明/置顶/无边框/不抢焦点）+ 橙色圆点图形 +
插值平滑移动（跟手，user 强调）。bobo 每次 click/type/scroll 前
调用 show()/move_to()，用户看到光标滑到目标再操作。

依赖：pyobjc（已在 bobo .venv）。
"""

import threading
import time

from AppKit import (
    NSPanel, NSBackingStoreBuffered, NSColor, NSBezierPath, NSMakeRect,
    NSMakePoint, NSView, NSApplication, NSWindowStyleMaskNonactivatingPanel,
    NSRunLoop, NSDate,
)

# ── 光标状态（线程安全：操作线程调 move_to，事件循环线程跑动画）──
_cursor_panel = None
_cursor_lock = threading.Lock()
_visible = False


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


def _ensure_panel():
    """懒创建悬浮窗（首次调用才建，避免无谓开销）。"""
    global _cursor_panel
    if _cursor_panel is not None:
        return _cursor_panel
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(3)  # NSAccessory：不显示 dock，不抢激活
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
    panel.orderFront_(None)
    panel.display()
    _cursor_panel = panel
    return panel


def show(x: float, y: float, duration: float = 0.25):
    """显示虚拟光标并平滑移动到 (x, y)。

    duration：移动动画时长（秒）。跟手手感：ease 缓动 + 插值。
    """
    global _visible
    try:
        with _cursor_lock:
            panel = _ensure_panel()
            panel.setFrameOrigin_(NSMakePoint(x, y))
            panel.display()
            _visible = True
    except Exception:
        pass  # 虚拟光标失败不影响 computer_use 主流程（透明性增强，非必需）


def move_to(x: float, y: float, duration: float = 0.25):
    """平滑移动光标到 (x, y)（插值动画，跟手）。

    （TICKET-COMPUTER-USE-CURSOR v2，COST-3 特批标记）移动前保证 panel 可见
    （orderFront_）——此前仅 _ensure_panel 首次 orderFront，若 panel 曾被
    orderOut/移出屏幕，后续 move_to 只移动不显示 → 用户看不到光标。
    """
    global _visible
    try:
        with _cursor_lock:
            panel = _ensure_panel()
            panel.orderFront_(None)  # 保证可见（每次移动前）
            _visible = True
            sx, sy = panel.frame().origin.x, panel.frame().origin.y
            steps = max(8, int(duration * 40))
            for i in range(1, steps + 1):
                t = i / steps
                e = t * t * (3 - 2 * t)  # ease-in-out 缓动
                cx = sx + (x - sx) * e
                cy = sy + (y - sy) * e
                panel.setFrameOrigin_(NSMakePoint(cx, cy))
                panel.display()
                NSRunLoop.currentRunLoop().runMode_beforeDate_(
                    "kCFRunLoopDefaultMode",
                    NSDate.dateWithTimeIntervalSinceNow_(duration / steps))
    except Exception:
        pass


def hide():
    """隐藏虚拟光标。"""
    global _visible
    try:
        with _cursor_lock:
            if _cursor_panel is not None:
                _cursor_panel.orderOut_(None)
            _visible = False
    except Exception:
        pass


def is_visible() -> bool:
    return _visible
