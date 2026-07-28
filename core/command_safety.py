"""command_safety.py — 命令安全分级（白名单 / 黑名单 / 灰名单）。

从 engine.py 提取，原为 Engine 类的类属性和方法。
"""

import re as _re
import shlex as _shlex
import os as _os
from typing import Tuple
from core.file_safety import is_write_denied

# Bobo 自身仓库根（core/ 的上级目录，即 ~/Desktop/BOBO_Project_Backup）
_BOBO_REPO_ROOT = _os.path.abspath(
    _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..")
)


# 白名单：日常安全命令，静默执行
SAFE_COMMANDS = {
    "git", "ls", "cat", "echo", "python", "python3", "node", "npm", "npx",
    "pip", "pip3", "cd", "pwd", "mkdir", "cp", "mv", "grep", "find", "head",
    "tail", "wc", "curl", "wget", "du", "df", "whoami", "date", "env",
    "which", "man", "diff", "sort", "uniq", "touch", "file", "stat",
    "less", "more", "clear", "history", "type", "uname", "hostname",
    "go", "cargo", "rustc", "make", "cmake", "docker", "ps", "top",
    "tree", "xargs", "awk", "sed", "tr",
    "open",   # macOS: open apps/files/URLs
    "kill", "killall", "pgrep", "pkill",
    "osascript",    # macOS AppleScript automation
    "say",          # macOS text-to-speech
    "pbcopy", "pbpaste",  # macOS clipboard
    "screencapture", "sips",  # macOS screenshot / image
    "mdfind", "mdls", "mdutil",  # macOS Spotlight
    "launchctl", "defaults",  # macOS launch services / prefs
    "sw_vers", "system_profiler", "sysctl", "nettop",  # macOS system info
    "plutil", "pmset", "tmutil",  # macOS plist / power / time machine
    "diskutil", "hdiutil",  # macOS disk (read-only safe)
    "security", "codesign",  # macOS keychain / signing
    "ditto", "rsync",  # macOS file copy
}

# 黑名单：永远阻止的高危模式
DANGEROUS_PATTERNS = [
    (r'rm\s+(-[rRf]|--recursive|--force)', "递归删除文件"),
    (r'sudo\s+', "提权操作"),
    (r'(chmod|chown)\s+.*777', "开放全部权限"),
    (r'>\s*/dev/(sd[a-z]+|disk\d+|nvme\d+n\d+|mmcblk\d+)', "直接写入磁盘设备"),
    (r'\bdd\s+if=', "磁盘镜像操作"),
    (r'mkfs\.', "格式化文件系统"),
    (r':\(\)\s*\{', "fork 炸弹"),
    (r'>\s*/etc/(passwd|shadow|sudoers|hosts)', "修改系统关键文件"),
    (r'(shutdown|reboot|halt|poweroff)', "系统关机/重启"),
    (r'curl.*\|\s*(ba)?sh', "管道执行远程脚本"),
    (r'wget.*\|\s*(ba)?sh', "管道执行远程脚本"),
    (r'git\s+push\s+.*--force', "强制推送"),
    (r'(scp|rsync|nc|netcat)\s+.*:', "远程文件传输/网络连接"),
    (r'\$\(', "命令替换注入 ($(...))"),
    (r'`[^`]+`', "反引号命令替换"),
    (r'curl.*\$\(', "curl + 命令替换"),
    (r'wget.*\$\(', "wget + 命令替换"),
]


