"""computer_use — AX 树驱动的电脑操作工具（TICKET-COMPUTER-USE-CORE）。

铁律（owner 定）：
- 权限首用弹窗引导（禁静默默认开启操作）：首次调用检测 Screen Recording /
  Accessibility 权限，未授权 → 返回引导提示（去系统设置授权），**拒绝一切操作**，
  连 capture 都不给；不自动开权限（不打破隐私边界）。
- 密码/密钥绝不经过 LLM：本工具只做 AX 树驱动（系统给坐标），不接触凭据，
  敏感操作后续走系统弹窗。
- AX 树驱动（禁 vision 猜坐标的"截图分析后定位"模式）。

依赖：pyobjc（ApplicationServices AXUIElement + Quartz CGEvent）—— 已在 bobo .venv。
"""

import subprocess
import tempfile
import os

import ApplicationServices as AS
import Quartz
from AppKit import NSWorkspace

TOOL_NAME = "computer_use"

# 可交互元素 role（capture 索引 + click element=N 定位用）
_INTERACTIVE_ROLES = {
    "AXButton", "AXTextField", "AXCheckBox", "AXRadioButton",
    "AXMenuBarItem", "AXMenuItem", "AXStaticText", "AXWindow", "AXLink",
    "AXPopUpButton", "AXComboBox", "AXSlide", "AXDisclosureTriangle",
}

# 遍历限制（防巨大 AX 树撑爆上下文）
_MAX_DEPTH = 6
_MAX_ELEMENTS = 200


# ── 权限检测（首用弹窗引导）───────────────────────────────────────────
def _accessible() -> bool:
    """Accessibility（辅助功能）权限：控制他应用/键盘鼠标所需。"""
    try:
        return bool(AS.AXIsProcessTrusted())
    except Exception:
        return False


def _screen_recording() -> bool:
    """Screen Recording（屏幕录制）权限：截屏所需。"""
    try:
        return bool(Quartz.CGPreflightScreenCaptureAccess())
    except Exception:
        return False


def _permission_prompt() -> str:
    """未授权 → 返回引导弹窗/提示（连 capture 都不给）。"""
    return ("⛔ computer_use 需要系统权限，当前尚未授权，已拒绝一切操作。\n"
            "请先在系统设置中授权后重试：\n"
            "  系统设置 → 隐私与安全性 → 屏幕录制（Screen Recording）\n"
            "  系统设置 → 隐私与安全性 → 辅助功能（Accessibility）\n"
            "勾选运行 Bobo 的终端/应用（Terminal / iTerm2 / VS Code 等）。\n"
            "授权后须重启 Bobo 引擎进程（权限在进程启动时读取）。\n"
            "本工具不会自动开启权限，也不会绕过隐私边界。")


def _require_permission() -> str | None:
    """未授权返回引导提示字符串；已授权返回 None。"""
    if not _accessible() or not _screen_recording():
        return _permission_prompt()
    return None


# ── AX 树遍历 ─────────────────────────────────────────────────────
def _ax_point(v):
    """解包 AXValue 为 CGPoint（kAXPosition 等）。pyobjc 签名 3 参。"""
    if v is None:
        return None
    try:
        ok, p = AS.AXValueGetValue(v, AS.kAXValueCGPointType, None)
        if ok:
            return p
        return None
    except Exception:
        return None


def _ax_size(v):
    """解包 AXValue 为 CGSize（kAXSize 等）。"""
    if v is None:
        return None
    try:
        ok, s = AS.AXValueGetValue(v, AS.kAXValueCGSizeType, None)
        if ok:
            return s
        return None
    except Exception:
        return None


def _attr(el, name):
    """安全读取 AX 属性值；失败返回 None。"""
    try:
        err, val = AS.AXUIElementCopyAttributeValue(el, name, None)
        if err != 0:
            return None
        return val
    except Exception:
        return None


def _role(el):
    return _attr(el, "AXRole") or ""


