"""command_safety.py — 命令安全分级（白名单 / 黑名单 / 灰名单）。

从 engine.py 提取，原为 Engine 类的类属性和方法。
"""

import re as _re
import shlex as _shlex
import os as _os
import json as _json
import fnmatch as _fnmatch
from typing import Tuple
from core.file_safety import is_write_denied

# Bobo 自身仓库根（core/ 的上级目录，即 ~/Desktop/boboagent_main）
_BOBO_REPO_ROOT = _os.path.abspath(
    _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..")
)


# 白名单：日常安全命令，静默执行
SAFE_COMMANDS = {
    "ls", "cat", "echo", "python", "python3", "node", "npm", "npx",
    "pip", "pip3", "cd", "pwd", "mkdir", "cp", "mv", "grep", "find", "head",
    "tail", "wc", "curl", "wget", "du", "df", "whoami", "date", "env",
    "which", "man", "diff", "sort", "uniq", "touch", "file", "stat",
    "less", "more", "clear", "history", "type", "uname", "hostname",
    "go", "cargo", "rustc", "make", "cmake", "docker", "ps", "top",
    "tree", "xargs", "awk", "sed", "tr",
    "open",   # macOS: open apps/files/URLs
    # 票 SAFETY-1（2026-08-16 两次事故）：kill/killall/pkill 移出白名单——
    # pkill -f 误杀自身后端（SIGTERM 优雅退出 code 0 → 桌面端不重启 → 永久断连）、
    # SIGKILL 误杀桌面端渲染进程（白屏）。杀灭命令全部走强制审批/黑名单，
    # 不再静默执行。pgrep（只查询不杀灭）保留白名单。
    "pgrep",
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
    # owner 2026-08-14 拍板（Kimi 实操事故实证）：reset --hard 会无声清掉工作区
    # 所有未提交改动（共享工作区场景曾误清 bobo 在施文件），AUTO 模式硬拦。
    (r'git\s+reset\s+.*--hard', "git reset --hard（清空工作区未提交改动）"),
    (r'(scp|rsync|nc|netcat)\s+.*:', "远程文件传输/网络连接"),
    (r'\$\(', "命令替换注入 ($(...))"),
    (r'`[^`]+`', "反引号命令替换"),
    (r'curl.*\$\(', "curl + 命令替换"),
    (r'wget.*\$\(', "wget + 命令替换"),
    # ── 票 SAFETY-1（2026-08-16 两次事故根治疗，与 reset --hard 同级黑名单）──
    # 18:53 pkill -f 误杀 bobo 自身后端（SIGTERM 优雅退出 code 0 → Electron 只对
    # 非 0 退出码重启 → owner 桌面端永久断连）；20:41 清理环境时 SIGKILL 误杀
    # owner 正在用的桌面端渲染进程（日志实证 [renderer-gone] reason=killed
    # exitCode=9）→ 白屏。模式匹配杀灭一律硬拦，只允许对具体数字 PID 的
    # kill <pid> / kill -9 <pid>（且强制审批，见 classify_kill_command）。
    (r'\bpkill\b', "进程模式匹配杀灭（pkill）"),
    (r'\bkillall\b', "按进程名批量杀灭（killall）"),
    # 按名 kill（kill python / kill -9 python）不在黑名单正则硬拦——信号解析
    # 歧义（kill -s TERM 12345 中 -s 与目标都是 \w）会误伤合法数字 PID 命令。
    # 由 classify_kill_command 统一判定（非数字目标 → dangerous，语义更准）。
]


# ── 票 AUTO-G2：误伤收紧 —— 引号/heredoc 字面文本不参与危险判定 ──

_HEREDOC_RE = _re.compile(r"<<-?\s*(?:['\"](?P<quoted>\w+)['\"]|(?P<bare>\w+))")


