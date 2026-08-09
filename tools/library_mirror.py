"""
tools/library_mirror.py — 主库 library/ → Obsidian vault library/ 单向镜像（票 R2 / R2b）

真源：<项目根>/library/（boboagent_main 项目主库，唯一正统，owner 裁决 2026-08-09）
镜像：OBSIDIAN_VAULT/library/（Obsidian 展示层，只读勿手改）

三道铁闸（TICKET-R2b 血案修正，2026-08-09 终审，不许翻案）：
  闸 1 — vault 解析禁区：vault 解析后命中 cwd / 项目根 / 主库本体或其祖先 / 与主库重叠
        任一条件 → skipped=True + 发 library.mirror_blocked 事件（含原因），零写入零删除。
  闸 2 — 批量删除熔断：待删清单 > 5 或 > 镜像侧现有文件数 30% → 放弃整个删除阶段
        （写入阶段照常），发 library.mirror_blocked（reason=mass_delete_fuse，
        pending_removed 全清单）。显式人工 override：allow_mass_delete=True，
        仅手动入口 `python -m tools.library_mirror --allow-mass-delete` 可传；
        living_notes 挂钩永远不许传。
  闸 3 — 测试隔离铁律：测试必须显式传 vault_dir=<tmp>；不传的必须 delenv + 断言 skipped。

血案教训（罪证链见 TICKET-R2b §一）：删除传播是核弹级能力，必须有剂量限制。

用法：
  python -m tools.library_mirror [--allow-mass-delete]   # 手动全量灌库
  from tools.library_mirror import sync_library_to_obsidian
"""

import logging
import os
from pathlib import Path

logger = logging.getLogger("bobo.library_mirror")

# 项目主库（真源）：与 living_notes.py 同款定位
_REPO_ROOT = Path(__file__).resolve().parent.parent
LIBRARY_DIR = _REPO_ROOT / "library"

# 镜像侧目录名（相对 OBSIDIAN_VAULT）
_MIRROR_REL = "library"

# 镜像头注释（index.md 除外）
_MIRROR_HEADER = "<!-- MIRROR: 真源=boboagent_main/library/，请勿手改 -->\n"

# macOS 系统文件，两侧都不管（Obsidian 打开 vault 会自行生成，避免删除抖动）
_SKIP_NAMES = {".DS_Store"}

# 闸 2 熔断参数：待删 > 5 或 > 镜像侧 30%
_MASS_DELETE_ABS = 5
_MASS_DELETE_RATIO = 0.3


def _emit(event_type: str, data: dict):
    """事件埋点。写失败静默，绝不影响主流程（同 living_notes._emit）。"""
    try:
        from core.event_bus import event_bus as _ebus
        _ebus.write(event_type, data)
    except Exception:
        pass


def _is_within(child: Path, parent: Path) -> bool:
    """realpath 校验 child 是否落在 parent 内（含 parent 本身）。

    符号链接会先被 resolve 解析：链接指向 vault 外 → 返回 False（拒绝）。
    """
    try:
        child_r = child.resolve()
        parent_r = parent.resolve()
    except Exception:
        return False
    return child_r == parent_r or str(child_r).startswith(str(parent_r) + os.sep)


def _mirror_header_for(rel: Path) -> str:
    """index.md 不加镜像头（已有 AUTO-GENERATED 头）；其余文件加。"""
    if rel.name == "index.md":
        return ""
    return _MIRROR_HEADER


def _expected_content(rel: Path, raw: bytes) -> bytes:
    """镜像侧期望内容 = 镜像头 + 主库原内容（幂等：已带头则不再叠加）。"""
    header = _mirror_header_for(rel).encode("utf-8")
    if header and raw.startswith(header):
        return raw
    return header + raw


def _walk_files(root: Path):
    """遍历目录下所有非系统文件，返回 [Path, ...]。"""
    result = []
    for r, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in _SKIP_NAMES]
        for fname in files:
            if fname in _SKIP_NAMES:
                continue
            result.append(Path(r) / fname)
    return result


# ── 闸 1：vault 解析禁区 ──────────────────────────────

def _blocked_reason(vault: Path, dst_root: Path, src: Path) -> str | None:
    """闸 1 校验：vault / dst_root 是否命中禁区。命中返回原因字符串，否则 None。

    禁区（任一命中即跳过，零写入零删除）：
      - vault == cwd（血案根因：Path("")→Path(".") 后 vault 落为 cwd）
      - vault == 项目根 _REPO_ROOT
      - vault == 主库 LIBRARY_DIR 本身，或与主库互为祖先/后代（重叠）
      - dst_root（vault/library）与主库重叠
    """
    try:
        vault_r = vault.resolve()
        cwd_r = Path.cwd().resolve()
        root_r = _REPO_ROOT.resolve()
        src_r = src.resolve()
        dst_r = dst_root.resolve()
    except Exception:
        return "resolve_failed"

    if vault_r == cwd_r:
        return "vault_is_cwd"
    if vault_r == root_r:
        return "vault_is_repo_root"
    if vault_r == src_r:
        return "vault_is_library_dir"
    if _is_within(src_r, vault_r):
        return "library_inside_vault"      # 主库是 vault 的子目录（vault 是主库祖先）
    if _is_within(vault_r, src_r):
        return "vault_inside_library"      # vault 是主库的子目录
    if _is_within(dst_r, src_r) or _is_within(src_r, dst_r):
        return "dst_overlaps_library"      # 镜像目标与主库重叠
    return None