def _title(el):
    return _attr(el, "AXTitle") or _attr(el, "AXDescription") or ""


def _frame(el):
    """返回 (x, y, w, h)（Quartz 全局坐标，原点左上，与 CGEvent 一致）。"""
    p = _ax_point(_attr(el, "AXPosition"))
    s = _ax_size(_attr(el, "AXSize"))
    if p is None or s is None:
        return None
    try:
        return (float(p.x), float(p.y), float(s.width), float(s.height))
    except Exception:
        return None


def _front_pid() -> int:
    """当前前台应用的 pid。"""
    try:
        return int(NSWorkspace.sharedWorkspace().frontmostApplication().processIdentifier())
    except Exception:
        return 0


def _iter_elements(root, depth=0):
    """DFS 遍历 AX 树，产生 (el, role, title, frame, depth)。"""
    if depth > _MAX_DEPTH:
        return
    role = _role(root)
    title = _title(root)
    frame = _frame(root)
    if role:
        yield (root, role, title, frame, depth)
    children = _attr(root, "AXChildren")
    if not children and role == "AXApplication":
        # 应用容器的窗口放 AXWindows（不是 AXChildren）
        children = _attr(root, "AXWindows")
    if children:
        for ch in children:
            yield from _iter_elements(ch, depth + 1)


def _collect_elements(pid):
    """收集前台应用的元素索引列表（与 capture / click 用同一顺序）。"""
    app = AS.AXUIElementCreateApplication(pid)
    items = []
    for (el, role, title, frame, depth) in _iter_elements(app):
        if frame is None:
            continue
        items.append({
            "el": el, "role": role, "title": title,
            "frame": frame, "depth": depth,
            "interactive": role in _INTERACTIVE_ROLES,
        })
        if len(items) >= _MAX_ELEMENTS:
            break
    return items


def _el_index_text(items) -> str:
    """capture 输出 AX 树元素索引（编号/role/name/坐标/可交互标记）。"""
    lines = ["[AX 树元素索引]（capture 时点 element=N 或用坐标点击）"]
    for i, it in enumerate(items, start=1):
        x, y, w, h = it["frame"]
        marker = "*" if it["interactive"] else " "
        nm = (it["title"] or "")[:30]
        lines.append(f"{i:>3}{marker} {it['role']:<20} {nm:<28} ({x:.0f},{y:.0f} {w:.0f}x{h:.0f})")
    return "\n".join(lines)


def _describe(image_path: str) -> str:
    """复用 read_local_file 的视觉描述。"""
    from tools.read_local_file import _describe_image
    try:
        return _describe_image(image_path)
    except Exception as e:
        return f"[视觉描述] 调用失败: {e}"


def _capture_png() -> str:
    """截屏到临时 PNG，返回路径。"""
    fd, path = tempfile.mkstemp(suffix=".png", prefix="cu_cap_")
    os.close(fd)
    try:
        subprocess.run(["screencapture", "-x", path], check=True, timeout=10)
    except Exception as e:
        return f"错误: 截屏失败: {e}"
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return f"错误: 截屏失败（大小异常）——请确认屏幕录制权限已授权"
    return path


def action_capture(describe: bool = True) -> str:
    """实时看屏幕：截屏 + AX 树元素索引（role/name/坐标）+ 视觉描述。"""
    pid = _front_pid()
    items = _collect_elements(pid)
    path = _capture_png()
    if path.startswith("错误:"):
        return path
    parts = [f"[屏幕快照] {path}"]
    parts.append(f"[前台应用] pid={pid} 共 {len(items)} 个元素")
    if describe:
        parts.append(_describe(path))
    parts.append(_el_index_text(items))
    return "\n\n".join(parts)


def _click_at(x: float, y: float):
    """在全局坐标 (x, y) 上点一次左键。"""
    pt = Quartz.CGPointMake(float(x), float(y))
    down = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseDown, pt, Quartz.kCGMouseButtonLeft)
    up = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseUp, pt, Quartz.kCGMouseButtonLeft)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)


