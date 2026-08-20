"""GUI 测试基建（TICKET-GUI-T1）— 桌面端单文件测试共享工具。

背景：apps/desktop/dist/index.html 是 4687 行 vanilla 单文件（唯一真身），
无构建管线、无前端测试。本 harness 提供三类能力，让任何前端 bug 修复
都能快速写测试：

1. extract_main_js()  — 提取主 <script> 块（HTML 里最后一段 JS）
2. extract_func()     — 按 { } 括号配对提取指定 function 源码
3. run_node()         — 在 node 里实跑提取的 JS（行为验证）
4. DOM 桩             — make_el() 最小 DOM 元素桩（node 环境无 DOM）
5. bracket_balance()  — 括号平衡检查（结构完整性兜底）

用法示例见 tests/test_ticket_gui_f19.py、test_gui_structure.py。
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
GUI_FILE = ROOT / "apps" / "desktop" / "dist" / "index.html"

# 关键函数清单：缺一个 = 渲染链路断裂（结构检查用）
CRITICAL_FUNCS = [
    "addMsg",            # 消息渲染
    "addTool",           # 工具卡
    "createThinkBox",    # 思考框
    "collapseThinkBox",  # 思考框收束
    "loadSession",       # 会话加载（点击入口）
    "loadSessions",      # 会话列表
    "renderFullHistory",          # 短会话全量渲染
    "renderFullHistoryWindowed",  # 长会话窗口化渲染
    "buildHistUnits",    # 窗口化数据模型
    "renderHistWindow",  # 窗口化 DOM 渲染
    "histWindowOnScroll",# 窗口化滚动
    "clearChat",         # 清空聊天区
    "stopThinking",      # 中断
    "sendPrompt",        # 发消息（prompt.submit）
    "newChat",           # 新会话
    "splitThinking",     # 思考段剥离
    "renderSessions",    # 侧栏渲染
    "currentBusy",       # 忙碌状态
]

# 前端事件注册白名单：缺一个 = 事件断链
CRITICAL_EVENTS = [
    "gateway.ready",
    "message.start",
    "message.delta",
    "message.complete",
    "reasoning.delta",
    "tool.start",
    "tool.complete",
    "status.update",
    "notes.changed",
    "terminal.output",
    "approval.request",
    "backend.exited",
]


def extract_main_js() -> str:
    """提取主 <script> 块（最后一段，即应用主脚本）。"""
    src = GUI_FILE.read_text(encoding="utf-8")
    blocks = re.findall(r"<script>(.*?)</script>", src, re.S)
    assert blocks, "index.html 无 <script> 块"
    return blocks[-1]


def extract_func(src: str, fname: str) -> str:
    """按 { } 括号配对提取 function <fname> 完整源码（含 async 前缀）。

    找不到或括号不闭合 → 抛 AssertionError（结构检查语义）。
    """
    m = re.search(r"(?:async\s+)?function\s+" + fname + r"\s*\(", src)
    assert m, f"未找到 function {fname}"
    open_i = src.index("{", m.start())
    depth = 0
    for i in range(open_i, len(src)):
        c = src[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return src[m.start():i + 1]
    raise AssertionError(f"function {fname} 括号不闭合")


def run_node(js: str, timeout: int = 30) -> str:
    """在 node 里实跑 JS，失败抛 AssertionError（带 stderr）。"""
    r = subprocess.run(
        ["node", "-e", js], capture_output=True, text=True, timeout=timeout
    )
    if r.returncode != 0:
        raise AssertionError(f"node 执行失败: {r.stderr}")
    return r.stdout


def make_el(tag: str = "div"):
    """最小 DOM 元素桩（node 无 DOM；支持测试所需的最小操作集）。"""
    el = {
        "tagName": tag.upper(),
        "_className": "",
        "_innerHTML": "",
        "_textContent": "",
        "style": {},
        "dataset": {},
        "children": [],
        "parentNode": None,
        "classList": {
            "_set": set(),
            "add": lambda c: el["classList"]["_set"].add(c),
            "remove": lambda c: el["classList"]["_set"].discard(c),
            "toggle": lambda c: (
                el["classList"]["_set"].discard(c)
                if c in el["classList"]["_set"]
                else el["classList"]["_set"].add(c)
            ) or (c in el["classList"]["_set"]),
            "contains": lambda c: c in el["classList"]["_set"],
        },
        "appendChild": lambda c: (el["children"].append(c), setattr(c, "parentNode", el)),
        "remove": lambda: (
            el["parentNode"]["children"].remove(el)
            if el["parentNode"] and el in el["parentNode"]["children"]
            else None
        ),
        "setAttribute": lambda k, v: el["dataset"].__setitem__(k, v),
        "getAttribute": lambda k: el["dataset"].get(k),
        "addEventListener": lambda *a: None,
        "removeEventListener": lambda *a: None,
        "querySelector": lambda sel: None,
        "querySelectorAll": lambda sel: [],
        "focus": lambda: None,
        "click": lambda: None,
    }

    def _get_html(self_):
        return el["_innerHTML"]

    def _set_html(self_, v):
        el["_innerHTML"] = v
        el["children"] = []

    def _get_text(self_):
        return el["_textContent"]

    def _set_text(self_, v):
        el["_textContent"] = str(v)

    def _get_off_h(self_):
        return 100

    def _get_cli_h(self_):
        return 600

    def _get_scroll_h(self_):
        return len(el["children"]) * 100 + 1000

    def _get_scroll_top(self_):
        return 0

    def _set_scroll_top(self_, v):
        pass

    el["innerHTML"] = property(_get_html, _set_html)
    el["textContent"] = property(_get_text, _set_text)
    el["offsetHeight"] = property(_get_off_h)
    el["clientHeight"] = property(_get_cli_h)
    el["scrollHeight"] = property(_get_scroll_h)
    el["scrollTop"] = property(_get_scroll_top, _set_scroll_top)
    return el


def bracket_balance(js: str) -> int:
    """返回 { } 配对后的最终深度（0=平衡，负数=提前闭合）。"""
    depth = 0
    for c in js:
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth < 0:
                return depth
    return depth


def assert_structure() -> None:
    """结构完整性检查（GUI-T2 核心）：
    1. 括号平衡
    2. 关键函数存在
    3. 关键事件注册存在
    4. 主脚本非空且大小合理
    """
    src = GUI_FILE.read_text(encoding="utf-8")
    main = extract_main_js()
    assert bracket_balance(main) == 0, "主脚本括号不平衡"
    assert len(main) > 50000, f"主脚本异常短: {len(main)} chars"
    for fn in CRITICAL_FUNCS:
        assert re.search(r"(?:async\s+)?function\s+" + fn + r"\s*\(", main), \
            f"关键函数缺失: {fn}"
    for evt in CRITICAL_EVENTS:
        assert f"on('{evt}'" in main, f"关键事件缺失: {evt}"


@pytest.fixture
def gui_src() -> str:
    """fixture：主脚本源码（结构检查/静态断言用）。"""
    return extract_main_js()


@pytest.fixture
def gui_file() -> Path:
    return GUI_FILE