def sync_library_to_obsidian(library_dir=None, vault_dir=None, sid="",
                             allow_mass_delete: bool = False) -> dict:
    """全量镜像：主库 library/ → OBSIDIAN_VAULT/library/。

    参数可注入（测试用双临时目录）：
      library_dir: 主库目录（默认 <项目根>/library）
      vault_dir:   Obsidian vault 根（默认 OBSIDIAN_VAULT 环境变量）
      allow_mass_delete: 闸 2 显式人工 override，仅手动入口可传 True；
        living_notes 挂钩永远不许传（默认 False）。

    返回：
      {"ok": bool, "synced": [rel...], "removed": [rel...],
       "skipped": bool, "blocked": str|None}
      skipped=True 表示 vault 未配置/不存在（零动作，发 library.mirror_blocked 事件）。
      blocked 非 None 表示闸 1 / 闸 2 拦截原因（闸 1 零写入零删除；闸 2 熔断时写入照常）。
    """
    src = Path(library_dir) if library_dir else LIBRARY_DIR
    vault_raw = str(vault_dir) if vault_dir else os.environ.get("OBSIDIAN_VAULT", "")
    if not vault_raw.strip():
        # 闸 1a：空值/纯空白 → 跳过（堵死 Path("")→Path(".") 血案陷阱）
        _emit("library.mirror_blocked", {"reason": "empty_vault", "sid": sid})
        return {"ok": False, "synced": [], "removed": [],
                "skipped": True, "blocked": "empty_vault"}
    vault = Path(vault_raw)
    if not vault.exists():
        _emit("library.mirror_blocked", {"reason": "vault_missing", "sid": sid})
        return {"ok": False, "synced": [], "removed": [],
                "skipped": True, "blocked": "vault_missing"}

    dst_root = vault / _MIRROR_REL
    dst_root.mkdir(parents=True, exist_ok=True)
    dst_root_real = dst_root.resolve()

    # 闸 1b：vault 解析禁区（cwd / 项目根 / 主库 / 重叠）
    reason = _blocked_reason(vault, dst_root, src)
    if reason:
        _emit("library.mirror_blocked", {"reason": reason, "sid": sid})
        return {"ok": False, "synced": [], "removed": [],
                "skipped": True, "blocked": reason}

    synced: list[str] = []
    removed: list[str] = []

    # ── 1. 写入/更新：主库 → 镜像 ──
    for src_file in _walk_files(src):
        rel = src_file.relative_to(src)
        dst_file = dst_root / rel
        if not _is_within(dst_file, dst_root_real):
            logger.warning("mirror target escapes vault library, skipped: %s", dst_file)
            continue
        try:
            raw = src_file.read_bytes()
        except OSError as e:
            logger.warning("mirror read failed: %s (%s)", src_file, e)
            continue
        expected = _expected_content(rel, raw)
        try:
            if dst_file.exists() and dst_file.read_bytes() == expected:
                continue  # 幂等：内容一致不重写、不刷新 mtime
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            dst_file.write_bytes(expected)
            synced.append(str(rel))
        except OSError as e:
            logger.warning("mirror write failed: %s (%s)", dst_file, e)

    # ── 2. 删除：先统计待删清单，闸 2 熔断检查通过才执行 ──
    src_rels = {str(f.relative_to(src)) for f in _walk_files(src)}
    pending_removed: list[str] = []
    for root, dirs, files in os.walk(dst_root, topdown=False):
        dirs[:] = [d for d in dirs if d not in _SKIP_NAMES]
        for fname in files:
            if fname in _SKIP_NAMES:
                continue
            dst_file = Path(root) / fname
            if not _is_within(dst_file, dst_root_real):
                continue  # 符号链接指向 vault 外：保守保留，不删
            rel = str(dst_file.relative_to(dst_root))
            if rel not in src_rels:
                pending_removed.append(rel)

    fuse_triggered = False
    if pending_removed and not allow_mass_delete:
        mirror_count = len(_walk_files(dst_root))
        if (len(pending_removed) > _MASS_DELETE_ABS or
                len(pending_removed) > _MASS_DELETE_RATIO * mirror_count):
            fuse_triggered = True
            _emit("library.mirror_blocked", {
                "reason": "mass_delete_fuse",
                "pending_removed": pending_removed,
                "mirror_count": mirror_count,
                "sid": sid,
            })
            logger.warning(
                "mirror mass-delete fuse triggered: %d pending > abs %d or ratio %.0f%% "
                "of %d mirror files; deletion phase aborted (writes still applied)",
                len(pending_removed), _MASS_DELETE_ABS,
                _MASS_DELETE_RATIO * 100, mirror_count)

    if not fuse_triggered:
        for rel in pending_removed:
            dst_file = dst_root / rel
            try:
                dst_file.unlink()
                removed.append(rel)
            except OSError as e:
                logger.warning("mirror remove failed: %s (%s)", dst_file, e)
        # 清理空目录（仅限 dst_root 内，保留根目录本身）
        for root, dirs, files in os.walk(dst_root, topdown=False):
            dirs[:] = [d for d in dirs if d not in _SKIP_NAMES]
            try:
                if Path(root) != dst_root and not os.listdir(root):
                    os.rmdir(root)
            except OSError:
                pass

    _emit("library.mirror_sync", {
        "files_synced": len(synced),
        "files_removed": len(removed),
        "sid": sid,
    })
    return {"ok": True, "synced": synced, "removed": removed,
            "skipped": False,
            "blocked": "mass_delete_fuse" if fuse_triggered else None}


if __name__ == "__main__":
    # 手动全量入口：python -m tools.library_mirror [--allow-mass-delete]
    import sys
    allow = "--allow-mass-delete" in sys.argv
    result = sync_library_to_obsidian(allow_mass_delete=allow)
    print(f"skipped={result['skipped']} blocked={result['blocked']} "
          f"synced={len(result['synced'])} removed={len(result['removed'])}")
    for r in result["synced"]:
        print("  +", r)
    for r in result["removed"]:
        print("  -", r)
