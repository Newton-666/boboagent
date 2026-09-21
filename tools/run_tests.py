"""run_tests.py — 自动发现并运行项目测试

用法：
    run_tests(path=".", framework="auto")

特点：
    - 自动检测测试框架（pytest / jest / go test）
    - 超时保护（默认 120s）
    - 结果返回 pass/fail + 失败详情
    - 与 edit_file + file_writer 配合，形成 改代码 → 跑测试 → 修复 闭环
"""

import os
import re
import subprocess
from pathlib import Path


TIMEOUT = 120  # 秒


def _run_cmd(cmd, timeout, cwd=None):
    from core.tool_lifecycle import run_cancellable_subprocess
    return run_cancellable_subprocess(cmd, timeout=timeout, cwd=cwd)


def _detect_framework(project_dir: Path) -> str | None:
    """自动检测项目的测试框架。"""
    # pytest
    if (project_dir / "pyproject.toml").exists():
        return "pytest"
    if (project_dir / "setup.cfg").exists():
        return "pytest"
    if list(project_dir.glob("test_*.py")) or list(project_dir.glob("*_test.py")):
        return "pytest"
    if (project_dir / "tests").is_dir():
        return "pytest"

    # jest
    if (project_dir / "package.json").exists():
        try:
            import json
            pkg = json.loads((project_dir / "package.json").read_text())
            scripts = pkg.get("scripts", {})
            if "test" in scripts:
                return "jest"
        except Exception:
            pass

    # go
    if list(project_dir.glob("*_test.go")):
        return "go"

    return None


_last_test_results: dict[str, tuple[int, str]] = {}


def _run_pytest(project_dir: Path) -> str:
    """运行 pytest，返回格式化的结果。"""
    try:
        result = _run_cmd(
            ["python3", "-m", "pytest", str(project_dir), "-q", "--tb=short"],
            timeout=TIMEOUT, cwd=str(project_dir)
        )
    except FileNotFoundError:
        return "pytest 未安装。运行: pip install pytest"
    except subprocess.TimeoutExpired:
        return f"测试超时（>{TIMEOUT}s）"

    output = (result.stdout + result.stderr).strip()
    if not output:
        output = "(无输出)"

    # 提取关键信息：通过/失败数
    summary = ""
    passed_match = re.search(r'(\d+) passed', output)
    failed_match = re.search(r'(\d+) failed', output)
    error_match = re.search(r'(\d+) error', output)

    parts = []
    if passed_match:
        parts.append(f"{passed_match.group(1)} 通过")
    if failed_match:
        parts.append(f"{failed_match.group(1)} 失败")
    if error_match:
        parts.append(f"{error_match.group(1)} 错误")
    summary = ", ".join(parts) if parts else "完成"

    # 失败时只保留关键部分
    if result.returncode != 0:
        # 截取前 3000 字符，优先保留 FAILURES 部分
        failures_idx = output.find("FAILURES")
        if failures_idx > 0:
            output = output[failures_idx:failures_idx + 3000]
        else:
            output = output[:3000]

    result_text = f"[pytest] {summary}\n\n{output[:3000]}"

    # 测试回归分析：对比上次运行结果
    key = str(project_dir)
    if result.returncode != 0 and key in _last_test_results:
        old_code, old_out = _last_test_results[key]
        if old_code != 0:
            old_fail = re.search(r'(\d+) failed', old_out)
            new_fail = re.search(r'(\d+) failed', output)
            if old_fail and new_fail:
                old_n = int(old_fail.group(1))
                new_n = int(new_fail.group(1))
                diff = new_n - min(new_n, old_n)
                if diff <= 0:
                    result_text += "\n[提示] 这些失败在上次运行时已存在，不是本次修改导致的"
                elif diff < new_n:
                    result_text += f"\n[提示] 相比上次，新增 {diff} 个失败，{new_n - diff} 个失败已存在"
    _last_test_results[key] = (result.returncode, output)

    return result_text

def _run_jest(project_dir: Path) -> str:
    """运行 jest。"""
    try:
        result = _run_cmd(
            ["npx", "jest", "--no-coverage", "--verbose"],
            timeout=TIMEOUT, cwd=str(project_dir)
        )
    except FileNotFoundError:
        return "Node.js / npx 未安装"
    except subprocess.TimeoutExpired:
        return f"测试超时（>{TIMEOUT}s）"

    output = (result.stdout + result.stderr).strip()
    if not output:
        output = "(无输出)"

    tests_match = re.search(r'Tests:\s+(.*)', output)
    summary = tests_match.group(1) if tests_match else "完成"

    status = "通过" if result.returncode == 0 else "失败"
    return f"[jest] {status}: {summary}\n\n{output[:3000]}"


def _run_go_test(project_dir: Path) -> str:
    """运行 go test。"""
    try:
        result = _run_cmd(
            ["go", "test", "./..."],
            timeout=TIMEOUT, cwd=str(project_dir)
        )
    except FileNotFoundError:
        return "Go 未安装"
    except subprocess.TimeoutExpired:
        return f"测试超时（>{TIMEOUT}s）"

    output = (result.stdout + result.stderr).strip()
    status = "通过" if result.returncode == 0 else "失败"
    return f"[go test] {status}\n\n{output[:3000]}"


def execute(path: str = ".", framework: str = "auto") -> str:
    """运行项目测试。

    Args:
        path: 项目根目录路径（默认当前工作目录）
        framework: 测试框架，支持 auto / pytest / jest / go。默认 auto 自动检测。
    """
    try:
        from core.tool_lifecycle import is_cancelled
        if is_cancelled():
            return "错误: 操作已取消（超时），未运行测试"
    except Exception:
        pass
    project_dir = Path(path).expanduser().resolve()
    if not project_dir.exists():
        return f"错误: 目录不存在: {project_dir}"
    if not project_dir.is_dir():
        return f"错误: 不是目录: {project_dir}"

    if framework == "auto":
        detected = _detect_framework(project_dir)
        if detected is None:
            # 最后的尝试：看看有没有 Makefile 或 tox
            if (project_dir / "Makefile").exists():
                return "检测到 Makefile，请手动指定 framework 或用 execute_terminal 运行 make test"
            return (
                f"在 {project_dir} 下未自动检测到测试框架。\n"
                f"  支持的框架: pytest, jest, go\n"
                f"  或用 framework 参数手动指定，或用 execute_terminal 直接运行测试命令。"
            )
        framework = detected

    if framework == "pytest":
        return _run_pytest(project_dir)
    elif framework == "jest":
        return _run_jest(project_dir)
    elif framework == "go":
        return _run_go_test(project_dir)
    else:
        return f"不支持的测试框架: {framework}。支持: auto, pytest, jest, go"


def register(reg):
    reg("run_tests", execute, {
        "type": "function",
        "function": {
            "name": "run_tests",
            "description": (
                "运行项目的测试套件，返回通过/失败状态和失败详情。"
                "修改代码后应运行此工具，验证没有破坏已有功能。"
                "如果测试失败，用 grep_code 定位问题代码，用 edit_file 修复，再运行 run_tests 验证。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "项目根目录路径。默认为当前工作目录。"
                    },
                    "framework": {
                        "type": "string",
                        "enum": ["auto", "pytest", "jest", "go"],
                        "description": "测试框架。默认 auto 自动检测。"
                    }
                }
            }
        }
    })
