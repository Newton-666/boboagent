"""Load full content of a previously marked result from workspace.

Part of the Context Engineering — Result Marking System.
Tool results (read_local_file, web_search, grep_code, etc.) are stored
externally as [RESULT] markers. When the LLM needs the full content,
it calls load_result(id) to retrieve what was saved.
"""

import json
from config import BOBO_DATA_DIR
import os
import re

TOOL_NAME = "load_result"

# TICKET-OBS-1: 防御兜底 — 取回内容仍是标记时自动跟进解析的深度上限。
# load_result 的返回（[FULL RESULT] 前缀）永远不应被再次外部化标记；
# 若异常路径已造成嵌套，这里限深自动跟进，超限报错而非继续套娃。
MAX_FOLLOW_DEPTH = 3
_MARKER_ID_RE = re.compile(r"→ id: ([0-9a-z_]+), \d+ chars")


def _workspace_dir() -> str:
    """工作区路径：调用时从 BOBO_DATA_DIR 动态解析（TICKET-D2）。

    废除 import 时快照 WORKSPACE_DIR——快照在测试 patch 目录后裂脑。
    """
    return str(BOBO_DATA_DIR / "workspace")


def _stats_path() -> str:
    """统计文件路径：随 _workspace_dir() 动态派生（原 _STATS_PATH 二次快照）。"""
    return os.path.join(_workspace_dir(), "_stats.json")

def _update_stats(key: str, delta: int = 1):
    """Atomically increment a counter in workspace/_stats.json."""
    os.makedirs(_workspace_dir(), exist_ok=True)
    import threading, tempfile
    _stats_lock = threading.Lock()
    with _stats_lock:
        stats = {}
        if os.path.exists(_stats_path()):
            try:
                with open(_stats_path(), 'r', encoding='utf-8') as f:
                    stats = json.load(f)
            except Exception:
                stats = {}
        stats[key] = stats.get(key, 0) + delta
        fd, tmp = tempfile.mkstemp(dir=_workspace_dir(), suffix='.json', prefix='.st_')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(stats, f, ensure_ascii=False, indent=2)
            import shutil
            shutil.move(tmp, _stats_path())
        except Exception:
            try: os.unlink(tmp)
            except Exception: pass


def get_marking_stats() -> dict:
    """Return current marking statistics: marked, loaded, load_miss, total_chars_saved."""
    if not os.path.exists(_stats_path()):
        return {"marked": 0, "loaded": 0, "load_miss": 0, "total_chars_saved": 0}
    try:
        with open(_stats_path(), 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {"marked": 0, "loaded": 0, "load_miss": 0, "total_chars_saved": 0}



def execute(id: str, max_chars: int = 5000) -> str:
    """Load the full content of a previously marked tool result by its ID.

    Args:
        id: The result ID from a [RESULT] marker (e.g. "3_a1b2c3d4")
        max_chars: Maximum characters to return. Default 5000.
                   Exceeding content is truncated with a note.

    TICKET-OBS-1: load_result 的返回（[FULL RESULT] 前缀）永远不被再次标记；
    防御兜底：若取回的内容本身仍是标记（[RESULT] 或嵌套的 [FULL RESULT]），
    自动跟进解析，限深 MAX_FOLLOW_DEPTH 层，超限返回 [ERROR] 而非继续套娃。
    """
    return _execute_follow(id, max_chars, depth=0, visited=frozenset())


def _execute_follow(id: str, max_chars: int, depth: int, visited: frozenset) -> str:
    """取回结果；若内容仍是标记则自动跟进（限深 MAX_FOLLOW_DEPTH）。"""
    if depth > MAX_FOLLOW_DEPTH:
        _update_stats("load_miss")
        return (
            f"[ERROR] load_result 嵌套超过 {MAX_FOLLOW_DEPTH} 层"
            f"（'{id}'），拒绝继续跟进以避免套娃。\n"
            f"请直接重新调用原工具获取最新结果。"
        )
    if id in visited:
        _update_stats("load_miss")
        return (
            f"[ERROR] load_result 检测到循环引用"
            f"（'{id}' 已在跟进链中），拒绝继续跟进。\n"
            f"请直接重新调用原工具获取最新结果。"
        )
    visited = visited | {id}

    path = os.path.join(_workspace_dir(), f"{id}.json")
    if not os.path.exists(path):
        return (
            f"[NOT FOUND] Result '{id}' no longer available "
            f"(may have been cleaned up or the ID is stale).\n"
            f"如果需要，请重新调用原工具获取最新结果。"
        )
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        _update_stats("load_miss")
        return f"[ERROR] Failed to read result '{id}': {e}"

    content = data.get("content", "")
    tool = data.get("tool", "?")
    args = data.get("args", "{}")

    # TICKET-OBS-1 防御兜底：剥掉嵌套的 [FULL RESULT] 包装（每层 +1 深度）
    while content.startswith("[FULL RESULT]") and depth <= MAX_FOLLOW_DEPTH:
        content = content.split("\n\n", 1)[1] if "\n\n" in content else ""
        depth += 1
    if depth > MAX_FOLLOW_DEPTH:
        _update_stats("load_miss")
        return (
            f"[ERROR] load_result 嵌套超过 {MAX_FOLLOW_DEPTH} 层"
            f"（'{id}'），拒绝继续跟进以避免套娃。\n"
            f"请直接重新调用原工具获取最新结果。"
        )
    # 取回内容本身是 [RESULT] 标记 → 提取 id 自动跟进
    if content.startswith("[RESULT]"):
        m = _MARKER_ID_RE.search(content)
        if m:
            nested_id = m.group(1)
            return _execute_follow(nested_id, max_chars, depth, visited)

    total_chars = len(content)
    if total_chars > max_chars:
        content = (
            content[:max_chars]
            + f"\n...(截断，共 {total_chars} 字符，仅显示前 {max_chars})"
        )

    _update_stats("loaded")
    return f"[FULL RESULT] {tool}({args})\n\n{content}"


TOOL_FUNC = execute
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": (
            "Load the full content of a previously [RESULT]-marked tool result by its ID. "
            "Use this when you need more detail from a search result, file read, or web fetch "
            "than the summary in the marker provides. "
            "If you need most of a file to answer, call this directly without hesitation. "
            "If you only need a specific detail, check the marker summary first."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "id": {
                    "type": "string",
                    "description": "The result ID from a [RESULT] marker (e.g. '3_a1b2c3d4')",
                },
                "max_chars": {
                    "type": "integer",
                    "description": (
                        "Maximum characters to return. Default 5000. "
                        "Use a smaller value if you only need part of the result."
                    ),
                },
            },
            "required": ["id"],
        },
    },
}


def register(reg):
    reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA)
