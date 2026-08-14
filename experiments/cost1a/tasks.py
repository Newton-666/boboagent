#!/usr/bin/env python3
"""五道固定任务 + 确定性判分（TICKET-COST-1A-SANDBOX）。

判分只看产物：文件内容断言 / 命令输出断言 / memory.jsonl / 最终回复关键字，
不看模型自评，不看用了什么工具——四档可比（C 档无笔记工具也能用 edit 完成）。
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

TASKS = ["t1_bugfix", "t2_search", "t3_refactor", "t4_memory", "t5_note"]


def setup_t1(sandbox: Path):
    (sandbox / "buggy.py").write_text(
        "def add(a, b):\n    return a - b  # BUG: should be a + b\n\n"
        "def main():\n    print(add(2, 3))\n\nif __name__ == '__main__':\n    main()\n",
        encoding="utf-8")
    (sandbox / "test_buggy.py").write_text(
        "from buggy import add\n\ndef test_add():\n    assert add(2, 3) == 5\n    assert add(-1, 1) == 0\n",
        encoding="utf-8")


def setup_t2(sandbox: Path):
    code = (sandbox / "codebase")
    code.mkdir(exist_ok=True)
    (code / "mod_a.py").write_text(
        "# 模块 A\nCOST1A_MAGIC_VALUE = 314159\n\ndef helper():\n    return COST1A_MAGIC_VALUE\n",
        encoding="utf-8")
    (code / "mod_b.py").write_text(
        "# 模块 B\nfrom mod_a import COST1A_MAGIC_VALUE\n\ndef report():\n    return f'value={COST1A_MAGIC_VALUE}'\n",
        encoding="utf-8")
    (code / "mod_c.py").write_text(
        "# 模块 C（无关模块）\nPLAIN = 42\n", encoding="utf-8")


def setup_t3(sandbox: Path):
    (sandbox / "a.py").write_text(
        "def legacy_name(x):\n    return x * 2\n\ndef main():\n    print(legacy_name(21))\n",
        encoding="utf-8")
    (sandbox / "b.py").write_text(
        "from a import legacy_name\n\ndef run():\n    return legacy_name(10)\n", encoding="utf-8")


def setup_t4(sandbox: Path):
    pass  # 无文件；用 save_memory


def setup_t5(sandbox: Path):
    notes = sandbox / "notes"
    if notes.exists():
        for f in notes.iterdir():
            f.unlink()  # 清残留，保证确定性
    notes.mkdir(exist_ok=True)


SETUPS = {
    "t1_bugfix": setup_t1,
    "t2_search": setup_t2,
    "t3_refactor": setup_t3,
    "t4_memory": setup_t4,
    "t5_note": setup_t5,
}

TASK_PROMPTS = {
    "t1_bugfix": (
        "沙盒里有一个 buggy.py：它的 add 函数有 bug（两个数相加返回了错误结果）。"
        "请读取文件定位 bug，用 edit_file 修复，然后用 execute_terminal 运行 "
        "'python3 -m pytest test_buggy.py' 验证测试通过。最后简要说明你做了什么。"
    ),
    "t2_search": (
        "沙盒 codebase/ 目录有一个代码库。请用 grep_code 定位常量 "
        "COST1A_MAGIC_VALUE 的定义位置（哪个文件、第几行、值是多少），"
        "并在最终回复中给出文件路径、行号和值。"
    ),
    "t3_refactor": (
        "沙盒里有 a.py 和 b.py，其中函数 legacy_name 被两处引用。"
        "请把 legacy_name 重命名为 modern_name，a.py 的定义和 b.py 的引用都要改。"
        "最后用 execute_terminal 运行 'python3 -c \"from b import run; print(run())\"' 验证。"
    ),
    "t4_memory": (
        "请用 save_memory 保存一条事实：'团队代号为 COST1A-BRAVO'。"
        "保存成功后，在最终回复中告诉我你记住了什么（引用保存的内容）。"
    ),
    "t5_note": (
        "请用笔记工具（obsidian 系）在沙盒 notes/ 目录下创建一篇笔记，"
        "文件名 meeting-2026.md，内容包含'COST1A 沙盒实验启动'。"
        "（B 档请使用 obsidian_tool 并选择正确的 action；"
        "A/D 档使用 write_obsidian 原始工具。）完成后确认文件名与内容。"
    ),
}

# B 档 action 选错率统计：任务 5 的期望 action（写笔记）
EXPECTED_ACTIONS = {
    "t5_note": {"write_obsidian", "append_obsidian"},
}


def _run_cmd(sandbox: Path, cmd: str) -> str:
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                           timeout=15, cwd=str(sandbox))
        return (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        return "TIMEOUT"


def judge_t1(sandbox: Path, reply: str, calls: list[dict]) -> tuple[bool, str]:
    """文件修复 + 测试通过。"""
    src = (sandbox / "buggy.py").read_text(encoding="utf-8")
    ok_fix = ("a + b" in src and "a - b" not in src)
    out = _run_cmd(sandbox, f"{sys.executable} -m pytest test_buggy.py -q")  # 终审修复：用当前解释器，不依赖 PATH 里的 python3 有 pytest
    ok_test = "passed" in out and "failed" not in out
    return (ok_fix and ok_test), f"fix={ok_fix} test={ok_test}"


def judge_t2(sandbox: Path, reply: str, calls: list[dict]) -> tuple[bool, str]:
    """回复包含文件路径 + 行号 + 值。"""
    ok_file = "mod_a.py" in reply
    ok_val = "314159" in reply
    ok_line = bool(re.search(r"\bline\s*[：:]?\s*\d+|第\s*\d+\s*行|:\s*\d+", reply))
    return (ok_file and ok_val and ok_line), f"file={ok_file} val={ok_val} line={ok_line}"


def judge_t3(sandbox: Path, reply: str, calls: list[dict]) -> tuple[bool, str]:
    """两文件改名完成 + 运行验证。"""
    a = (sandbox / "a.py").read_text(encoding="utf-8")
    b = (sandbox / "b.py").read_text(encoding="utf-8")
    ok_rename = ("modern_name" in a and "legacy_name" not in a
                 and "modern_name" in b and "legacy_name" not in b)
    out = _run_cmd(sandbox, f'{sys.executable} -c "from b import run; print(run())"')  # 同上
    ok_run = "20" in out
    return (ok_rename and ok_run), f"rename={ok_rename} run={ok_run}"


def judge_t4(sandbox: Path, reply: str, calls: list[dict]) -> tuple[bool, str]:
    """memory.jsonl 有事实 + 回复引用。"""
    mem = sandbox / "memory.jsonl"
    ok_saved = mem.exists() and "COST1A-BRAVO" in mem.read_text(encoding="utf-8")
    ok_reply = "COST1A-BRAVO" in reply
    return (ok_saved and ok_reply), f"saved={ok_saved} reply={ok_reply}"


def judge_t5(sandbox: Path, reply: str, calls: list[dict]) -> tuple[bool, str]:
    """笔记文件存在且内容对（不看工具）。"""
    note = sandbox / "notes" / "meeting-2026.md"
    # 兼容：模型可能建了别的路径（notes/meeting-2026.md 或 notes/meeting-2026）
    candidates = [note, sandbox / "notes" / "meeting-2026"]
    hit = next((p for p in candidates if p.exists()), None)
    if hit is None:
        return False, "笔记文件不存在"
    content = hit.read_text(encoding="utf-8")
    ok_content = "COST1A 沙盒实验启动" in content
    return ok_content, f"note={hit.name} content={ok_content}"


JUDGES = {
    "t1_bugfix": judge_t1,
    "t2_search": judge_t2,
    "t3_refactor": judge_t3,
    "t4_memory": judge_t4,
    "t5_note": judge_t5,
}


def judge(task_id: str, sandbox: Path, reply: str, calls: list[dict]) -> tuple[bool, str]:
    return JUDGES[task_id](sandbox, reply, calls)
