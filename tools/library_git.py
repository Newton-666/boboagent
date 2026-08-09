"""
tools/library_git.py — library/ 独立仓库自动提交钩子（票 G1）

library/.git 是独立 git 仓库（主库版本化保底，禁远端，血案后遗症根治）。
本模块只在 living_notes 成功写笔记后触发 add/commit；无变更时跳过。

安全红线（TICKET-G1 §三，违反即事故）：
  - 只允许 add/commit；禁止 push / reset / checkout / clean / rm 等任何其他写操作；
  - git 缺席 / 仓库损坏 / 提交失败 → 静默降级记 notes.error，绝不阻塞笔记主流程；
  - 测试严禁在真实 library/ 里产生提交（钩子必须指向 tmp 库或 monkeypatch）。

用法：
  from tools.library_git import auto_commit
  auto_commit(action="write", topic="主题", sid="sid-1")
"""

import logging
import os
import subprocess
from pathlib import Path

logger = logging.getLogger("bobo.library_git")

# 主库目录（与 living_notes.py 同款定位；可注入供测试隔离）
_REPO_ROOT = Path(__file__).resolve().parent.parent
LIBRARY_DIR = _REPO_ROOT / "library"

# 只允许执行的 git 子命令（安全红线：白名单）
_ALLOWED_GIT = {"add", "commit"}


def _run_git(library_dir: Path, args: list[str]):
    """在 library_dir 内执行 git args（白名单校验）。返回 (returncode, stdout+stderr)。"""
    if not args or args[0] not in _ALLOWED_GIT:
        logger.warning("library_git blocked non-whitelisted git op: %s", args)
        return 2, "blocked"
    proc = subprocess.run(
        ["git", "-C", str(library_dir), *args],
        capture_output=True, text=True, timeout=30,
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def auto_commit(library_dir=None, action: str = "", topic: str = "",
                sid: str = "") -> dict:
    """若 library/.git 存在：add -A + commit（无变更跳过）。失败永不抛异常。

    参数：
      library_dir: 主库目录（默认 <项目根>/library；测试传 tmp 库）
      action:      动作标签（write / update / rebuild 等，进提交信息）
      topic:       主题名（进提交信息）
      sid:         会话 id（进提交信息）

    返回：
      {"committed": bool, "skipped": bool, "error": str|None}
      committed=True 产生新提交；skipped=True 表示无 .git 或无变更；error 非 None 表示失败已降级。
    """
    lib = Path(library_dir) if library_dir else LIBRARY_DIR
    try:
        git_dir = lib / ".git"
        if not git_dir.exists():
            return {"committed": False, "skipped": True, "error": None}

        # 只允许 add/commit（白名单在 _run_git 内强校验）
        rc, _ = _run_git(lib, ["add", "-A"])
        if rc != 0:
            raise RuntimeError(f"git add failed rc={rc}")
        msg = f"auto: {action} {topic} (sid={sid})".strip()
        rc, out = _run_git(lib, ["commit", "-m", msg])
        if rc != 0:
            # 无变更时 commit 返回非零（nothing to commit）→ 视为 skipped，非错误
            if "nothing to commit" in out.lower() or "no changes added" in out.lower():
                return {"committed": False, "skipped": True, "error": None}
            raise RuntimeError(f"git commit failed rc={rc}: {out[:200]}")
        return {"committed": True, "skipped": False, "error": None}
    except Exception as e:
        logger.warning("library git auto-commit failed (silent degrade): %s", e)
        return {"committed": False, "skipped": False, "error": str(e)}