def _split_heredoc_blocks(command: str) -> list:
    """扫描命令，切出 heredoc 块区间。

    返回 [(block_text, is_literal, keep)]：
      block_text —— 整个 heredoc 块原文（含首行与闭合定界符行）
      is_literal —— 定界符带引号（<<'EOF' 等，内容纯字面不展开）
      keep       —— 是否保留参与判定（裸定界符且内容含 $/反引号 → 真执行，保留）
    行内引号/反引号不在此处理（行级正则负责）。
    """
    _lines = command.split("\n")
    _blocks: list = []
    _i = 0
    while _i < len(_lines):
        _ln = _lines[_i]
        _m = _HEREDOC_RE.search(_ln)
        if not _m:
            _i += 1
            continue
        _delim = _m.group("quoted") or _m.group("bare")
        _is_literal = _m.group("quoted") is not None
        # 收集块内容（首行定界符之后的行 + 到闭合定界符为止）
        _j = _i + 1
        _body_lines = []
        while _j < len(_lines) and _lines[_j].strip() != _delim:
            _body_lines.append(_lines[_j])
            _j += 1
        _end = _j  # 闭合定界符行（可能越界 = 未闭合）
        _body = "\n".join(_body_lines)
        _head_tail = _ln[_ln.find("<<"):]  # 首行定界符段（含行内跟随文本）
        _keep = False
        if not _is_literal and ("$" in _head_tail or "$" in _body
                                or "`" in _head_tail or "`" in _body):
            _keep = True  # 裸定界符内容会被 shell 展开 → 保守保留参与判定
        # block_text 只含 `<<` 之后的定界符段 + body + 闭合行：
        # 首行 `<<` 之前的命令部分（如 cat > /tmp/x.py）保留参与判定——
        # 真实重定向目标（含受保护文件）不得被连带剥离（票 AUTO-G2 收紧）。
        _block_span = _head_tail
        if _body:
            _block_span += "\n" + _body
        if _end < len(_lines):
            _block_span += "\n" + _lines[_end]
        _blocks.append((_block_span, _is_literal, _keep))
        _i = _end + 1
    return _blocks


def strip_literal_text(command: str) -> str:
    """剥离不参与执行的引号体/heredoc 字面文本，产出黑名单判定的可执行骨架。

    票 AUTO-G2 误伤源：cat > /tmp/x.py <<'EOF' 体内的 "git push --force"
    字样是写入文件的文本、不执行，却被全串黑名单 _re.search 命中判"强制推送"。

    安全语义不动（含命令替换的引号体/裸 heredoc 绝不剥离，仍参与判定）：
      1. 单引号体 '...' —— 纯字面，剥离
      2. 双引号体 "..." —— 内容含 $( 或反引号（shell 展开执行）→ 保留原样；
         否则剥离
      3. 反引号 `...` —— 真实命令替换，从不剥离
      4. heredoc <<'EOF'（引号定界符）→ 块内容纯字面，剥离
         heredoc <<EOF（裸定界符）→ 内容会展开：含 $ 或反引号 → 整块保留；
         纯文本 → 剥离
    """
    # 1) heredoc 块（多行结构，先行级处理）
    _blocks = _split_heredoc_blocks(command)
    _out = command
    for _block_text, _is_literal, _keep in _blocks:
        if _keep:
            continue  # 保留参与判定
        _out = _out.replace(_block_text, "", 1)
    # 2) 行内引号体
    _out = _re.sub(r"'[^']*'", "", _out)          # 单引号体剥离
    def _dq(_m):
        _inner = _m.group(0)[1:-1]
        if "$(" in _inner or "`" in _inner:
            return _m.group(0)  # 含命令替换 → 保留（真执行）
        return ""
    _out = _re.sub(r'"[^"]*"', _dq, _out)          # 双引号体：无命令替换才剥离
    return _out


def is_blacklisted(command: str) -> tuple[bool, str]:
    """黑名单硬锁判定：复用 DANGEROUS_PATTERNS，split 前整条原始串检查。

    返回 (hit: bool, reason: str)。命中 → (True, "递归删除文件" 等黑名单原因)。
    必须在 split 前查原始串——shlex punctuation_chars 会把 `$(` 拆成
    `$` + `(`（中间带空格），段级 `\$\(` 失配（46cd0e3 教训）。
    票 AUTO-G2：先剥离引号/heredoc 字面文本再匹配（误伤收紧——
    cat > /tmp/x.py <<'EOF' 体内的 "git push --force" 字样不参与判定）。
    """
    _skeleton = strip_literal_text(command)
    for pattern, reason in DANGEROUS_PATTERNS:
        if _re.search(pattern, _skeleton):
            return True, reason
    return False, ""


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


# ── 票 SAFETY-1：进程杀灭分级（kill/pkill/killall）────────────────────
# 2026-08-16 两次事故：pkill -f 误杀自身后端（断连）、SIGKILL 误杀桌面端渲染
# 进程（白屏）。设计：模式匹配杀灭与 bobo 相关目标 = 黑名单硬拦（dangerous）；
# 对具体数字 PID 的 kill <pid> / kill -9 <pid> = 强制人工确认（confirm）——
# 普通模式弹审批（提示进程身份），AUTO 模式不自动执行（拒绝+待人工清单）。

_KILL_RE = _re.compile(r'\b(?:kill|pkill|killall)\b')

