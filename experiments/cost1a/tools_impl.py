#!/usr/bin/env python3
"""8 个核心工具的最小本地实现 + action 分发（TICKET-COST-1A-SANDBOX）。

沙盒内真实可跑：read/edit/grep/ls 操作沙盒工作目录；terminal 限白名单子进程；
memory 写沙盒 memory.jsonl；load_result 读沙盒结果缓存；web_search 为 stub。
家族合并工具（B 档）经 dispatch() 按 action 分发到这 8 个实现或占位实现。
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path

# 沙盒工作目录（runner 每次任务创建独立 sandbox，注入到 _WORKDIR）
_WORKDIR: Path = Path(".")
_MEMORY_FILE: Path = Path("memory.jsonl")
_RESULT_CACHE: dict[str, str] = {}
_TERMINAL_WHITELIST = ("echo", "cat", "ls", "grep", "python3", "python", "pwd", "wc", "head", "tail", "sed", "md5", "diff")


def set_sandbox(workdir: Path):
    """设置沙盒工作目录（runner 每任务调用一次）。"""
    global _WORKDIR, _MEMORY_FILE
    _WORKDIR = workdir
    _MEMORY_FILE = workdir / "memory.jsonl"


def _resolve(p: str) -> Path:
    """路径解析：相对路径基于沙盒工作目录，禁止越界。"""
    path = Path(p)
    if not path.is_absolute():
        path = _WORKDIR / path
    path = path.resolve()
    # 越界防护：只能访问工作目录内
    root = _WORKDIR.resolve()
    if not str(path).startswith(str(root)):
        raise PermissionError(f"越界路径（沙盒限制）: {p}")
    return path


# ── 8 个核心工具实现 ────────────────────────────────────────────

def impl_read_local_file(path: str, **kw) -> str:
    p = _resolve(path)
    if not p.exists():
        return f"错误: 文件不存在 {path}"
    return p.read_text(encoding="utf-8", errors="replace")[:20000]


def impl_edit_file(path: str, old_string: str, new_string: str = "", **kw) -> str:
    p = _resolve(path)
    if not p.exists():
        return f"错误: 文件不存在 {path}"
    text = p.read_text(encoding="utf-8", errors="replace")
    if text.count(old_string) != 1:
        return f"错误: old_string 出现 {text.count(old_string)} 次（需恰好 1 次）"
    p.write_text(text.replace(old_string, new_string), encoding="utf-8")
    return f"已替换: {path}"


def impl_execute_terminal(command: str, **kw) -> str:
    cmd = (command or "").strip()
    if not cmd:
        return "错误: 空命令"
    prog = cmd.split()[0]
    if prog not in _TERMINAL_WHITELIST:
        return f"错误: 命令 {prog} 不在沙盒白名单 {_TERMINAL_WHITELIST}"
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                           timeout=15, cwd=str(_WORKDIR))
        out = (r.stdout or "") + (r.stderr or "")
        return out[:8000] if out else f"（退出码 {r.returncode}，无输出）"
    except subprocess.TimeoutExpired:
        return "错误: 命令超时（15s）"


def impl_grep_code(pattern: str, path: str = ".", **kw) -> str:
    p = _resolve(path)
    if p.is_file():
        return impl_execute_terminal(f"grep -n '{pattern}' {path}")
    return impl_execute_terminal(f"grep -rn '{pattern}' {path}")


def impl_list_directory(path: str = ".", **kw) -> str:
    p = _resolve(path)
    if not p.exists():
        return f"错误: 目录不存在 {path}"
    try:
        items = sorted(os.listdir(p))
    except NotADirectoryError:
        return f"错误: 不是目录 {path}"
    return "\n".join(items) if items else "（空目录）"


def impl_load_result(result_id: str, **kw) -> str:
    if result_id in _RESULT_CACHE:
        return _RESULT_CACHE[result_id]
    return f"错误: 结果 {result_id} 不在沙盒缓存"


def impl_save_memory(content: str, **kw) -> str:
    entry = {"ts": time.time(), "content": str(content)}
    with open(_MEMORY_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return f"已保存到沙盒记忆（共 {sum(1 for _ in open(_MEMORY_FILE, encoding='utf-8'))} 条）"


def impl_search_memory(query: str = "", **kw) -> str:
    """沙盒记忆搜索（B/C 档核心工具集无 search_memory，A/D 档有；实现给 A/D 用）。"""
    if not _MEMORY_FILE.exists():
        return "（沙盒记忆为空）"
    lines = [json.loads(l) for l in _MEMORY_FILE.read_text(encoding="utf-8").splitlines() if l.strip()]
    if not query:
        return "\n".join(l["content"] for l in lines) or "（空）"
    return "\n".join(l["content"] for l in lines if query in l["content"]) or f"（无匹配: {query}）"


def impl_web_search(query: str, **kw) -> str:
    """web_search stub：沙盒无网络搜索 key，返回占位（任务不含 web 题）。"""
    return f"[沙盒 stub] 搜索结果占位 for: {query}"


def impl_web_fetch(url: str, **kw) -> str:
    return f"[沙盒 stub] 网页抓取占位 for: {url}"


# ── 家族工具实现（B 档合并工具的分发目标）────────────────────────

# 文件操作类家族动作 → 映射到本地文件实现
_OBSIDIAN_FILE_ACTIONS = {
    "read_obsidian": lambda a: impl_read_local_file(a.get("path", "")),
    "write_obsidian": None,  # 特殊处理（写文件）
    "append_obsidian": None,
    "search_obsidian": lambda a: impl_grep_code(a.get("query", ""), a.get("path", ".")),
    "list_folder": lambda a: impl_list_directory(a.get("path", ".")),
    "move_note": None,
    "rename_note": None,
    "delete_note": None,
    "create_folder": None,
}


# 占位家族实现（外部服务无沙盒后端）：明确告知沙盒不支持，引导用本地工具
def _stub_result(action: str) -> str:
    return (f"[沙盒 stub] {action} 在沙盒内不可用（无外部服务）。"
            f"请改用本地工具：read_local_file/edit_file/execute_terminal/"
            f"grep_code/list_directory/save_memory。")


_FAMILY_IMPLS = {
    "obsidian_tool": {
        "write_obsidian": lambda a: _write_obsidian(a),
        "append_obsidian": lambda a: _append_obsidian(a),
        "move_note": _stub_result, "rename_note": _stub_result,
        "delete_note": _stub_result, "create_folder": _stub_result,
        "delete_folder": _stub_result, "copy_to_obsidian": _stub_result,
        "code_to_obsidian": _stub_result, "review_to_obsidian": _stub_result,
        "batch_copy_notes": _stub_result, "batch_move_notes": _stub_result,
        "batch_delete_notes": _stub_result,
        # 其余（read/search/list_folder）走 _OBSIDIAN_FILE_ACTIONS 通用文件实现
    },
}


def _write_obsidian(a: dict) -> str:
    """write_obsidian 最小实现：写/覆盖沙盒笔记文件（扩展名 .md 兜底）。"""
    path = a.get("path") or a.get("filepath") or a.get("note") or ""
    content = a.get("content") or a.get("text") or ""
    if not path:
        return "错误: 缺少 path"
    p = _resolve(path if path.endswith(".md") else path + ".md")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(str(content), encoding="utf-8")
    return f"已写入笔记: {p}"


def _append_obsidian(a: dict) -> str:
    path = a.get("path") or a.get("filepath") or a.get("note") or ""
    content = a.get("content") or a.get("text") or ""
    if not path:
        return "错误: 缺少 path"
    p = _resolve(path if path.endswith(".md") else path + ".md")
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(str(content) + "\n")
    return f"已追加笔记: {p}"


# ── 统一分发入口 ────────────────────────────────────────────────
# 返回 (text_result, action_used) ；action_used 用于 B 档 action 选错率统计

def dispatch(tool_name: str, arguments: dict) -> tuple[str, str | None]:
    """按工具名分发到实现。返回 (结果文本, 实际 action)。"""
    args = arguments or {}

    # 家族合并工具：读 action 参数分发
    if tool_name in _FAMILY_IMPLS:
        action = args.get("action", "")
        impls = _FAMILY_IMPLS[tool_name]
        fn = impls.get(action)
        if fn is None and action in _OBSIDIAN_FILE_ACTIONS:
            fn = _OBSIDIAN_FILE_ACTIONS[action]
        if fn is None:
            fn = _stub_result
        return fn(args), action

    # 核心工具直分（**args 展开命名参数；参数名对齐真实 schema 别名）
    _IMPL = {
        "read_local_file": impl_read_local_file,
        "edit_file": impl_edit_file,
        "execute_terminal": impl_execute_terminal,
        "grep_code": impl_grep_code,
        "list_directory": impl_list_directory,
        "load_result": impl_load_result,
        "save_memory": impl_save_memory,
        "web_search": impl_web_search,
        "web_fetch": impl_web_fetch,
        "search_memory": impl_search_memory,
    }
    _ALIASES = {
        "read_local_file": {"filepath": "path"},
        "edit_file": {"file_path": "path"},
        "load_result": {"id": "result_id"},
    }
    fn = _IMPL.get(tool_name)
    if fn is None:
        return _stub_result(tool_name), None
    norm = {_ALIASES.get(tool_name, {}).get(k, k): v for k, v in args.items()}
    try:
        return fn(**norm), None
    except Exception as e:
        return f"错误: 工具 {tool_name} 执行失败: {type(e).__name__}: {e}", None
