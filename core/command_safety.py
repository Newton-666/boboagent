"""command_safety.py — 命令安全分级（白名单 / 黑名单 / 灰名单）。

从 engine.py 提取，原为 Engine 类的类属性和方法。
"""

import re as _re
import shlex as _shlex
from typing import Tuple
from core.file_safety import is_write_denied


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


def is_high_risk_tool(tool_name: str, tool_args: dict) -> Tuple[bool, str]:
    if tool_name == "execute_terminal":
        command = tool_args.get("command", "")
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
