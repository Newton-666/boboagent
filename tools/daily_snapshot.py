#!/usr/bin/env python3
"""每日快照：library 记忆库 git 提交 + knowledge_base.json 快照分支推送。

设计：
- library/ 有自己的独立 git，直接 add -A + commit（本地版本历史）。
- data/knowledge_base.json 被 gitignore，通过临时 worktree 提交到
  backup/data-snapshot 分支并推送 origin——不碰用户工作区与 HEAD。
- 幂等：无变化则跳过 commit；任何一步失败打日志继续，退出码反映失败。
"""
import subprocess, sys, tempfile, shutil, os
from datetime import datetime
from pathlib import Path

ROOT = Path("/Users/niuqingwei/Desktop/boboagent_main")
LIB = ROOT / "library"
KB = ROOT / "data" / "knowledge_base.json"
BACKUP_BRANCH = "backup/data-snapshot"
TS = datetime.now().strftime("%Y-%m-%d %H:%M")

def run(cmd, cwd, check=True):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"{cmd} -> {r.returncode}: {r.stderr[:300]}")
    return r

def snapshot_library():
    if not (LIB / ".git").exists():
        return "library 无 .git，跳过"
    run(["git", "add", "-A"], LIB)
    dirty = run(["git", "status", "--porcelain"], LIB).stdout.strip()
    if not dirty:
        return "library 无变化"
    run(["git", "commit", "-m", f"snapshot: {TS}"], LIB)
    return f"library 已提交（{len(dirty.splitlines())} 项变更）"

def snapshot_knowledge_base():
    if not KB.exists():
        return "knowledge_base.json 不存在，跳过"
    wt = Path(tempfile.mkdtemp(prefix="bobo-kb-snap-"))
    try:
        # 确保备份分支存在（基于当前 main，避免孤儿历史）
        if run(["git", "rev-parse", "--verify", BACKUP_BRANCH], ROOT, check=False).returncode != 0:
            run(["git", "branch", BACKUP_BRANCH, "main"], ROOT)
        run(["git", "worktree", "add", str(wt), BACKUP_BRANCH], ROOT)
        dst = wt / "data" / "knowledge_base.json"
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(KB, dst)
        run(["git", "add", "-f", "data/knowledge_base.json"], wt)
        if not run(["git", "status", "--porcelain"], wt).stdout.strip():
            return "knowledge_base 无变化"
        run(["git", "commit", "-m", f"snapshot: knowledge_base {TS}"], wt)
        run(["git", "push", "origin", BACKUP_BRANCH], wt)
        return "knowledge_base 已快照并推送"
    finally:
        run(["git", "worktree", "remove", "--force", str(wt)], ROOT, check=False)
        shutil.rmtree(wt, ignore_errors=True)

if __name__ == "__main__":
    results, failed = [], False
    for name, fn in (("library", snapshot_library), ("knowledge_base", snapshot_knowledge_base)):
        try:
            results.append(f"[{name}] {fn()}")
        except Exception as e:
            results.append(f"[{name}] 失败: {e}")
            failed = True
    print("\n".join(results))
    import json as _json
    print(_json.dumps({"artifact": {
        "ts": TS,
        "results": results,
        "ok": not failed,
    }}, ensure_ascii=False))
    sys.exit(1 if failed else 0)
