"""File safety — write-denied paths + binary file detection.

Phase 2 security catch-up: prevents LLM from accidentally writing to or
reading sensitive system files. Inspired by Hermes' agent/file_safety.py.

Issue #3: also enforces data/protected_paths.json (plus hardcoded kernel
defaults) so in-repo core/ / tools/ / gateway cannot be silently rewritten.
"""

import json
import os
import fnmatch
import struct
from pathlib import Path
from typing import Optional, Set

# ── Write-Denied Paths ──────────────────────────────────────────────────

_HOME = str(Path.home())

# Exact paths that should NEVER be written to
WRITE_DENIED_PATHS: Set[str] = {
    "/etc/passwd",
    "/private/etc/passwd",  # macOS symlink
    "/etc/shadow",
    "/etc/sudoers",
    "/etc/hosts",
    "/etc/hostname",
    "/etc/resolv.conf",
    "/etc/fstab",
    "/etc/crontab",
    "/etc/ssh/sshd_config",
    "/private/etc/ssh/sshd_config",  # macOS symlink
    f"{_HOME}/.ssh/id_rsa",
    f"{_HOME}/.ssh/id_ed25519",
    f"{_HOME}/.ssh/id_ecdsa",
    f"{_HOME}/.ssh/authorized_keys",
    f"{_HOME}/.ssh/config",
    f"{_HOME}/.aws/credentials",
    f"{_HOME}/.aws/config",
    f"{_HOME}/.gcloud/credentials.db",
    f"{_HOME}/.gitconfig",
    f"{_HOME}/.netrc",
    f"{_HOME}/.npmrc",
    f"{_HOME}/.env",
    f"{_HOME}/.bashrc",
    f"{_HOME}/.zshrc",
    f"{_HOME}/.profile",
    f"{_HOME}/.bash_profile",
    f"{_HOME}/.bobo/.env",
}

# Prefixes — any file under these directories is denied
WRITE_DENIED_PREFIXES: tuple = (
    "/etc/",
    "/private/etc/",  # macOS symlink
    "/boot/",
    "/sys/",
    "/proc/",
    "/dev/",
    f"{_HOME}/.ssh/",
    f"{_HOME}/.aws/",
    f"{_HOME}/.gcloud/",
    f"{_HOME}/.gnupg/",
    f"{_HOME}/.config/gcloud/",
    f"{_HOME}/Library/Keychains/",
    f"{_HOME}/.bobo/",  # prevent overwriting config
    "/System/",
    "/Library/System/",
)

# File patterns that look like credentials
CREDENTIAL_SNIFF_PATTERNS = (
    ".env",
    "credentials",
    "secret",
    "token",
    "private_key",
    "id_rsa",
    "id_ed25519",
    "id_ecdsa",
    ".pem",
    ".key",
    ".pfx",
    ".p12",
    "password",
)


# ── protected_paths（issue #3）────────────────────────────────────────
# 仓库根：core/ 的上级。路径常量以 config 为准；失败时本地兜底，不炸启动。
_BOBO_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
try:
    from config import PROTECTED_PATHS_FILE as _CFG_PROTECTED_FILE
    from config import DEFAULT_PROTECTED_GLOBS as _CFG_DEFAULT_GLOBS
    _PROTECTED_PATHS_FILE = str(_CFG_PROTECTED_FILE)
    _DEFAULT_PROTECTED_GLOBS: tuple[str, ...] = tuple(_CFG_DEFAULT_GLOBS)
except Exception:
    _PROTECTED_PATHS_FILE = os.path.join(_BOBO_REPO_ROOT, "data", "protected_paths.json")
    _DEFAULT_PROTECTED_GLOBS = (
        "core/**",
        "tools/**",
        "bobo_tui_gateway/**",
        "data/protected_paths.json",
    )

_FILE_READ_ACTIONS = frozenset({"read", "exists"})
_FILE_MUTATING_TOOLS = frozenset({"edit_file", "delete_file", "file_writer"})

_protected_load_fail_audited = False