def action_click(element=None, coordinate=None) -> str:
    """按 element=N（AX 索引）或 coordinate=[x,y]（像素坐标）点击。"""
    pid = _front_pid()
    items = _collect_elements(pid)
    if element is not None:
        try:
            idx = int(element)
        except (TypeError, ValueError):
            return f"错误: element 需为整数索引（1..{len(items)}）"
        if idx < 1 or idx > len(items):
            return f"错误: 元素索引越界（有效 1..{len(items)}）"
        it = items[idx - 1]
        x, y, w, h = it["frame"]
        cx, cy = x + w / 2.0, y + h / 2.0
        _click_at(cx, cy)
        return f"已点击 元素#{idx}（{it['role']} '{(it['title'] or '')[:20]}'） @ ({cx:.0f},{cy:.0f})"
    if coordinate is not None:
        try:
            cx, cy = float(coordinate[0]), float(coordinate[1])
        except (TypeError, ValueError, IndexError):
            return "错误: coordinate 需为 [x, y] 两个数字"
        _click_at(cx, cy)
        return f"已点击 坐标 ({cx:.0f},{cy:.0f})"
    return "错误: 请提供 element=N 或 coordinate=[x,y]"


def _post_key_combo(keyname: str):
    """发送组合键：'cmd+s' / 'ctrl+a' / 'esc' / 'return' 等。"""
    flags = 0
    if "cmd" in keyname:
        flags |= Quartz.kCGEventFlagMaskCommand
    if "ctrl" in keyname:
        flags |= Quartz.kCGEventFlagMaskControl
    if "opt" in keyname or "alt" in keyname:
        flags |= Quartz.kCGEventFlagMaskAlternate
    if "shift" in keyname:
        flags |= Quartz.kCGEventFlagMaskShift
    base = keyname.replace("cmd", "").replace("ctrl", "").replace("opt", "").replace("alt", "").replace("shift", "").strip().split("+")[-1]
    keycode = _keycode(base)
    if keycode is None:
        return False
    down = Quartz.CGEventCreateKeyboardEvent(None, keycode, True)
    Quartz.CGEventSetFlags(down, flags)
    up = Quartz.CGEventCreateKeyboardEvent(None, keycode, False)
    Quartz.CGEventSetFlags(up, flags)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)
    return True


_KEYCODE_MAP = {
    "a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7, "c": 8, "v": 9,
    "b": 11, "q": 12, "w": 13, "e": 14, "r": 15, "y": 16, "t": 17, "1": 18, "2": 19,
    "3": 20, "4": 21, "6": 22, "5": 23, "=": 24, "9": 25, "7": 26, "-": 27, "8": 28,
    "0": 29, "]": 30, "o": 31, "u": 32, "[": 33, "i": 34, "p": 35, "l": 37, "\n": 36,
    "return": 36, "j": 38, "'": 39, "k": 40, ";": 41, "\\": 42, ",": 43, "/": 44,
    "n": 45, "m": 46, ".": 47, "tab": 48, "esc": 53, "escape": 53, " ": 49,
}


def _keycode(name: str):
    n = name.lower()
    if n in _KEYCODE_MAP:
        return _KEYCODE_MAP[n]
    if len(n) == 1 and n.isalpha():
        return _KEYCODE_MAP[n]
    return None


def action_key(key: str) -> str:
    """组合键：'cmd+s' 等。"""
    if not key:
        return "错误: 请提供 key（如 'cmd+s'）"
    if _post_key_combo(key):
        return f"已发送组合键 {key}"
    return f"错误: 不认识 key: {key}（当前支持字母/数字及 cmd/ctrl/opt/shift）"


