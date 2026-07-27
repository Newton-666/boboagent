"""共享代码检查 — edit_file / file_operation 工具共用。

写 .py 文件后自动语法检查，失败不阻断，只附加醒目的状态信息。
"""

import sys
import subprocess


def py_compile_check(path: str) -> str:
    """写 .py 文件后自动语法检查。失败不阻断，只附加醒目的 ❌ 信息。

    Returns:
        "" （非 .py 文件），或带 ✅/❌/⚠️ 标记的状态字符串。
    """
    if not path.endswith(".py"):
        return ""
    try:
        r = subprocess.run(
            [sys.executable, "-m", "py_compile", path],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            return f"\n✅ py_compile 通过: {path}"
        stderr = r.stderr.strip().split("\n")[-10:]
        return f"\n❌ py_compile 失败: {path}\n{chr(10).join(stderr)}\n（文件已写入，但语法检查未过——必须立即修复，禁止交付）"
    except Exception as e:
        return f"\n⚠️ py_compile 未执行: {e}"
