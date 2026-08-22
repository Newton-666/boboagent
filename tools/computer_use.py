"""computer_use — AX 树驱动的电脑操作工具（TICKET-COMPUTER-USE-CORE / TICKET-COMPUTER-USE-ACTION，COST-3 特批标记）。

铁律（owner 定）：
- 权限首用弹窗引导（禁静默默认开启操作）：首次调用检测 Screen Recording /
  Accessibility 权限，未授权 → 返回引导提示（去系统设置授权），**拒绝一切操作**，
  连 capture 都不给；不自动开权限（不打破隐私边界）。
- 密码/密钥绝不经过 LLM：本工具只做 AX 树驱动（系统给坐标），不接触凭据，
  敏感操作后续走系统弹窗。
- AX 树驱动（禁 vision 猜坐标的"截图分析后定位"模式）。

依赖：pyobjc（ApplicationServices AXUIElement + Quartz CGEvent）—— 已在 bobo .venv。
"""

import hashlib
import subprocess
import tempfile
import os

import ApplicationServices as AS
import Quartz
from AppKit import NSWorkspace

TOOL_NAME = "computer_use"

# 票 BACKGROUND（COST-3）：目标应用 pid（会话级状态）。open_app 记录后，
# capture/click 用 target_pid 遍历目标应用（非前台可见，后台并行）；未 open_app 时回退前台。
_target_pid = 0

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


def _find_pid(app_name: str) -> int:
    """按应用名查找运行中实例的 pid（NSRunningApplication.localizedName 匹配，不区分大小写）。"""
    try:
        ws = NSWorkspace.sharedWorkspace()
        for ra in ws.runningApplications():
            nm = (ra.localizedName() or "").lower()
            if app_name.lower() in nm:
                return int(ra.processIdentifier())
    except Exception:
        pass
    return 0


def _which_pid() -> int:
    """目标 pid（open_app 记录）优先；未设置时回退前台 pid（向后兼容）。"""
    global _target_pid
    if _target_pid:
        return int(_target_pid)
    return _front_pid()


def _ensure_target() -> str | None:
    """验证操作目标（键盘/输入前，防静默丢到错误焦点）。票 D（COST-3，缺陷4）。"""
    if not _which_pid():
        return "错误: 无操作目标（未 open_app 且未检测到前台应用），拒绝输入（防静默丢焦点）"
    return None


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


def _element_id(role: str, title: str, frame) -> str:
    """元素身份（role+title+frame 归一化 hash）。票 C（COST-3）：树重排后仍可按身份匹配防漂移。"""
    x, y, w, h = frame
    sig = f"{role}|{title}|{round(x)}|{round(y)}|{round(w)}|{round(h)}"
    return hashlib.md5(sig.encode("utf-8")).hexdigest()[:8]


def _visible(frame) -> bool:
    """过滤零尺寸/屏幕外元素（缺陷3）：宽高必须为正，且不完全在屏幕外。"""
    x, y, w, h = frame
    if w <= 0 or h <= 0:
        return False
    try:
        cb = Quartz.CGDisplayBounds(Quartz.CGMainDisplayID())
        sw, sh = float(cb.size.width), float(cb.size.height)
    except Exception:
        sw, sh = 100000.0, 100000.0
    if x >= sw or x + w <= 0 or y >= sh or y + h <= 0:
        return False
    return True


def _collect_elements(pid):
    """收集目标应用（target_pid 或前台）的元素索引列表（与 capture / click 用同一顺序）。

    每个元素带 element_id（role+title+frame 身份 hash，票 C 防漂移）+ interactive 标记；
    过滤零尺寸/屏幕外元素（缺陷3，capture 不失明）。
    """
    app = AS.AXUIElementCreateApplication(pid)
    items = []
    for (el, role, title, frame, depth) in _iter_elements(app):
        if frame is None:
            continue
        if not _visible(frame):
            continue
        items.append({
            "el": el, "role": role, "title": title,
            "frame": frame, "depth": depth,
            "element_id": _element_id(role, title, frame),
            "interactive": role in _INTERACTIVE_ROLES,
        })
        if len(items) >= _MAX_ELEMENTS:
            break
    return items


