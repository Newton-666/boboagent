"""File safety — write-denied paths + binary file detection.

Phase 2 security catch-up: prevents LLM from accidentally writing to or
reading sensitive system files. Inspired by Hermes' agent/file_safety.py.
"""

import os
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
