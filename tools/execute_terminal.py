"""执行终端命令（高风险操作，需要用户确认）"""

import signal
import subprocess
import shlex
import re
import os
import threading
import time
from core.file_safety import sanitize_env

# ── 票 AUTO-E2：ESC 随时硬中断 ──────────────────────────────
# 轮询间隔（100-200ms）：ESC → 进程死亡 ≤2s 的验收口径，150ms 裕量充足
_POLL_INTERVAL = 0.15
# 杀进程组宽限：先 TERM，宽限期内未死再 KILL
_KILL_GRACE = 2.0

TOOL_NAME = "execute_terminal"

# 真正危险的命令模式（与 engine.py DANGEROUS_PATTERNS 保持一致，
# 作为最后一道防线——engine 已通过 _classify_command + 用户确认做了一级防护）
DANGEROUS_PATTERNS = [
    r'rm\s+(-[rRf]|--recursive|--force)',      # rm -rf /path（对齐 engine.py:772）
    r'sudo\s+',                          # sudo 命令
    r'chmod\s+777\s+',                   # chmod 777
    r'chown\s+',                         # chown
    r'dd\s+of=',                         # dd 写入
    r'>\s*/dev/(sd[a-z]+|disk\d+|nvme\d+n\d+|mmcblk\d+)',  # 写入磁盘设备（排除 /dev/null /dev/urandom 等）
    r':\s*\(\s*\)\s*:\s*',               # fork bomb
    r'\|\s*sh\s*',                       # pipe to sh
    r'\|\s*bash\s*',                     # pipe to bash
    r'\$\(',                             # 命令替换 $(...)
    r'curl.*\$\(',                       # curl + 命令替换
    r'wget.*\$\(',                       # wget + 命令替换
]

# 命令长度限制（防止超长命令注入）
MAX_COMMAND_LENGTH = 10000

# 高危字符（反引号命令替换）
BLOCKED_CHARS = set('`')


def is_dangerous(command: str) -> bool:
    """检查命令是否危险"""
    # 长度检查
    if len(command) > MAX_COMMAND_LENGTH:
        return True
    
    # 票 AUTO-G2：误伤收紧——先剥离引号/heredoc 字面文本（骨架匹配），
    # cat > /tmp/x.py <<'EOF' 体内的危险字样是文件内容不执行、不参与判定。
    # 含命令替换的引号体/裸 heredoc 由 strip_literal_text 保守保留（安全语义不动）。
    from core.command_safety import strip_literal_text
    _skeleton = strip_literal_text(command)

    # 危险模式匹配
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, _skeleton):
            return True
    
    # 禁止字符检查（反引号执行、变量注入）
    for char in BLOCKED_CHARS:
        if char in _skeleton:
            return True
    
    return False


def _kill_process_group(proc):
    """TERM 整组 → 宽限 → KILL 整组。

    start_new_session=True 保证 pgid == pid，killpg 杀整组可覆盖
    子进程的子进程（防止成孤儿）；TERM 后宽限期内未死再 KILL。
    """
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        pass
    try:
        proc.wait(timeout=_KILL_GRACE)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        proc.wait()