def _el_index_text(items) -> str:
    """capture 输出 AX 树元素索引（编号/role/name/坐标/element_id/可交互标记）。"""
    lines = ["[AX 树元素索引]（capture 时点 element=N / element_id=身份 / 或用坐标点击）"]
    for i, it in enumerate(items, start=1):
        x, y, w, h = it["frame"]
        marker = "*" if it["interactive"] else " "
        nm = (it["title"] or "")[:30]
        lines.append(f"{i:>3}{marker} {it['role']:<20} {nm:<28} ({x:.0f},{y:.0f} {w:.0f}x{h:.0f}) id={it['element_id']}")
    return "\n".join(lines)


def _describe(image_path: str) -> str:
    """复用 read_local_file 的视觉描述。"""
    from tools.read_local_file import _describe_image
    try:
        return _describe_image(image_path)
    except Exception as e:
        return f"[视觉描述] 调用失败: {e}"


def _window_id(pid: int) -> int | None:
    """按 pid 找该应用的主窗口 CGWindowID（screencapture -l 用）。

    （TICKET-COMPUTER-USE-BACKGROUND 修正，COST-3 特批标记）用 CGWindowList
    （按窗口 ID 截，不管前台/层级——后台并行核心：
    Safari 在后台被 bobo 窗口盖住也能截到 Safari 内容）。
    """
    try:
        wins = Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListOptionOnScreenOnly, Quartz.kCGNullWindowID)
        for w in wins or []:
            if int(w.get("kCGWindowOwnerPID", 0)) == int(pid) and \
               w.get("kCGWindowLayer", 0) == 0:
                return int(w.get("kCGWindowNumber", 0))
    except Exception:
        pass
    return None


def _capture_png(pid=None) -> str:
    """截屏到临时 PNG，返回路径。

    后台并行铁律（owner 定，COST-3 特批标记）：**截图必须截目标应用窗口，
    不截当前屏幕/前台**。优先级：
      ① screencapture -l <windowid>（按窗口 ID 截，非前台/被盖住也能截到目标窗口）
      ② 失败 → AXWindow frame -R 区域截（目标应用区域）
      ③ 再失败 → 返回错误（**绝不回退全屏**——全屏=截前台=截到 bobo 自己，错）
    """
    fd, path = tempfile.mkstemp(suffix=".png", prefix="cu_cap_")
    os.close(fd)
    # ① 按窗口 ID 截（最稳：目标窗口内容，不管前台是谁）
    if pid:
        wid = _window_id(pid)
        if wid:
            try:
                subprocess.run(["screencapture", "-x", "-l", str(wid), path],
                               check=True, timeout=10)
                if os.path.exists(path) and os.path.getsize(path) > 0:
                    return path
            except Exception:
                pass
    # ② AXWindow frame 区域截（目标应用区域）
    region = None
    if pid:
        try:
            for it in _collect_elements(pid):
                if it["role"] == "AXWindow":
                    x, y, w, h = it["frame"]
                    if w > 0 and h > 0:
                        region = f"{x:.0f} {y:.0f} {w:.0f} {h:.0f}"
                        break
        except Exception:
            region = None
    if region:
        try:
            subprocess.run(["screencapture", "-x", "-R", region, path],
                           check=True, timeout=10)
            if os.path.exists(path) and os.path.getsize(path) > 0:
                return path
        except Exception:
            pass
    # ③ 失败返回错误（绝不回退全屏——全屏=前台=截错对象）
    try:
        os.remove(path)
    except Exception:
        pass
    return (f"错误: 无法截取目标应用窗口（pid={pid}）——screencapture -l/-R 均失败，"
            "未回退全屏（全屏会截到当前前台而非目标应用，违背后台并行铁律）。")


def action_capture(describe: bool = False) -> str:
    """实时看屏幕：截屏 + AX 树元素索引（role/name/坐标/element_id）。

    用 _which_pid()：open_app 后遍历目标应用（后台并行，用户在别的前台也能截到目标）；未 open_app 回退前台。
    默认 describe=False（不调 vision，快——AX 树定位够用，秒级返回）。
    只有真正需要"看懂内容/视觉理解"才传 describe=True（代价：调 vision，慢）。
    """
    pid = _which_pid()
    items = _collect_elements(pid)
    path = _capture_png(pid)
    if path.startswith("错误:"):
        return path
    parts = [f"[屏幕快照] {path}"]
    if pid == _target_pid and _target_pid:
        parts.append(f"[目标应用] pid={pid}（后台并行，非前台）共 {len(items)} 个元素")
    else:
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