# bobo 自身/桌面端进程标识（杀灭目标含任一 → 硬拦）。注意：检查对象是
# kill 的目标参数，不是整条命令——`kill 12345 && echo bobo done` 的目标是
# 数字 PID，不应被 `echo bobo` 误伤（需求"命令文本含 bobo 一律拦"落点收敛
# 到杀灭目标，更精确且不误伤）。
_BOBO_PROCESS_MARKERS = (
    "bobo_tui_gateway", "boboagent_main", "electron", "bobo", "desktop",
)


def _kill_targets(command: str) -> list:
    """提取杀灭命令的目标参数（去信号前缀、去链式后续命令）。

    - kill -9 12345       → ['12345']
    - kill -TERM 12345    → ['12345']
    - kill -s TERM 12345  → ['12345']
    - kill --signal=KILL 12345 → ['12345']
    - kill python         → ['python']
    - pkill -f python     → ['python']（-f 是选项，目标仍在）
    只取链首目标（kill 的目标在第一个 && || ; | 之前）。
    """
    m = _KILL_RE.search(command)
    if not m:
        return []
    rest = command[m.end():].strip()
    # 去掉信号/选项前缀（kill -9 / -TERM / -s TERM / --signal=TERM / -f 等）
    rest = _re.sub(
        r'^(?:(?:-\d+|-s\s+\w+|--signal(?:=|\s+)\w+|-\w+)\s+)+', '', rest)
    # 截断到链式操作符之前（目标只在链首）
    rest = _re.split(r'\s*(?:&&|\|\||;|\|)\s*', rest)[0]
    return rest.split()


def classify_kill_command(command: str) -> tuple:
    """票 SAFETY-1：进程杀灭命令分级。

    返回 (level, reason)：
    - dangerous：模式匹配杀灭（pkill/killall/按进程名 kill）、或杀灭目标含
      bobo 自身/桌面端进程标识 → 硬拦（与 reset --hard 同级，任何模式拒绝）
    - confirm：对具体数字 PID 的 kill <pid> / kill -9 <pid> → 强制人工确认
      （普通模式弹审批含进程身份；AUTO 模式转 external-irreversible 拒绝）
    - safe：不含杀灭语义（pgrep 查询等）→ 交给常规分类

    先剥离引号/heredoc 字面文本（票 AUTO-G2 惯例：字样≠执行），再剥离
    shell 注释（`kill 12345 # bobo` 的注释是说明文字，不是杀灭目标）。
    """
    _skeleton = strip_literal_text(command)
    # 剥离 shell 注释（# 前有空白或行首才剥；`echo a#b` 的 # 是字面量不剥）
    _skeleton = _re.sub(r'(^|\s)#.*$', r'\1', _skeleton, flags=_re.M)
    if not _KILL_RE.search(_skeleton):
        return ("safe", "")

    # 1) 模式匹配杀灭：pkill / killall（DANGEROUS_PATTERNS 已硬拦，此处兜底
    #    供 is_high_risk_tool / side_effect 分级直接复用）
    if _re.search(r'\bpkill\b', _skeleton):
        return ("dangerous", "pkill 模式匹配杀灭——可能误杀 bobo 自身或用户正在使用的进程（今晚已发生两次事故）")
    if _re.search(r'\bkillall\b', _skeleton):
        return ("dangerous", "killall 按进程名批量杀灭——可能误杀 bobo 自身或用户正在使用的进程（今晚已发生两次事故）")

    targets = _kill_targets(_skeleton)
    if not targets:
        return ("safe", "")  # kill 无目标参数（罕见），交给常规分类

    # 2) 杀灭目标含 bobo 自身/桌面端标识 → 硬拦
    _low = " ".join(targets).lower()
    for marker in _BOBO_PROCESS_MARKERS:
        if marker in _low:
            return ("dangerous", f"杀灭目标含 bobo 自身/桌面端进程标识（{marker}）——禁止自杀/误杀用户进程")
    _root_name = _os.path.basename(_BOBO_REPO_ROOT.rstrip(_os.sep)).lower()
    if _root_name and _root_name in _low:
        return ("dangerous", f"杀灭目标含本项目路径标识（{_root_name}）——禁止自杀/误杀用户进程")

    # 3) 数字 PID → 强制确认；非数字目标 → 按名杀灭硬拦
    if all(t.isdigit() for t in targets):
        return ("confirm", f"将杀进程 PID: {', '.join(targets)}")
    return ("dangerous", f"按进程名 kill（目标非数字 PID: {targets[0]}）——须指定具体数字 PID 并说明理由")


