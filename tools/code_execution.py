"""code_execution.py - 执行代码并获取输出（带项目文件管理 + 自修复 + 测试生成）"""

import subprocess
import tempfile
import os
import time
from pathlib import Path

TOOL_NAME = "code_execution"

# 项目文件保存目录（从 config 读取，可通过环境变量 BOBO_PROJECTS_DIR 覆盖）
from config import PROJECTS_DIR as _CONFIG_PROJECTS_DIR
PROJECTS_DIR = Path(_CONFIG_PROJECTS_DIR)

# 自修复最大尝试次数
MAX_FIX_ATTEMPTS = 3


def _ensure_projects_dir():
    """确保 projects 目录存在"""
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)


def _save_code(code: str, language: str, task_name: str = None, version: str = "main") -> tuple:
    """
    保存代码到 projects 目录。

    Returns:
        tuple: (filepath, task_name)
    """
    _ensure_projects_dir()

    if not task_name:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        task_name = f"code_{timestamp}"

    ext_map = {"python": ".py", "javascript": ".js", "bash": ".sh"}
    ext = ext_map.get(language, ".txt")

    task_dir = PROJECTS_DIR / task_name
    task_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{version}{ext}"
    filepath = task_dir / filename
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(code)

    return str(filepath), task_name


def _save_run_log(task_name: str, output: str, version: str = "main"):
    """保存执行日志到 projects 目录"""
    task_dir = PROJECTS_DIR / task_name
    log_file = task_dir / "run.log"
    with open(log_file, 'a', encoding='utf-8') as f:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        f.write(f"[{timestamp}] ({version})\n{output}\n\n")


def _build_fix_prompt(code: str, error_output: str, language: str) -> list:
    """构造修复代码的 prompt"""
    prompt = f"""以下代码执行报错，请修复。

语言: {language}

代码:
```{language}
{code}
```

错误信息:
```
{error_output}
```

请只返回修复后的完整代码，不要任何解释。"""
    return [{"role": "user", "content": prompt}]


def _build_test_prompt(code: str, language: str) -> list:
    """构造生成测试的 prompt"""
    prompt = f"""请为以下代码生成测试。

语言: {language}

代码:
```{language}
{code}
```

要求：
- 使用 {language} 的标准测试框架
- 覆盖正常情况和边界情况
- 只返回测试代码，不要任何解释"""
    return [{"role": "user", "content": prompt}]


def _check_syntax(code: str, language: str) -> str:
    """
    本地语法检查。语法正确返回 None，错误返回错误描述。
    用于自修复循环中预检 LLM 返回的代码，避免无效执行。
    """
    if language == "python":
        try:
            import ast
            ast.parse(code)
            return None
        except SyntaxError as e:
            return f"语法错误: {e}"
    
    if language == "javascript":
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
                f.write(code)
                temp_file = f.name
            result = subprocess.run(['node', '--check', temp_file],
                                    capture_output=True, text=True, timeout=10)
            os.unlink(temp_file)
            if result.returncode != 0:
                return f"语法错误: {result.stderr.strip()[:100]}"
            return None
        except FileNotFoundError:
            return None
        except:
            return None
    
    if language == "bash":
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as f:
                f.write(code)
                temp_file = f.name
            result = subprocess.run(['bash', '-n', temp_file],
                                    capture_output=True, text=True, timeout=10)
            os.unlink(temp_file)
            if result.returncode != 0:
                return f"语法错误: {result.stderr.strip()[:100]}"
            return None
        except:
            return None
    
    return None


def _call_llm_for_fix(llm_caller, code: str, error_output: str, language: str) -> str:
    """调用 LLM 修复代码，返回修复后的代码"""
    messages = _build_fix_prompt(code, error_output, language)
    response = llm_caller(messages, use_tools=False)

    if isinstance(response, dict) and "error" in response:
        return None

    try:
        if isinstance(response, dict):
            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
        else:
            content = str(response)

        import re
        code_match = re.search(r'```(?:\w+)?\n(.*?)```', content, re.DOTALL)
        if code_match:
            return code_match.group(1).strip()
        return content.strip()
    except:
        return None


def _call_llm_for_test(llm_caller, code: str, language: str) -> str:
    """调用 LLM 生成测试代码"""
    messages = _build_test_prompt(code, language)
    response = llm_caller(messages, use_tools=False)

    if isinstance(response, dict) and "error" in response:
        return None

    try:
        if isinstance(response, dict):
            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
        else:
            content = str(response)

        import re
        code_match = re.search(r'```(?:\w+)?\n(.*?)```', content, re.DOTALL)
        if code_match:
            return code_match.group(1).strip()
        return content.strip()
    except:
        return None


def _run_test_file(test_path: str, language: str) -> str:
    """运行测试文件，返回测试结果"""
    try:
        if language == "python":
            result = subprocess.run(
                ['python3', '-m', 'pytest', test_path, '-q'],
                capture_output=True, text=True, timeout=30
            )
        elif language == "javascript":
            result = subprocess.run(
                ['node', '--test', test_path],
                capture_output=True, text=True, timeout=30
            )
        else:
            return "(不支持此语言的测试运行)"

        output = ""
        if result.stdout:
            output += result.stdout.strip()
        if result.stderr:
            if output:
                output += "\n"
            output += result.stderr.strip()
        
        if result.returncode == 0:
            return f"测试通过: {output[:100]}" if output else "测试通过"
        else:
            return f"测试失败: {output[:200]}"
    except subprocess.TimeoutExpired:
        return "测试执行超时（30秒）"
    except FileNotFoundError:
        return "测试运行环境未安装"
    except Exception as e:
        return f"测试执行失败: {e}"