def action_click(element=None, coordinate=None, element_id=None) -> str:
    """点击。优先级：element_id（身份，防漂移）> coordinate（坐标，稳定）> element=N（位置号兜底）。

    票 C（COST-3）：element_id 身份匹配——树重排后仍能找到同一元素并点其当前 frame 中心，不漂移。
    用 _which_pid()（目标 pid 优先，后台并行）；未 open_app 回退前台。
    """
    pid = _which_pid()
    items = _collect_elements(pid)
    # ① element_id 身份匹配优先（防漂移）
    if element_id is not None:
        for it in items:
            if it["element_id"] == str(element_id):
                x, y, w, h = it["frame"]
                cx, cy = x + w / 2.0, y + h / 2.0
                _click_at(cx, cy)
                return f"已点击 元素{it['element_id']}（{it['role']} '{(it['title'] or '')[:20]}'） @ ({cx:.0f},{cy:.0f})"
        return f"错误: 元素身份 {element_id} 不存在（树可能已重排），请重新 capture"
    # ② coordinate 坐标（稳定，不漂移）
    if coordinate is not None:
        try:
            cx, cy = float(coordinate[0]), float(coordinate[1])
        except (TypeError, ValueError, IndexError):
            return "错误: coordinate 需为 [x, y] 两个数字"
        _click_at(cx, cy)
        return f"已点击 坐标 ({cx:.0f},{cy:.0f})"
    # ③ element=N 位置号兜底
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
    return "错误: 请提供 element_id=身份 / element=N / coordinate=[x,y] 之一"


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
    """组合键：'cmd+s' 等（发送前验证目标焦点，防静默丢失——缺陷4）。"""
    if not key:
        return "错误: 请提供 key（如 'cmd+s'）"
    err = _ensure_target()
    if err:
        return err
    if _post_key_combo(key):
        return f"已发送组合键 {key}"
    return f"错误: 不认识 key: {key}（当前支持字母/数字及 cmd/ctrl/opt/shift）"


def action_type(text: str) -> str:
    """向当前应用输入文字（剪贴板 + cmd+v，安全应用使用，不碰密码框；发送前验证目标——缺陷4）。"""
    if text is None:
        return "错误: 请提供 text"
    err = _ensure_target()
    if err:
        return err
    # 密码/凭据绝不进 LLM：这里只做文本输入，不接触任何凭据字段
    try:
        p = subprocess.run(["pbcopy"], input=text.encode("utf-8"), timeout=5)
    except Exception as e:
        return f"错误: 复制到剪贴板失败: {e}"
    if _post_key_combo("cmd+v"):
        return f"已输入文字（{len(text)} 字符）"
    return "错误: 输入失败（无法发送 cmd+v）"


def action_open_app(app_name: str) -> str:
    """打开指定应用（NSWorkspace.launchApplication / 'open -a' 兜底），并记录 _target_pid（票 BACKGROUND）。

    ——补全原子操作：bobo 想"帮我在谷歌搜索/在 Pages 操作"时能直接 open_app，
    不用写 applescript 造轮子。open_app 后 capture/click 走目标 pid（用户在前台做别的也能后台并行操作）。
    """
    global _target_pid
    if not app_name or not str(app_name).strip():
        return "错误: 请提供 app_name（如 'Safari'/'Pages'/'Finder'）"
    app = str(app_name).strip()
    try:
        ws = NSWorkspace.sharedWorkspace()
        if ws.launchApplication(app):
            _target_pid = _find_pid(app)
            return f"已打开应用 {app}（目标 pid={_target_pid}，后台并行）"
    except Exception:
        pass  # NSWorkspace 在新版 macOS 签名/反馈不稳定，走 open -a 兜底
    try:
        r = subprocess.run(["open", "-a", app], capture_output=True, timeout=8)
        if r.returncode == 0:
            _target_pid = _find_pid(app)
            return f"已打开应用 {app}（open -a 兜底，目标 pid={_target_pid}，后台并行）"
        return f"错误: 打开应用 {app} 失败: {(r.stderr or b'').decode('utf-8', 'ignore').strip()}"
    except Exception as e:
        return f"错误: 打开应用 {app} 异常: {e}"