def _ps_lookup_pid(command: str) -> str:
    """审批提示用：从 kill 命令提取数字 PID，ps 现场查进程身份（尽力而为）。

    只读命令 ps -p <pid>，失败返回提示（审批弹窗仍会展示，用户可自行确认）。
    """
    m = _re.search(r'\bkill\b\s+(?:(?:-\w+|-\d+|-s\s+\w+|--signal(?:=|\s+)\w+)\s+)*(\d+)', command)
    if not m:
        return ""
    pid = m.group(1)
    try:
        import subprocess as _sp
        r = _sp.run(["ps", "-p", pid, "-o", "pid=,comm="],
                    capture_output=True, text=True, timeout=3)
        out = r.stdout.strip()
        if out:
            return f"目标进程: {out}"
        return f"PID {pid} 当前不存在（可能已退出）"
    except Exception:
        return f"PID {pid}（ps 查询失败，请先 ps 确认身份）"


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
    # 票 AUTO-G2：误伤收紧——先剥离引号/heredoc 字面文本（骨架匹配），
    # cat > /tmp/x.py <<'EOF' 体内的 "git push --force" 字样不参与判定
    _skeleton = strip_literal_text(cmd_clean)
    for pattern, reason in DANGEROUS_PATTERNS:
        if _re.search(pattern, _skeleton):
            return ("dangerous", reason)

    # ── 票 SAFETY-1：进程杀灭分级（pkill/killall/按名 kill 已入黑名单被
    #  上一步拦截；这里处理 bobo 标识目标与数字 PID 放行审批）──
    _kill_level, _kill_reason = classify_kill_command(cmd_clean)
    if _kill_level == "dangerous":
        return ("dangerous", _kill_reason)
    if _kill_level == "confirm":
        return ("gray", f"进程杀灭需人工确认 — {_kill_reason}")

    # ── 第 2 步：重定向目标 ──
    # 票 AUTO-G2 误伤收紧：重定向检查同样用骨架（剥离引号/heredoc 字面文本），
    # heredoc 体内的 "> /etc/passwd" 字样是文件内容、不参与判定。
    redirect_result = check_redirect_targets(strip_literal_text(cmd_clean))
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
            # 每段先过黑名单（票 AUTO-G2：同样先剥离字面文本再匹配）
            for pattern, reason in DANGEROUS_PATTERNS:
                if _re.search(pattern, strip_literal_text(seg_text)):
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


def _has_real_git_command(command: str) -> bool:
    """判断命令中是否含有真实的 git 子命令（而非字符串内容中的 "git"）。

    先按 shell 控制操作符（&& ; |）分段，检查每段是否以 git 为首个命令。
    避免 `echo "git commit -m fix"` 或 `git log --grep="git commit"` 误触。
    """
    segments = split_shell_segments(command)
    if segments is None:
        # 解析失败（引号不配对等），回退到原始字符串判定
        return bool(_re.search(r'\bgit\b', command))
    for tokens in segments:
        if tokens and tokens[0] == "git":
            return True
    return False


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
    # 快速排除：不是真实的 git 命令（避免 echo/grep 字符串内容误触）
    if not _has_real_git_command(cmd):
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


# ── self-hosting v3.5：feat 分支非破坏性 git 命令豁免 ──

_NON_DESTRUCTIVE_GIT_SUBCOMMANDS = frozenset({
    "status", "log", "diff", "show", "blame", "ls-files", "ls-tree",
    "add", "commit", "branch", "checkout", "stash", "config", "remote", "fetch",
})

# 即使子命令在白名单，命令行里出现这些模式仍视为有破坏性
_GIT_DESTRUCTIVE_OPTION_PATTERNS = [
    (r'\bpush\b', "push"),
    (r'\breset\b', "reset"),
    (r'\bclean\b', "clean"),
    (r'\brebase\b', "rebase"),
    (r'\bmerge\b', "merge"),
    (r'\bcherry-pick\b', "cherry-pick"),
    (r'\brevert\b', "revert"),
    (r'\bcheckout\s+-f', "checkout -f"),
    (r'\bcheckout\s+.*--\s*\.', "checkout -- ."),
]


