"""Load full content of a previously marked result from workspace.

Part of the Context Engineering — Result Marking System.
Tool results (read_local_file, web_search, grep_code, etc.) are stored
externally as [RESULT] markers. When the LLM needs the full content,
it calls load_result(id) to retrieve what was saved.
"""

import json
import os

TOOL_NAME = "load_result"
WORKSPACE_DIR = os.path.expanduser("~/.bobo/workspace")

_STATS_PATH = os.path.join(WORKSPACE_DIR, "_stats.json")

def _update_stats(key: str, delta: int = 1):
    """Atomically increment a counter in workspace/_stats.json."""
    os.makedirs(WORKSPACE_DIR, exist_ok=True)
    import threading, tempfile
    _stats_lock = threading.Lock()
    with _stats_lock:
        stats = {}
        if os.path.exists(_STATS_PATH):
            try:
                with open(_STATS_PATH, 'r', encoding='utf-8') as f:
                    stats = json.load(f)
            except Exception:
                stats = {}
        stats[key] = stats.get(key, 0) + delta
        fd, tmp = tempfile.mkstemp(dir=WORKSPACE_DIR, suffix='.json', prefix='.st_')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(stats, f, ensure_ascii=False, indent=2)
            import shutil
            shutil.move(tmp, _STATS_PATH)
        except Exception:
            try: os.unlink(tmp)
            except Exception: pass


def get_marking_stats() -> dict:
    """Return current marking statistics: marked, loaded, load_miss, total_chars_saved."""
    if not os.path.exists(_STATS_PATH):
        return {"marked": 0, "loaded": 0, "load_miss": 0, "total_chars_saved": 0}
    try:
        with open(_STATS_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {"marked": 0, "loaded": 0, "load_miss": 0, "total_chars_saved": 0}



def execute(id: str, max_chars: int = 5000) -> str:
    """Load the full content of a previously marked tool result by its ID.

    Args:
        id: The result ID from a [RESULT] marker (e.g. "3_a1b2c3d4")
        max_chars: Maximum characters to return. Default 5000.
                   Exceeding content is truncated with a note.
    """
    path = os.path.join(WORKSPACE_DIR, f"{id}.json")
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