def execute(command: str, timeout: int = 30, _interrupt_event=None, _project_root: str | None = None) -> str:
    """执行终端命令并返回输出。

    票 AUTO-E2：运行期间每 _POLL_INTERVAL 检查一次 _interrupt_event，
    一旦 set 立即杀进程组（ESC 硬中断 ≤2s），返回结果带 ⛔ 中断标注，
    已产生的部分 stdout/stderr 一并返回（现场证据不丢）。
    _interrupt_event 由 tool_runner 注入（engine._interrupt_event），
    schema 不暴露，LLM 无法伪造。

    票 DESK-P1：_project_root 由 tool_runner 注入（engine.project_root，
    会话级，来自 gateway 落库）。有值且为目录时 Popen cwd=该项目根——
    文件操作/终端命令默认落在项目目录；None 保持默认现状（进程 cwd）。
    schema 不暴露，LLM 无法伪造。
    """
    try:
        # 参数类型校验
        if not isinstance(command, str):
            return f"错误: command 参数必须是字符串，收到 {type(command).__name__}"

        # 空命令检查
        if not command.strip():
            return "错误: 命令不能为空"

        # 安全检查
        if is_dangerous(command):
            # 审计 #27：engine 已做确认流程，工具层是最后一道防线；
            # 被拦时明确告知"已拦截"而非误导"需要确认"
            return f"⛔ 安全策略拦截: {command}\n此命令已被内置黑名单拦截，请换用安全替代方案。"

        # 使用 shell 执行（支持管道、重定向），环境变量已脱敏
        # 安全防护由上游 Engine 的 _is_high_risk_tool + 用户确认机制保障
        clean_env = sanitize_env()
        # 票 DESK-P1：会话项目根作为默认 cwd（_project_root 由 tool_runner
        # 注入，LLM 不可见；None/不存在目录 → 保持进程 cwd 现状）
        _cwd = None
        if _project_root and os.path.isdir(_project_root):
            _cwd = _project_root
        proc = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            executable='/bin/bash',
            env=clean_env,
            cwd=_cwd,
            start_new_session=True,  # E2-1：独立进程组，可整组 killpg
        )

        # 后台读线程：轮询期间不读管道会写满缓冲死锁（大输出命令），
        # 用 daemon 线程持续排空 stdout/stderr
        out_chunks, err_chunks = [], []

        def _drain(stream, sink):
            try:
                for line in stream:
                    sink.append(line)
            except Exception:
                pass

        t_out = threading.Thread(target=_drain, args=(proc.stdout, out_chunks), daemon=True)
        t_err = threading.Thread(target=_drain, args=(proc.stderr, err_chunks), daemon=True)
        t_out.start()
        t_err.start()

        # E2-1：轮询循环——中断事件 / 进程结束 / 超时 三者其一即退出
        interrupted = False
        timed_out = False
        deadline = time.time() + timeout
        while True:
            if _interrupt_event is not None and _interrupt_event.is_set():
                interrupted = True
                _kill_process_group(proc)
                break
            if proc.poll() is not None:
                break
            if time.time() > deadline:
                timed_out = True
                _kill_process_group(proc)
                break
            time.sleep(_POLL_INTERVAL)

        t_out.join(timeout=1.0)
        t_err.join(timeout=1.0)
        proc.wait()

        output = ""
        if out_chunks:
            output = "".join(out_chunks)
        if err_chunks:
            if output:
                output += "\n[stderr]\n"
            output += "".join(err_chunks)

        # 中断：现场证据不丢，标注明确
        if interrupted:
            partial = output.strip()[:4000] or "（尚无输出）"
            return f"⛔ 已被用户中断（ESC）\n已有部分输出:\n{partial}"

        if timed_out:
            partial = output.strip()[:2000]
            hint = f"\n如果需要更长时间，请指定更大的 timeout 参数后重试。" if partial else "无输出。如果需要更长时间，请指定更大的 timeout 参数后重试。"
            return f"命令执行超过 {timeout}s（当前上限），已终止。已有部分输出:\n{partial}{hint}"

        if not output:
            output = "(命令执行成功，无输出)"

        if len(output) > 8000:
            output = output[:8000] + "\n... (输出被截断)"

        return output.strip()

    except Exception as e:
        return f"执行失败: {str(e)}"


TOOL_FUNC = execute
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": """【用途】在终端中执行命令。
【适用场景】用户要求"运行XX命令"、"执行XX"、"查看系统信息"等。
【支持】管道(|)、重定向(>)、变量($) 等 shell 特性。
【注意】rm -rf, sudo, chmod 777 等危险命令会被拦截。""",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "要执行的命令，例如 'ls -la' 或 'ps aux | grep python'"
                },
                "timeout": {
                    "type": "integer",
                    "description": "超时时间（秒），默认30秒"
                }
            },
            "required": ["command"]
        }
    }
}


def register(reg):
    reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA)