def _is_self_repo_non_destructive_git_on_non_main(command: str) -> bool:
    """判定是否为在 bobo 自身仓库执行的非破坏性 git 命令（v3.5 豁免）。

    放行范围严格限定为：status / log / diff / add / commit / branch /
    checkout -b / stash / config / remote / fetch 等非破坏性操作。
    push/reset/clean/rebase/merge 等破坏性命令一概不放行。

    分支策略（v3.5.1 修正）：豁免不限于 feat 分支——main 上的
    status/log/diff 等只读命令同样放行；main 上的 git commit 由调用链上游的
    v3 硬闸（_is_self_repo_main_commit）先行拦截，本函数无需重复检查分支。
    （原实现要求非 main 分支，导致测试随 cwd 分支状态翻转——合体 bug。）
    """
    if not _has_real_git_command(command):
        return False

    subcommand = _find_git_subcommand(command)
    if subcommand not in _NON_DESTRUCTIVE_GIT_SUBCOMMANDS:
        return False

    for pattern, _name in _GIT_DESTRUCTIVE_OPTION_PATTERNS:
        if _re.search(pattern, command):
            return False

    # checkout 只允许 checkout -b（创建新分支），其他 checkout 放行风险大
    if subcommand == "checkout":
        m = _re.search(r'\bcheckout\s+(-b\s+\S+|\s*)', command)
        if not m or not m.group(1).strip().startswith("-b"):
            return False

    target_dir = _resolve_git_target_dir(command)
    if target_dir is None:
        target_dir = _os.getcwd()
    if not _is_bobo_repo_dir(target_dir):
        return False

    # 分支不检查：main 上只读命令同样放行；main commit 由上游 v3 硬闸拦截
    return True


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
    # 快速排除：不是真实的 git 命令（避免 echo/grep 字符串内容误触）
    if not _has_real_git_command(cmd):
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

        # ── self-hosting v3.5：feat 分支非破坏性 git 命令免确认放行 ──
        if _is_self_repo_non_destructive_git_on_non_main(command):
            return False, ""

        # ── 票 SAFETY-1：进程杀灭强制审批 ──
        # pkill/killall/按名 kill 已被 classify_command 黑名单拦截（dangerous）；
        # 这里处理对具体数字 PID 的 kill <pid>——普通模式必须弹审批，审批提示
        # 现场 ps 查询进程身份（AUTO 模式由 classify_side_effect 转拒绝，不在此路径）。
        _kill_level, _kill_reason = classify_kill_command(command)
        if _kill_level == "dangerous":
            return True, f"🚫 {_kill_reason}: {command[:60]}"
        if _kill_level == "confirm":
            _pid_info = _ps_lookup_pid(command)
            return True, (
                f"⚠ 此命令可能误杀 bobo 自身或用户正在使用的进程（今晚已发生两次事故），"
                f"如确需清理孤儿进程请指定具体 PID 并说明理由。{_kill_reason}"
                + (f"；{_pid_info}" if _pid_info else "")
            )

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


# ── 票 A：AUTO MODE auto 决策树 v1 —— 纯读 git 命令判定 ──

# TICKET-AUTO-G1（2026-08-13）：只读 git 子命令全集扩充。
# 原集合仅 status/log/diff/show/blame/ls-files/ls-tree，导致 rev-parse/describe/
# show-ref 等纯读命令落入"外部不可逆（无法确认可回滚）"被 AUTO 全拒。
# 以下均为纯只读子命令（不写 refs/工作区/远程，零副作用）：
_AUTO_READONLY_GIT_SUBCOMMANDS = frozenset({
    "status", "log", "diff", "show", "blame", "ls-files", "ls-tree",
    "rev-parse", "describe", "show-ref", "ls-remote", "for-each-ref",
    "name-rev", "symbolic-ref", "count-objects", "shortlog", "whatchanged",
    "cherry", "check-ignore", "check-attr", "check-mailmap", "check-ref-format",
    "rev-list", "cat-file", "verify-pack", "var", "version", "help",
})

# git 混合子命令的只读形式（子命令本身可读可写，不能整体进只读集合，
# 按后续参数细分：命中以下形式 → pure-read；否则维持 local-reversible）：
_GIT_READONLY_FORMS_BY_SUB = {
    "branch": frozenset({"--show-current", "--list", "-a", "-r", "-v", "-vv"}),
    "stash":  frozenset({"list", "show"}),
    "remote": frozenset({"-v", "show"}),
    "tag":    frozenset({"-l", "--list"}),
    "config": frozenset({"--get", "--get-all", "--get-regexp", "--list", "-l", "--show-origin"}),
}


# 命令替换注入（$( 或反引号）绝不视为纯读——可在参数位置执行任意命令
_CMD_SUBSTITUTION_RE = _re.compile(r'\$\(|`[^`]*`')


