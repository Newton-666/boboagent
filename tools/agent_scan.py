#!/usr/bin/env python3
"""agent_scan — 侦查脚本（Kimi 评审补丁 1：pid 主判据）。

原理：
    tmux 全局守护进程可见所有 pane。每个 pane 的 pane_pid 是 shell；
    真正跑 agent 的进程在它的进程树里。进程命令行是物理事实：
      bobo → 树中出现 `python -m bobo_tui_gateway.entry`
      pi   → 树中出现二进制名 `pi`
    标题（pane_title）只做兜底/补充展示，不做主判据。

用法：
    python3 tools/agent_scan.py [--json]
"""
import json
import os
import subprocess
import sys

# ---- 特征判定（集中管理，易调整）----
BOBO_CMD_MARK = "bobo_tui_gateway.entry"   # bobo 进程命令行特征
PI_CMD_MARK = "pi"                         # pi 二进制名（作为整段命令行最后 token 判断）
PI_TITLE_MARK = "π"                        # 标题兜底：pi 标题含 π
BOBO_TITLE_MARK = "✓ 会话"                 # 标题兜底：bobo 标题含 ✓ 会话


def run(cmd, timeout=15):
    """跑命令，返回 stdout 文本。"""
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return r.stdout or ""


def pane_pid(pane: str) -> str:
    """取 pane 的 pane_pid（tmux 给的主键）。"""
    return run(["tmux", "display", "-t", pane, "-p", "#{pane_pid}"]).strip()


def process_tree(pid: str) -> list:
    """递归收集 pid 的子孙进程命令行（含自身）。"""
    out = []
    stack = [pid]
    while stack:
        cur = stack.pop()
        r = run(["ps", "-o", "pid=,command=", "-p", cur])
        for line in r.splitlines():
            parts = line.strip().split(" ", 1)
            if len(parts) == 2:
                out.append((parts[0], parts[1]))
                # 找子进程
                kids = run(["pgrep", "-P", parts[0]]).strip().split()
                stack.extend(kids)
    return out


def classify_by_cmd(tree: list) -> tuple:
    """进程树命令行主判据：返回 (kind, match_pid, match_cmd)。"""
    for pid, c in tree:
        if BOBO_CMD_MARK in c:
            return "bobo", pid, c
    for pid, c in tree:
        tokens = c.strip().split()
        if tokens and tokens[-1] == PI_CMD_MARK:
            return "pi", pid, c
    return "unknown", "", ""


def proc_detail(pid: str) -> dict:
    """区分信息：启动时间(lstart) + 工作目录(cwd)。Kimi 补丁 5 要求。"""
    info = {"lstart": "", "cwd": ""}
    if not pid:
        return info
    r = run(["ps", "-o", "lstart=", "-p", pid])
    if r.strip():
        info["lstart"] = r.strip()
    # macOS 用 lsof 取 cwd；Linux 用 /proc
    r = run(["lsof", "-a", "-p", pid, "-d", "cwd", "-Fn"])
    for line in r.splitlines():
        if line.startswith("n/"):
            info["cwd"] = line[1:]
            break
    return info


def classify_by_title(title: str) -> str:
    """标题兜底判据（仅当命令行为 unknown 时用）。"""
    if PI_TITLE_MARK in title:
        return "pi"
    if BOBO_TITLE_MARK in title:
        return "bobo"
    return "unknown"


def scan() -> list:
    """扫描全部 tmux pane，返回 [{pane, pid, cmd, title, kind, kind_src}]。"""
    raw = run(["tmux", "list-panes", "-a",
               "-F", "#{session_name}:#{window_index}.#{pane_index}|#{pane_pid}|#{pane_current_command}|#{pane_title}"])
    results = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        pane, pid, cur_cmd, title = line.split("|", 3)
        tree = process_tree(pid)
        kind, match_pid, match_cmd = classify_by_cmd(tree)
        src = "cmd"
        if kind == "unknown":
            tkind = classify_by_title(title)
            if tkind != "unknown":
                kind, src = tkind, "title"
                match_pid, match_cmd = pid, cur_cmd
        detail = proc_detail(match_pid) if kind != "unknown" else {}
        results.append({
            "pane": pane, "pid": pid, "cmd": cur_cmd, "title": title,
            "kind": kind, "kind_src": src,
            "match_pid": match_pid, "match_cmd": match_cmd[:120],
            "lstart": detail.get("lstart", ""), "cwd": detail.get("cwd", ""),
        })
    return results


def main():
    as_json = "--json" in sys.argv
    results = scan()
    if as_json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return
    for r in results:
        mark = {"bobo": "🧠", "pi": "🤖", "unknown": "❓"}.get(r["kind"], "?")
        print(f"{mark} {r['pane']:<24} kind={r['kind']:<8} src={r['kind_src']:<5} title={r['title'][:40]}")
        print(f"    pid={r['pid']} cmd={r['cmd'][:60]}")
        if r["kind"] != "unknown":
            print(f"    match_pid={r['match_pid']} lstart={r['lstart']}")
            print(f"    cwd={r['cwd']}")
    bobo = [r for r in results if r["kind"] == "bobo"]
    pi = [r for r in results if r["kind"] == "pi"]
    unk = [r for r in results if r["kind"] == "unknown"]
    print(f"\n统计: bobo×{len(bobo)}  pi×{len(pi)}  未知×{len(unk)}  (共 {len(results)} pane)")


if __name__ == "__main__":
    main()