def reset_protected_paths_cache() -> None:
    """测试钩子：重置缺失/损坏清单的一次性审计标记。"""
    global _protected_load_fail_audited
    _protected_load_fail_audited = False


def _audit_protected_load_failure(cfg_path: str, reason: str) -> None:
    """清单缺失/损坏写审计，不得抛出（不炸启动）。"""
    global _protected_load_fail_audited
    if _protected_load_fail_audited:
        return
    _protected_load_fail_audited = True
    try:
        from core.event_bus import event_bus
        event_bus.write("protected_paths.load", {
            "ok": False,
            "path": cfg_path,
            "reason": reason,
        })
    except Exception:
        pass


def load_protected_paths(path: str | None = None) -> list[str]:
    """读取受保护清单（glob 表达式，相对项目根）。

    - 默认读 data/protected_paths.json（相对仓库根，不依赖 CWD）；
    - 缺失 / JSON 损坏 / 字段非法 → 返回空清单 + 审计（不炸启动）；
    - 返回的 globs 已去空白、去空串。
    内核兜底 glob 不在本函数返回值里，由 effective_protected_globs / is_protected 合并。
    """
    cfg = path if path is not None else _PROTECTED_PATHS_FILE
    try:
        with open(cfg, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        globs = data.get("globs", [])
        if not isinstance(globs, list):
            _audit_protected_load_failure(str(cfg), "globs 字段非法（非 list）")
            return []
        return [g.strip() for g in globs if isinstance(g, str) and g.strip()]
    except FileNotFoundError:
        _audit_protected_load_failure(str(cfg), "文件缺失")
        return []
    except Exception as exc:
        _audit_protected_load_failure(str(cfg), f"{type(exc).__name__}: {exc}")
        return []


def effective_protected_globs(path: str | None = None) -> list[str]:
    """默认内核 glob ∪ 配置 glob（去重保序）。配置缺失时仍有内核兜底。"""
    seen: list[str] = []
    for glob in list(_DEFAULT_PROTECTED_GLOBS) + load_protected_paths(path):
        if glob not in seen:
            seen.append(glob)
    return seen


def _normalize_repo_rel(path: str) -> list[str]:
    """把输入路径收成若干相对仓库根的候选（POSIX 分隔符）。

    相对路径按原样匹配（测试传 core/engine.py 不依赖 CWD）；
    绝对路径 / resolve 后路径再转相对。仓外路径不进入候选。
    """
    candidates: list[str] = []
    raw = (path or "").strip().lstrip("./").replace("\\", "/")
    if raw and not raw.startswith("/"):
        candidates.append(raw)

    repo_root = os.path.abspath(_BOBO_REPO_ROOT)

    def _rel_if_inside(abs_path: str) -> None:
        try:
            rel = os.path.relpath(abs_path, repo_root).replace("\\", "/")
        except Exception:
            return
        if rel.startswith("..") or os.path.isabs(rel):
            return
        if rel not in candidates:
            candidates.append(rel)

    if raw.startswith("/"):
        _rel_if_inside(os.path.abspath(os.path.expanduser(raw)))
    try:
        resolved = str(Path(path).expanduser().resolve())
        _rel_if_inside(resolved)
    except Exception:
        pass
    return candidates


def _glob_hits(rel: str, glob: str) -> bool:
    """glob 命中或目录前缀命中（core/** 命中 core/engine.py）。"""
    g = glob.strip().rstrip("/").replace("\\", "/")
    if not g or not rel:
        return False
    if fnmatch.fnmatch(rel, g):
        return True
    prefix = g[:-3] if g.endswith("/**") else g
    prefix = prefix.rstrip("/")
    if not prefix:
        return False
    return rel == prefix or rel.startswith(prefix + "/")


def is_protected(path: str, globs: list[str] | None = None) -> bool:
    """路径是否命中受保护清单（glob / 目录前缀，相对项目根）。

    globs 为空时使用 effective_protected_globs()（配置 ∪ 内核兜底）。
    显式传入空列表 → False（调用方自管清单）。
    """
    if not path:
        return False
    if globs is None:
        globs = effective_protected_globs()
    if not globs:
        return False
    for rel in _normalize_repo_rel(path):
        for g in globs:
            if _glob_hits(rel, g):
                return True
    return False


def file_tool_mutation(tool_name: str, tool_args: dict | None) -> tuple[bool, list[str]]:
    """文件工具是否写/删，及其目标路径。

    Returns (is_mutating, paths)。
    file_operation 的 read/exists 为只读；write/delete/batch_write 为写；
    未知 action 按写处理（保守）。路径空串不收入列表。
    """
    args = tool_args or {}
    if tool_name == "file_operation":
        action = str(args.get("action") or "").strip().lower()
        if action == "batch_write":
            paths: list[str] = []
            for item in args.get("files") or []:
                if isinstance(item, dict):
                    p = str(item.get("path") or "").strip()
                    if p:
                        paths.append(p)
            return True, paths
        p = str(args.get("path") or args.get("file_path") or args.get("filepath") or "").strip()
        paths = [p] if p else []
        if action in _FILE_READ_ACTIONS:
            return False, paths
        return True, paths
    if tool_name in _FILE_MUTATING_TOOLS:
        p = str(
            args.get("file_path")
            or args.get("filepath")
            or args.get("path")
            or args.get("file")
            or args.get("filename")
            or ""
        ).strip()
        return True, [p] if p else []
    return False, []


def is_write_denied(filepath: str) -> tuple[bool, str]:
    """Check if a file path should be write-denied.

    Returns (denied: bool, reason: str).
    """
    path = str(Path(filepath).expanduser().resolve())
    path_lower = path.lower()

    # Exact match
    if path in WRITE_DENIED_PATHS:
        return True, f"禁止写入系统敏感文件: {path}"

    # Prefix match (directory-level block)
    for prefix in WRITE_DENIED_PREFIXES:
        if path.startswith(prefix):
            return True, f"禁止写入受保护目录: {prefix}"

    # Credential-like filename check (only if in home dir or root level)
    basename = os.path.basename(path).lower()
    for pattern in CREDENTIAL_SNIFF_PATTERNS:
        if pattern in basename:
            # Allow if it's clearly a project file (deep inside a workspace)
            parts = path.split(os.sep)
            if _HOME in path and len(parts) < 5:
                return True, f"疑似凭据文件，禁止写入: {basename}"

    # Issue #3：仓内内核路径（protected_paths ∪ 默认 core/tools/gateway）。
    # 本函数给文件工具用。execute_terminal 改内核仍走 #4 确认链，本票不拦 shell 绕写。
    if is_protected(filepath) or is_protected(path):
        return True, f"禁止写入受保护路径（protected_paths）: {path}"

    return False, ""


# ── Binary File Detection ───────────────────────────────────────────────

# Extensions known to be binary or non-human-readable
BINARY_EXTENSIONS: Set[str] = {
    ".pyc", ".pyo", ".so", ".dylib", ".dll", ".exe",
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar",
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp",
    ".mp3", ".mp4", ".wav", ".avi", ".mov", ".mkv", ".flac",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".ttf", ".otf", ".woff", ".woff2",
    ".class", ".jar", ".war",
    ".db", ".sqlite", ".sqlite3",
    ".pkl", ".pickle", ".joblib",
    ".bin", ".dat", ".o", ".a",
    ".wasm",
}

# Magic bytes for common binary formats
BINARY_MAGIC_BYTES = {
    b"\x89PNG": "PNG image",
    b"\xff\xd8\xff": "JPEG image",
    b"GIF8": "GIF image",
    b"PK\x03\x04": "ZIP archive",
    b"\x1f\x8b\x08": "gzip archive",
    b"BZh": "bzip2 archive",
    b"\x7fELF": "ELF binary",
    b"\xca\xfe\xba\xbe": "Mach-O binary",
    b"\xce\xfa\xed\xfe": "Mach-O binary (32-bit)",
    b"MZ": "Windows executable",
    b"SQLite format 3\x00": "SQLite database",
    b"%PDF": "PDF document",
    b"\xd0\xcf\x11\xe0": "MS Office (OLE)",
}

MAX_MAGIC_READ = 512  # read first 512 bytes for magic detection


def is_binary_file(filepath: str) -> tuple[bool, str]:
    """Check if a file appears to be binary.

    Returns (is_binary: bool, reason: str).
    Checks extension first (fast), then magic bytes (accurate).
    """
    path = Path(filepath)
    ext = path.suffix.lower()

    # Fast path: extension check
    if ext in BINARY_EXTENSIONS:
        return True, f"二进制文件类型: {ext}"

    # Check if file exists before trying to read
    if not path.exists() or not path.is_file():
        return False, ""

    # Magic byte check
    try:
        with open(path, "rb") as f:
            head = f.read(MAX_MAGIC_READ)
    except Exception:
        return False, ""

    for magic, label in BINARY_MAGIC_BYTES.items():
        if head.startswith(magic):
            return True, f"二进制文件 (magic: {label})"

    # Null byte check: if file contains null bytes in first 512 bytes,
    # it's almost certainly binary
    if b"\x00" in head:
        return True, "二进制文件 (包含 null 字节)"

    return False, ""


def safe_read_check(filepath: str) -> Optional[str]:
    """Check if a file is safe to read. Returns error message or None if safe.

    Reads files that trigger binary detection will return a warning;
    files in denied paths will return an error.
    """
    binary, msg = is_binary_file(filepath)
    if binary:
        return f"警告: {msg} — 如确需读取请使用 execute_terminal 'cat' 或 'xxd' 命令"

    # Also check: is it in a denied directory for reading?
    path = str(Path(filepath).expanduser().resolve())
    for denied_prefix in ("/etc/shadow", f"{_HOME}/.ssh/id_", f"{_HOME}/.aws/", f"{_HOME}/.gnupg/"):
        if path.startswith(denied_prefix):
            return f"安全警告: 读取敏感文件 {path} — 操作已记录但允许继续"

    return None


# ── Env Isolation ───────────────────────────────────────────────────────

# Env vars to strip from subprocess environments (prevent credential leaks)
SANITIZE_ENV_PREFIXES: tuple = (
    "API_KEY",
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "PASSWD",
    "CREDENTIAL",
    "AUTH",
    "AWS_",
    "GCLOUD_",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "GITHUB_TOKEN",
    "NOTION_API_KEY",
    "DEEPSEEK_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENROUTER_API_KEY",
)

# Allowlist: env vars that are safe to pass through
SANITIZE_ENV_ALLOWLIST: tuple = (
    "PATH", "HOME", "USER", "LOGNAME", "SHELL",
    "LANG", "LC_ALL", "LC_CTYPE",
    "TERM", "COLORTERM",
    "PWD", "OLDPWD",
    "VIRTUAL_ENV", "CONDA_PREFIX",
    "NODE_PATH", "PYTHONPATH",
    "DISPLAY", "WAYLAND_DISPLAY",
    "SSH_AUTH_SOCK", "SSH_AGENT_PID",
    "DBUS_SESSION_BUS_ADDRESS",
    "XDG_",  # all XDG_* vars
    "HERMES_", "BOBO_",  # app-specific
    "OBSIDIAN_VAULT",  # needed by tools
)


def sanitize_env(env: dict | None = None) -> dict:
    """Return a sanitized copy of the environment for subprocess execution.

    Strips credentials and sensitive tokens, keeps only safe vars.
    """
    if env is None:
        env = dict(os.environ)

    clean = {}
    for key, value in env.items():
        # Allowlist check
        allowed = False
        for prefix in SANITIZE_ENV_ALLOWLIST:
            if key == prefix or key.startswith(prefix):
                allowed = True
                break
        if allowed:
            clean[key] = value
            continue

        # Denylist check
        blocked = False
        for prefix in SANITIZE_ENV_PREFIXES:
            if key.upper().startswith(prefix) or prefix in key.upper():
                blocked = True
                break
        if not blocked:
            clean[key] = value

    return clean