def is_auto_readonly_command(command: str) -> bool:
    """auto 决策树 v1：整条命令是否纯读（逐段判定，火 4）。

    只读集合 v1（票 A-3）+ TICKET-AUTO-G1 扩充：git 纯只读子命令（status/log/diff/
    show/rev-parse/describe/show-ref/ls-files/ls-tree/blame 等 30+）与混合子命令
    只读形式（branch --show-current / stash list / remote -v / tag -l /
    config --get），范围不限 self-repo）+ 纯读白名单子集段。
    split_shell_segments 已按 | && ; 分段，任何一段非只读 → 整条不放行
    （防 `git status && rm -rf x` 借首段放行整链；`git status && echo ok`
    各段只读 → 放行）。解析失败 / 空命令 → 不放行（保守，安全默认）。
    命令替换注入（$( / 反引号）一律不放行——`echo $(rm -rf x)`、
    `echo \`id\`` 不得借 echo/cat 白名单放行（危险黑名单最高优先级）。
    """
    if _CMD_SUBSTITUTION_RE.search(command):
        return False
    segments = split_shell_segments(command.strip())
    if not segments:
        return False
    for tokens in segments:
        seg_cmd = " ".join(tokens)
        if not (_is_auto_readonly_git_segment(seg_cmd) or _is_auto_safe_segment(seg_cmd)):
            return False
    return True


def _is_auto_readonly_git_segment(cmd: str) -> bool:
    """单段判定：段首是真实 git 命令且子命令在只读集合内（或命中只读形式）。"""
    if not _has_real_git_command(cmd):
        return False
    subcommand = _find_git_subcommand(cmd)
    if subcommand in _AUTO_READONLY_GIT_SUBCOMMANDS:
        return True
    return _is_readonly_git_form(cmd, subcommand)


def _is_readonly_git_form(command: str, subcommand: str | None) -> bool:
    """git 混合子命令（branch/stash/remote/tag/config）只读形式判定。

    TICKET-AUTO-G1：这些子命令本身可读可写（如 branch -d 删除、stash pop
    应用并删除、remote add 写远程配置、tag -a 打标签、config 写键值），
    不能整体进只读集合；但只读形式（branch --show-current / stash list /
    remote -v / tag -l / config --get 等）零副作用 → pure-read。
    - 命中只读形式 → True（pure-read）
    - 写形式 / 无参数（如裸 git stash 省略子命令）→ False（维持原判定）
    """
    if not subcommand:
        return False
    forms = _GIT_READONLY_FORMS_BY_SUB.get(subcommand)
    if not forms:
        return False
    m = _re.search(r'\bgit\b\s+(.*)', command)
    if not m:
        return False
    try:
        args = _shlex.split(m.group(1))
    except ValueError:
        args = m.group(1).split()
    try:
        idx = args.index(subcommand)
        after = args[idx + 1:]
    except ValueError:
        after = args
    return any(a in forms for a in after)


# 白名单中的明确纯读子集（票 B 语义收紧：SAFE_COMMANDS 含 mkdir/cp/mv/pip/npm
# 等写命令，classify safe ≠ 只读。只有这些命令段才算 pure-read）
_PURE_READ_COMMANDS = frozenset({
    "ls", "cat", "echo", "pwd", "grep", "find", "head", "tail", "wc", "du",
    "df", "whoami", "date", "env", "which", "man", "diff", "sort", "uniq",
    "file", "stat", "less", "more", "clear", "history", "type", "uname",
    "hostname", "ps", "top", "tree", "awk", "tr", "pgrep", "pytest",
    "mdfind", "mdls", "sw_vers", "system_profiler", "sysctl", "nettop",
    "plutil", "pmset", "diskutil", "hdiutil", "say", "pbcopy", "pbpaste",
    "screencapture", "sips", "security", "codesign",
})


def _first_token(cmd: str) -> str:
    """取命令段的首 token（命令名）。解析失败退化为空格 split。"""
    try:
        return _shlex.split(cmd)[0]
    except Exception:
        parts = cmd.split()
        return parts[0] if parts else ""


def _is_auto_safe_segment(cmd: str) -> bool:
    """单段判定：段首命令在纯读白名单子集（ls/cat/grep 等明确只读）。

    注意：不能直接用 classify_command 的 safe 级——SAFE_COMMANDS 白名单含
    mkdir/cp/mv/pip/npm 等写命令，safe 不等于只读（票 B 语义收紧）。
    """
    return _first_token(cmd) in _PURE_READ_COMMANDS


# ── 票 B：副作用三级分类（B-1，按命令族 × 子命令） ──

# 本地可回滚的 git 子命令（改本地状态，可 reset/revert 回滚）
_LOCAL_REVERSIBLE_GIT_SUBCOMMANDS = frozenset({
    "add", "commit", "branch", "checkout", "stash", "tag", "merge",
    "config", "remote", "fetch", "mv", "rm",
})