def action_type(text: str) -> str:
    """向当前应用输入文字（剪贴板 + cmd+v，安全应用使用，不碰密码框）。"""
    if text is None:
        return "错误: 请提供 text"
    # 密码/凭据绝不进 LLM：这里只做文本输入，不接触任何凭据字段
    try:
        p = subprocess.run(["pbcopy"], input=text.encode("utf-8"), timeout=5)
    except Exception as e:
        return f"错误: 复制到剪贴板失败: {e}"
    if _post_key_combo("cmd+v"):
        return f"已输入文字（{len(text)} 字符）"
    return "错误: 输入失败（无法发送 cmd+v）"


def execute(action: str, element=None, coordinate=None, text=None, key=None,
            describe: bool = True) -> str:
    """computer_use 工具入口。

    Args:
        action: capture / click / type / key
        element: click 时的 AX 元素索引（N）
        coordinate: click 时的像素坐标 [x, y]
        text: type 时输入的文字
        key: key 时的组合键（如 'cmd+s'）
        describe: capture 时是否附视觉描述（默认 True）
    """
    # 权限首用弹窗：未授权 → 返回引导提示，拒绝一切（连 capture 都不给）
    perm_err = _require_permission()
    if perm_err:
        return perm_err

    if action == "capture":
        return action_capture(describe)
    elif action == "click":
        return action_click(element=element, coordinate=coordinate)
    elif action == "type":
        return action_type(text)
    elif action == "key":
        return action_key(key)
    else:
        return (f"错误: 未知 action '{action}'。支持 capture / click / type / key。"
                "首次使用需在系统设置授权屏幕录制+辅助功能。")


TOOL_FUNC = execute

TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": "AX 树驱动的电脑操作：截屏看屏幕+AX 树元素索引（capture）、按元素索引或坐标点击（click）、输入文字（type）、组合键（key）。首次使用需系统权限：屏幕录制+辅助功能，未授权会返回引导提示。\\n\\n【何时用我——通用判断准则，自己判断任务对象在哪层】\\n当任务的操作对象在【可见界面层】时用我，比代码工具（grep/搜索/改代码）更优：\\n① 目标是界面元素（按钮/开关/菜单/输入框/文件图标/应用窗口）→ 用我点/输入，界面元素用代码工具够不着或很绕。\\n② 需要【看到】当前系统状态（屏幕长啥样/开了几个窗口/某应用有没有弹窗/界面卡没卡）→ 用我 capture，其他工具'看不见'屏幕。\\n③ 其他工具做不到/受限（搜索 API 挂了/VPN 不行/没 API/需操作真实浏览器绕过限制）→ 用我直接操作浏览器/应用。\\n④ 操作对象是图形界面应用（Safari/Finder/VSCode/邮件/任何 GUI 应用）→ 用我，这是唯一能直接操作 GUI 的。\\n\\n【何时不用我】操作对象在代码/文本/文件层（查函数定义/读文件/改代码/批量处理）→ 用 read_file/grep/edit_file/terminal 更快；terminal 有现成命令能做 → 不用我。\\n\\n关键：先判断任务对象在哪层——【界面层→用我】，【代码/文本/文件层→用其他工具】。不要看到'开关/模式/功能'就想到改代码，如果是界面上的按钮就点它。",
        "parameters": {"type": "object", "properties": {
            "action": {"type": "string", "enum": ["capture", "click", "type", "key"],
                       "description": "操作类型"},
            "element": {"type": "integer", "description": "click：AX 元素索引（capture 返回的 N）"},
            "coordinate": {"type": "array", "items": {"type": "number"},
                           "description": "click：像素坐标 [x, y]"},
            "text": {"type": "string", "description": "type：要输入的文字（不碰密码/凭据）"},
            "key": {"type": "string", "description": "key：组合键（如 'cmd+s'）"},
            "describe": {"type": "boolean", "default": True,
                         "description": "capture：是否附视觉描述（默认 True）"},
        }, "required": ["action"]}
    }
}


def register(reg):
    reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA)