def execute(code: str, language: str = "python", type: str = "run",
            llm_caller: callable = None) -> str:
    """执行代码

    Args:
        code: 代码内容
        language: python, javascript, bash
        type: run(执行), lint(检查语法), test(运行测试)
        llm_caller: LLM 调用函数（可选），传入后启用自修复和测试生成
    """
    # 先保存代码
    filepath, task_name = _save_code(code, language)

    if type == "run":
        result = _run_code(code, language)
    elif type == "lint":
        result = _lint_code(code, language)
    else:
        result = f"未知类型: {type}"

    # 保存执行日志
    _save_run_log(task_name, result)

    # ── 自修复：执行失败且有 llm_caller 时 ──
    if type == "run" and llm_caller is not None and _is_error_result(result):
        fixed_code = code
        for attempt in range(1, MAX_FIX_ATTEMPTS + 1):
            version = f"fix_v{attempt}"
            fixed_code = _call_llm_for_fix(llm_caller, fixed_code, result, language)
            if fixed_code is None:
                break

            syntax_error = _check_syntax(fixed_code, language)
            if syntax_error:
                result = syntax_error
                _save_run_log(task_name, result, version=version)
                continue

            fix_path, _ = _save_code(fixed_code, language, task_name, version=version)
            result = _run_code(fixed_code, language)
            _save_run_log(task_name, result, version=version)

            if not _is_error_result(result):
                return f"{result}\n(已自动修复，第{attempt}次成功，代码: {fix_path})"

        return f"{result}\n(已尝试修复{MAX_FIX_ATTEMPTS}次，均失败，最终代码: {fix_path})"

    # ── 测试生成：执行成功且有 llm_caller 时 ──
    if type == "run" and llm_caller is not None and not _is_error_result(result):
        test_code = _call_llm_for_test(llm_caller, code, language)
        if test_code:
            test_path, _ = _save_code(test_code, language, task_name, version="test")
            # 自动运行测试并获取结果
            test_result = _run_test_file(test_path, language)
            _save_run_log(task_name, f"测试结果: {test_result}", version="test")
            return f"{result}\n(代码已保存: {filepath})\n(测试已生成: {test_path})\n(测试结果: {test_result})"

    return f"{result}\n(代码已保存: {filepath})"


def _is_error_result(output: str) -> bool:
    """判断执行结果是否包含错误"""
    error_indicators = ["执行失败", "执行超时", "Error:", "Traceback", "SyntaxError",
                        "NameError", "TypeError", "ValueError", "IndexError", "KeyError",
                        "AttributeError", "ImportError", "ModuleNotFoundError", "FileNotFoundError",
                        "ZeroDivisionError", "IndentationError"]
    for indicator in error_indicators:
        if indicator in output:
            return True
    return False


def _run_code(code, language):
    if language == "python":
        return _run_python(code)
    elif language == "javascript":
        return _run_javascript(code)
    elif language == "bash":
        return _run_bash(code)
    else:
        return f"不支持的语言: {language}"


def _run_python(code):
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            temp_file = f.name

        result = subprocess.run(
            ['python3', temp_file],
            capture_output=True,
            text=True,
            timeout=30
        )
        os.unlink(temp_file)

        output = ""
        if result.stdout:
            output += result.stdout
        if result.stderr:
            if output:
                output += "\n[stderr]\n"
            output += result.stderr
        if not output:
            output = "(执行成功，无输出)"
        return output[:2000]
    except subprocess.TimeoutExpired:
        return "执行超时（30秒）"
    except Exception as e:
        return f"执行失败: {e}"


def _run_javascript(code):
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
            f.write(code)
            temp_file = f.name

        result = subprocess.run(
            ['node', temp_file],
            capture_output=True,
            text=True,
            timeout=30
        )
        os.unlink(temp_file)

        output = ""
        if result.stdout:
            output += result.stdout
        if result.stderr:
            if output:
                output += "\n[stderr]\n"
            output += result.stderr
        if not output:
            output = "(执行成功，无输出)"
        return output[:2000]
    except FileNotFoundError:
        return "Node.js 未安装，无法执行 JavaScript"
    except subprocess.TimeoutExpired:
        return "执行超时（30秒）"
    except Exception as e:
        return f"执行失败: {e}"


def _run_bash(code):
    """执行 Bash 代码（写入临时文件，不使用 shell=True）"""
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as f:
            f.write(code)
            temp_file = f.name

        result = subprocess.run(
            ['bash', temp_file],
            capture_output=True,
            text=True,
            timeout=30
        )
        os.unlink(temp_file)

        output = ""
        if result.stdout:
            output += result.stdout
        if result.stderr:
            if output:
                output += "\n[stderr]\n"
            output += result.stderr
        if not output:
            output = "(执行成功，无输出)"
        return output[:2000]
    except subprocess.TimeoutExpired:
        return "执行超时（30秒）"
    except Exception as e:
        return f"执行失败: {e}"


def _lint_code(code, language):
    if language == "python":
        try:
            import ast
            ast.parse(code)
            return "语法检查通过，无错误"
        except SyntaxError as e:
            return f"语法错误: {e}"
    else:
        return f"暂不支持 {language} 的语法检查"


TOOL_FUNC = execute
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": "执行代码并获取输出。支持 Python、JavaScript、Bash。可用于测试和验证代码。",
        "parameters": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "要执行的代码"},
                "language": {"type": "string", "enum": ["python", "javascript", "bash"], "description": "编程语言"},
                "type": {"type": "string", "enum": ["run", "lint"], "description": "执行类型"}
            },
            "required": ["code", "language"]
        }
    }
}


def register(reg):
    reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA)