# 外部不可逆命令模式（改外部/远程状态，不可回滚）
_EXTERNAL_IRREVERSIBLE_PATTERNS = [
    (r'\bgit\s+(push|push\s+.*--force)\b', "git push（外部远程）"),
    (r'\bnpm\s+publish\b', "npm publish（外部 registry）"),
    (r'\bpip\s+(publish|upload)\b', "pip upload（外部）"),
    (r'\bbrew\s+upgrade\b', "brew upgrade（外部）"),
    (r'\bscp\b', "scp（远程传输）"),
    (r'\bcurl\s+.*\s-([XTP]|request)\s+(POST|PUT|DELETE|PATCH)', "curl 写请求（POST/PUT/DELETE）"),
    (r'\bcurl\s+-[XTP]\s+(POST|PUT|DELETE|PATCH)', "curl 写请求（POST/PUT/DELETE）"),
    (r'\bcurl\s+-(X|request)\s+(POST|PUT|DELETE|PATCH)', "curl 写请求（POST/PUT/DELETE）"),
    (r'\bwget\s+.*\s-O', "wget 下载覆盖文件"),
]


def classify_side_effect(command: str) -> tuple[str, str]:
    """票 B-1：命令副作用三级分类，按命令族 × 子命令逐段判定。

    返回 (level, reason)：
    - pure-read：纯读零副作用 → auto 直接放行（票 A 归口复用）
    - local-reversible：改本地状态可回滚 → 先快照后放行（B-2）
    - external-irreversible：改外部/远程不可回滚 → auto 下仍弹窗（B-3）

    危险黑名单最高优先级：整条命令 split 前先过 DANGEROUS_PATTERNS，
    命中一律 external-irreversible（任何模式下不放行；split 后 `$ (` 会
    被 shlex 拆开导致 `\$\(` 失配，故必须在原始字符串上检查）。
    再逐段判定（复用 split_shell_segments，防 `git commit && git push`
    整链误放）：任何一段 external-irreversible → 整条 external-irreversible；
    否则任何一段 local-reversible → 整条 local-reversible；
    全段 pure-read → pure-read。
    空命令 / 解析失败 → external-irreversible（保守弹窗，安全默认）。
    """
    # 危险黑名单最高优先级：任何模式下命中一律转弹窗。
    # 票 AUTO-G2 误伤收紧：先剥离引号/heredoc 字面文本（骨架匹配），
    # cat > /tmp/x.py <<'EOF' 体内的 "git push --force" 字样是文件内容、不执行、不参与判定。
    # 注意：分段必须在剥离之后——shlex 会把 heredoc body 拍平成段内 token，
    # 先分段再剥离则 body 中的 "git push --force" 已失去 heredoc 结构、无法再剥离
    # （实弹取证发现，原实现 side_effect 对 heredoc 字面仍误判 external-irreversible）。
    _skeleton = strip_literal_text(command)
    for pattern, reason in DANGEROUS_PATTERNS:
        if _re.search(pattern, _skeleton):
            return ("external-irreversible", f"危险黑名单命中 — {reason}")

    segments = split_shell_segments(_skeleton)
    if not segments:
        return ("external-irreversible", "空命令或解析失败，保守弹窗")

    overall = "pure-read"
    for tokens in segments:
        seg_cmd = " ".join(tokens)
        level, _reason = _classify_segment_side_effect(seg_cmd)
        if level == "external-irreversible":
            return ("external-irreversible", _reason)
        if level == "local-reversible":
            overall = "local-reversible"
    if overall == "local-reversible":
        return ("local-reversible", "含本地可回滚写操作")
    return ("pure-read", "全段纯读")