def split_shell_segments(cmd_clean: str) -> list | None:
    """用 shlex 按控制操作符（| && || ;）把命令切成若干段。

    返回 token 段的列表；解析失败（如引号不配对）返回 None。
    之前只按 "|" 分段，`git status && evil`、`ls; evil` 会以白名单
    首命令命中而跳过整串检查（审计发现 #3）。
    """
    try:
        lexer = _shlex.shlex(cmd_clean, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        return None
    segments, current = [], []
    for tok in tokens:
        if tok and set(tok) <= set("|&;"):  # 操作符 token：| || && ; |& 等
            if current:
                segments.append(current)
                current = []
        else:
            current.append(tok)
    if current:
        segments.append(current)
    return segments


def check_redirect_targets(cmd_clean: str) -> tuple | None:
    """检查 > / >> 重定向目标是否写入受保护文件。

    此前分类器只看命令名不看重定向，`echo x >> ~/.zshrc` 会以 echo
    命中白名单静默执行（审计发现 #3）。命中 is_write_denied 即 dangerous。
    """
    # 匹配 > >> 2> 2>> &> &>> 的目标；(?!&) 跳过 >&1 之类的 fd 复制
    for m in _re.finditer(r'(?:\d+|&)?>>?\s*(?!&)(\S+)', cmd_clean):
        target = m.group(1).strip('"\'')
        if not target or target.startswith("-"):
            continue
        if target in ("/dev/null", "/dev/stdout", "/dev/stderr"):
            continue  # 常见且无害
        denied, reason = is_write_denied(target)
        if denied:
            return ("dangerous", f"重定向写入受保护文件 — {reason}: {target[:60]}")
    return None


def classify_command(command: str) -> tuple[str, str]:
    """分类命令：safe / dangerous / gray。返回 (等级, 原因)。

    检查优先级：
      1. 黑名单正则（全字符串匹配，拦截已知危险模式）
      2. 重定向目标检查（> / >> 写入受保护文件即 dangerous）
      3. 按控制操作符（| && || ;）分段，每段独立判定
      4. 白名单（段首命令命中即安全）；灰名单兜底（需用户确认）
    """
    if not command or not command.strip():
        return ("safe", "")

    cmd_clean = command.strip()

    # ── 第 1 步：全字符串黑名单 ──
    for pattern, reason in DANGEROUS_PATTERNS:
        if _re.search(pattern, cmd_clean):
            return ("dangerous", reason)

    # ── 第 2 步：重定向目标 ──
    redirect_result = check_redirect_targets(cmd_clean)
    if redirect_result:
        return redirect_result

    # ── 第 3 步：分段检查（管道 + && || ; 链）──
    # 必须在白名单检查之前执行，否则 "ls && unknown_cmd"
    # 会以 "ls" 命中白名单而跳过后半段的安全检查。
    segments = split_shell_segments(cmd_clean)
    if segments is None:
        return ("gray", "命令解析失败（引号可能不配对），需人工确认")
    if len(segments) > 1:
        for seg_tokens in segments:
            seg_text = " ".join(seg_tokens)
            seg_cmd = seg_tokens[0] if seg_tokens else ""
            if not seg_cmd:
                continue
            # 每段先过黑名单
            for pattern, reason in DANGEROUS_PATTERNS:
                if _re.search(pattern, seg_text):
                    return ("dangerous", f"链式命令中的危险操作 — {reason}: {seg_text[:60]}")
            # 再检查白名单
            if seg_cmd in SAFE_COMMANDS:
                continue
            # 不在白名单也不在黑名单 → 灰名单
            return ("gray", f"链式命令中包含未知命令: {seg_cmd}")
        # 所有段都通过 → 安全
        return ("safe", "")

    # ── 第 4 步：单命令白名单 ──
    base_cmd = segments[0][0] if segments and segments[0] else ""
    if base_cmd in SAFE_COMMANDS:
        return ("safe", "")

    # ── 第 5 步：灰名单兜底 ──
    return ("gray", f"未知安全等级的命令: {base_cmd}")


# ── self-hosting v2：自身仓库 git 操作物理闸 ──


def _is_on_main_branch(repo_dir: str) -> bool:
    """检查 git 仓库当前是否在 main 分支上。

    通过 git rev-parse 查询当前分支名。任何异常（超时/权限/非 git 目录）
    均返回 False——宁可漏拦一次 commit，也不误伤合法操作。
    """
    try:
        import subprocess as _sp
        r = _sp.run(
            ["git", "-C", repo_dir, "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=2,
        )
        return r.stdout.strip() == "main"
    except Exception:
        return False


def _find_git_subcommand(command: str) -> str | None:
    """从 git 命令字符串中提取子命令（跳过全局选项如 -C/-c/--git-dir 等）。

    git 全局选项（-C <path>, -c <key=val>, --git-dir=<path>,
    --work-tree=<path>, --no-pager 等）出现在子命令之前，
    必须跳过这些选项才能正确识别 commit vs merge vs status 等。
    """
    import shlex as _shlex_mod

    m = _re.search(r'\bgit\b\s+(.*)', command)
    if not m:
        return None
    rest = m.group(1).strip()
    try:
        tokens = _shlex_mod.split(rest)
    except ValueError:
        tokens = rest.split()
    if not tokens:
        return None

    # 带一个参数的全局选项
    _EAT_ONE = frozenset({'-C', '-c', '--git-dir', '--work-tree', '--exec-path'})
    # 无参数的全局选项
    _SKIP = frozenset({
        '-P', '--no-pager', '-p', '--paginate', '--bare',
        '--no-replace-objects', '--literal-pathspecs',
        '--glob-pathspecs', '--noglob-pathspecs', '--icase-pathspecs',
    })

    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok in _SKIP:
            i += 1
            continue
        if tok in _EAT_ONE:
            i += 2
            continue
        # --key=value 形式（如 --git-dir=/tmp）
        if any(tok.startswith(p + '=') for p in ('--git-dir', '--work-tree', '--exec-path')):
            i += 1
            continue
        # -c key=value 紧凑形式（无空格，如 -cuser.name=x，极少见但合法）
        if tok.startswith('-c') and len(tok) > 2 and tok[2] != ' ':
            i += 1
            continue
        return tok
    return None


def _is_self_repo_main_commit(command: str) -> bool:
    """判定命令是否为在 bobo 自身仓库 main 分支上执行 git commit。

    三条件缺一即放行：
    1. 命令的子命令必须是 commit（跳过 git 全局选项 -C/-c/--git-dir 等后判定）
    2. 目标目录必须是 bobo 自身仓库（_BOBO_REPO_ROOT）
    3. 当前分支必须是 main

    git merge 不经过 git commit 命令，天然不受影响。
    docs-only 提交不豁免——一律走 feat 分支。
    """
    cmd = command.strip()
    # 快速排除：不是 git 命令
    if not _re.search(r'\bgit\b', cmd):
        return False
    # 提取子命令（跳过全局选项如 -C/-c）
    subcommand = _find_git_subcommand(cmd)
    if subcommand != "commit":
        return False

    target_dir = _resolve_git_target_dir(cmd)
    if target_dir is None:
        target_dir = _os.getcwd()

    if not _is_bobo_repo_dir(target_dir):
        return False

    return _is_on_main_branch(target_dir)


def _is_self_repo_destructive_git(command: str) -> bool:
    """判定命令是否对 bobo 自身仓库执行 push/毁灭性 git 操作。

    只拦截三种操作：git push（任何形式）、git reset --hard、git clean -f[d]。
    其他 git 操作（status/log/merge/checkout）照常放行。

    判定方法：
    1. 从命令中解析目标目录（-C 参数 / cd 链 / 默认 cwd）
    2. 从目标目录向上找 .git 得到 git 仓库根
    3. 与 _BOBO_REPO_ROOT 比较

    解析不清的路径宁可放行：误伤日常 git 比漏拦更糟——
    漏拦还有 prompt 层和 reflog，误伤会让 bobo 在别的项目残废。
    """
    cmd = command.strip()
    # 快速排除：不是 git 命令、或不含目标子命令
    if not _re.search(r'\bgit\b', cmd):
        return False
    if not _re.search(r'\b(push|reset\s+--hard|clean\s+-f(?:d)?)\b', cmd):
        return False

    target_dir = _resolve_git_target_dir(cmd)
    if target_dir is None:
        target_dir = _os.getcwd()
    return _is_bobo_repo_dir(target_dir)


def _resolve_git_target_dir(command: str) -> str | None:
    """从 git 命令中提取目标目录。

    处理的形态（优先级）：
    - git -C <path> ...
    - cd <path> && ... git ...
    - 无（返回 None，调用方用 cwd）

    解析失败时返回 None（宁可放行）。
    """
    # 形态 a：git -C <path> ...
    m = _re.search(r'git\s+-C\s+(\S+)', command)
    if m:
        try:
            return _os.path.expanduser(m.group(1))
        except Exception:
            return None

    # 形态 b：cd <path> && ... git ...
    m = _re.search(r'cd\s+(\S+)\s*&&\s*.*git\s+', command)
    if m:
        try:
            return _os.path.expanduser(m.group(1))
        except Exception:
            return None

    # 形态 c：cd <path> ; ... git ...（分号链）
    m = _re.search(r'cd\s+(\S+)\s*;\s*.*git\s+', command)
    if m:
        try:
            return _os.path.expanduser(m.group(1))
        except Exception:
            return None

    return None


def _is_bobo_repo_dir(path: str) -> bool:
    """判定给定路径是否位于 bobo 自身仓库内。

    方法：从 path 向上遍历，找到 .git/ 目录后与 _BOBO_REPO_ROOT 比较。
    文件系统和路径解析异常均返回 False（宁可漏拦，不可误伤）。
    """
    try:
        p = _os.path.abspath(_os.path.expanduser(path))
    except Exception:
        return False
    _repo_root_abs = _os.path.abspath(_BOBO_REPO_ROOT)
    # 向上遍历找 .git
    while p and p != _os.path.dirname(p):
        if _os.path.isdir(_os.path.join(p, ".git")):
            return _os.path.abspath(p) == _repo_root_abs
        # 子目录也可判定：不等到 .git，直接比较前缀（仓库内任何子目录）
        if p == _repo_root_abs or _repo_root_abs.startswith(p + _os.sep):
            # p 是 repo_root 的祖先或等于，继续向上找 .git
            pass
        p = _os.path.dirname(p)
    return False


def is_self_repo_hard_block(tool_name: str, tool_args: dict) -> Tuple[bool, str]:
    """v2/v3 self-repo 闸命中 → 硬拒绝，不进确认流程。

    复用 _is_self_repo_destructive_git 与 _is_self_repo_main_commit，
    判定逻辑与 is_high_risk_tool 中的 v2/v3 检查完全一致，不加不减。
    """
    if tool_name != "execute_terminal":
        return False, ""
    command = tool_args.get("command", "")
    if _is_self_repo_destructive_git(command):
        return True, "此操作仅限用户在终端亲自执行，请通知用户手动操作后重试"
    if _is_self_repo_main_commit(command):
        return True, "此操作仅限用户在终端亲自执行，请通知用户手动操作后重试"
    return False, ""


def is_high_risk_tool(tool_name: str, tool_args: dict) -> Tuple[bool, str]:
    if tool_name == "execute_terminal":
        command = tool_args.get("command", "")

        # ── self-hosting v2 物理闸：自身仓库的 push/毁灭性 git 操作 ──
        if _is_self_repo_destructive_git(command):
            return True, f"🚫 bobo 自身仓库：push/毁灭性操作仅限用户（self-hosting v2）: {command[:60]}"

        # ── self-hosting v3 物理闸：自身仓库 main 分支 git commit ──
        if _is_self_repo_main_commit(command):
            return True, f"🚫 bobo 自身仓库：禁止在 main 直接提交，请切 feat 分支: {command[:60]}"

        level, reason = classify_command(command)
        if level == "dangerous":
            return True, f"🚫 危险操作 — {reason}: {command[:60]}"
        if level == "gray":
            return True, f"执行终端命令: {command[:60]}"
        # safe — 静默执行，不需要确认
        return False, ""

    if tool_name in ["delete_note", "move_note", "rename_note", "delete_folder"]:
        return True, f"文件操作: {tool_name}"

    # shell.exec RPC 方法始终需要确认（来自 TUI 直接输入）
    if tool_name == "shell.exec":
        command = tool_args.get("command", "")
        level, reason = classify_command(command)
        if level == "dangerous":
            return True, f"🚫 危险操作 — {reason}: {command[:60]}"
        return True, f"执行终端命令: {command[:60]}"

    return False, ""