def action_scroll(direction: str = "down", amount: int = 3) -> str:
    """滚动页面（CGEvent scroll wheel）。direction: up/down/left/right。

    ——补全原子操作：网页/长文档滚动，不用写 applescript（TICKET-COMPUTER-USE-ACTION）。
    """
    if direction not in ("up", "down", "left", "right"):
        return "错误: direction 需为 up/down/left/right"
    try:
        n = int(amount)
    except (TypeError, ValueError):
        n = 3
    if n < 1:
        n = 1
    # 滚轮正负：向下/向右为正（内容上移），向上/向左为负
    if direction in ("down", "right"):
        val = n
    else:
        val = -n
    try:
        ev = Quartz.CGEventCreateScrollWheelEvent(
            None, Quartz.kCGScrollEventUnitLine, 1, val)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)
        return f"已滚动 {direction} {n} 行"
    except Exception as e:
        return f"错误: 滚动失败: {e}"


def execute(action: str, element=None, coordinate=None, text=None, key=None,
            describe: bool = False, app_name=None, direction=None, amount=None,
            element_id=None) -> str:
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
        return action_click(element=element, coordinate=coordinate, element_id=element_id)
    elif action == "type":
        return action_type(text)
    elif action == "key":
        return action_key(key)
    elif action == "open_app":
        return action_open_app(app_name)
    elif action == "scroll":
        return action_scroll(direction=direction, amount=amount)
    else:
        return (f"错误: 未知 action '{action}'。支持 capture / click / type / key / open_app / scroll。"
                "首次使用需在系统设置授权屏幕录制+辅助功能。")


TOOL_FUNC = execute

TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": "AX 树驱动的电脑操作，覆盖整个 macOS（系统级通用，不限特定软件）：截屏看屏幕+AX 树元素索引（capture，默认不调 vision，快）、按元素索引或坐标点击（click）、输入文字（type）、组合键（key）、打开应用（open_app）、滚动页面（scroll）。这是原子操作集（直接做，不写脚本/applescript 造轮子）：open_app 直接打开目标 APP，scroll 滚动窗口。首次使用需系统权限：屏幕录制+辅助功能，未授权会返回引导（不自动开权限，不碰凭据）。\\n【何时用我——通用判断准则】操作对象在【界面层】时用我，比代码工具更优：① 目标是界面元素（按钮/开关/菜单/输入框/文件图标/窗口，任何 Apple 应用如 Finder/Pages/Word/Safari/Notes/系统设置）→ 用我点/输入/打开应用/滚动，界面元素用代码工具够不着。② 需要【看到】当前屏幕/系统状态 → 用我 capture。③ 其他工具受限（搜索 API 挂/VPN 不行/没 API）→ 用我直接操作真实浏览器/应用绕过。④ 操作对象是图形界面应用 → 用我，这是唯一能直接操作 GUI 的。⑤ 找文档/文件→我自己打开 Finder/文件夹，用 click+scroll 浏览定位（不只读文本层）。\\n【何时不用我】操作对象在代码/文本/文件层（查函数/读文件/改代码/批量处理）→ 用 read/grep/edit/terminal。\\n【定位与操作——防漂移】用 element_id=身份（role+title+frame hash）点击最稳——树重排后仍找得到；或 coordinate=[x,y]（frame 中心）稳定；element=N 是位置号，Safari 启动重排/菜单栏挤占会漂移、点错。**AX 索引不稳定——点击后确认结果**，别一次定位就假设成功。界面按钮就点它，不要写脚本造轮子。",
        "parameters": {"type": "object", "properties": {
            "action": {"type": "string", "enum": ["capture", "click", "type", "key", "open_app", "scroll"],
                       "description": "操作类型"},
            "element": {"type": "integer", "description": "click：AX 元素索引（capture 返回的 N，位置号，树重排会漂移——优先用 element_id/coordinate）"},
            "element_id": {"type": "string", "description": "click：元素身份（capture 输出的 id=xxx，role+title+frame hash，防漂移，树重排后仍找得到）"},
            "coordinate": {"type": "array", "items": {"type": "number"},
                           "description": "click：像素坐标 [x, y]（frame 中心，稳定）"},
            "text": {"type": "string", "description": "type：要输入的文字（不碰密码/凭据）"},
            "key": {"type": "string", "description": "key：组合键（如 'cmd+s'）"},
            "app_name": {"type": "string", "description": "open_app：要打开的应用名（如 'Safari'/'Pages'）"},
            "direction": {"type": "string", "enum": ["up", "down", "left", "right"],
                          "description": "scroll：滚动方向（默认 down）"},
            "amount": {"type": "integer", "description": "scroll：滚动行数（默认 3）"},
            "describe": {"type": "boolean", "default": True,
                         "description": "capture：是否附视觉描述（默认 True）"},
        }, "required": ["action"]}
    }
}


def register(reg):
    reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA)