def _classify_segment_side_effect(cmd: str) -> tuple[str, str]:
    """单段副作用判定。危险黑名单在任何模式下都是最高优先级。"""
    # 危险黑名单最高优先级：命中一律 external-irreversible 转弹窗
    # （含命令替换注入 $( / 反引号——`echo $(rm -rf x)`、`echo \`id\`` 不得
    #  借 echo/cat 纯读白名单误判 pure-read）
    # 票 AUTO-G2 误伤收紧：先剥离引号/heredoc 字面文本（骨架匹配），
    # heredoc/引号体内字样不参与危险判定。
    for pattern, reason in DANGEROUS_PATTERNS:
        if _re.search(pattern, strip_literal_text(cmd)):
            return ("external-irreversible", f"危险黑名单命中 — {reason}")

    # ── 票 SAFETY-1：进程杀灭——AUTO 下不自动执行（拒绝 + 待人工清单）。
    #  模式匹配杀灭（pkill/killall/按名 kill）已被上一步黑名单拦截；
    #  数字 PID 的 kill <pid> 也在此强制拒绝——杀灭不可回滚，禁止 auto 静默放行。
    _kill_level, _kill_reason = classify_kill_command(cmd)
    if _kill_level in ("dangerous", "confirm"):
        return ("external-irreversible", f"进程杀灭需人工确认 — {_kill_reason}")

    # 外部不可逆模式（含 git push / curl 写 / scp 等）
    # 票 AUTO-G2 误伤收紧：同样过骨架——heredoc/引号体内字样是文件内容不参与判定。
    for pattern, reason in _EXTERNAL_IRREVERSIBLE_PATTERNS:
        if _re.search(pattern, strip_literal_text(cmd)):
            return ("external-irreversible", reason)

    # git 命令：按子命令分 local-reversible / pure-read
    if _has_real_git_command(cmd):
        subcommand = _find_git_subcommand(cmd)
        if subcommand in _AUTO_READONLY_GIT_SUBCOMMANDS:
            return ("pure-read", f"git {subcommand}（只读）")
        if _is_readonly_git_form(cmd, subcommand):
            return ("pure-read", f"git {subcommand}（只读形式）")
        if subcommand in _LOCAL_REVERSIBLE_GIT_SUBCOMMANDS:
            return ("local-reversible", f"git {subcommand}（本地可回滚）")
        # 其他 git 子命令（reset --hard / clean 等）保守视为外部不可逆级（弹窗）
        return ("external-irreversible", f"git {subcommand}（无法确认可回滚）")

    # 非 git：纯读白名单子集 → pure-read；白名单写命令/gray → local-reversible；
    # dangerous → external-irreversible（保守弹窗）。
    # 注意不能用 classify safe 当只读——SAFE_COMMANDS 含 mkdir/cp/mv/pip 等写命令。
    base_cmd = _first_token(cmd)
    if base_cmd in _PURE_READ_COMMANDS:
        return ("pure-read", f"{base_cmd}（白名单纯读）")
    level, _reason = classify_command(cmd)
    if level == "dangerous":
        return ("external-irreversible", f"classify dangerous（{_reason}）")
    return ("local-reversible", f"{base_cmd or '?'}（本地操作，可回滚）")


# ── 票 O-1：OFFICE MODE 受保护清单 ──────────────────────────────────────────

def load_protected_paths(path: str | None = None) -> list[str]:
    """票 O-1：读取受保护清单（glob 表达式列表，相对项目根）。

    - 默认读 data/protected_paths.json（相对仓库根，不依赖 CWD）；
    - 缺失 / JSON 损坏 / 字段非法 → 返回空清单（不炸：office 裁决
      仍按角色与票据判定，清单纯属防御纵深）；
    - 返回的 globs 已去空白、去空串。
    """
    if path is None:
        path = _os.path.join(_BOBO_REPO_ROOT, "data", "protected_paths.json")
    try:
        with open(path, "r", encoding="utf-8") as _f:
            _data = _json.load(_f)
        _globs = _data.get("globs", [])
        if not isinstance(_globs, list):
            return []
        return [g.strip() for g in _globs if isinstance(g, str) and g.strip()]
    except Exception:
        return []


def is_protected(path: str, globs: list[str] | None = None) -> bool:
    """票 O-1：路径是否命中受保护清单（glob / 目录前缀匹配，相对项目根）。

    - 相对路径按原样匹配；绝对路径先转相对仓库根再匹配；
    - glob 命中（fnmatch）或目录前缀命中（`core/` 命中 `core/engine.py`）；
    - globs 为空（清单缺失）→ False（无清单即无保护，裁决不依赖它）。
    """
    if globs is None:
        globs = load_protected_paths()
    if not globs or not path:
        return False
    p = path.strip().lstrip("./")
    if p.startswith("/"):
        try:
            p = _os.path.relpath(p, _BOBO_REPO_ROOT)
        except Exception:
            pass
    for g in globs:
        g = g.strip().rstrip("/")
        if not g:
            continue
        if _fnmatch.fnmatch(p, g) or p.startswith(g + "/"):
            return True
    return False


def is_git_readonly_subcommand(subcommand: str | None) -> bool:
    """票 O-1：git 子命令是否只读（status/log/diff/show/blame/ls-files/ls-tree）。

    office 执法用：不在只读集合的 git 子命令一律视为写操作 → 员工全禁。
    """
    return subcommand in _AUTO_READONLY_GIT_SUBCOMMANDS
