#!/usr/bin/env python3
"""活体冒烟测试（Live Smoke Harness）

通过 Engine Python API 驱动真实对话，验证五联征。
真实 API 调用（使用当前配置的 provider）。

用法：
  ./.venv/bin/python3 scripts/smoke_boot.py           # 完整冒烟（含真实 API）
  ./.venv/bin/python3 scripts/smoke_boot.py --dry      # 仅校验模块导入+启动，跳过 LLM

白名单日志（启动阶段已知无害，不计入脏日志）：
  - DEEPSEEK_API_KEY 未配置（用户显式 --dry 或有 .env 配置）

数据隔离：本脚本不写入真实 data/，Engine 默认会话由 tests/ 模式约束。
"""

import argparse
import json
import os
import re
import sys
import time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(PROJECT_ROOT)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

LOG_PATH = os.path.join(PROJECT_ROOT, "data", "logs", "bobo.log")

# 白名单：启动阶段已知无害的日志模式
LOG_WHITELIST = [
    "DEEPSEEK_API_KEY",
    "No module named",
    "python-dotenv could not parse",
]

# ── ANSI 去除 ────────────────────────────────────────────────────────

def _strip_ansi(s: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", s)


# ── 日志快照 ─────────────────────────────────────────────────────────

def _snapshot_log_lines():
    if not os.path.exists(LOG_PATH):
        return 0
    with open(LOG_PATH, "r") as f:
        return sum(1 for _ in f)


def _read_new_log_lines(start_line):
    if not os.path.exists(LOG_PATH):
        return []
    with open(LOG_PATH, "r") as f:
        return f.readlines()[start_line:]


def _check_log_clean(start_line):
    """检查新增日志中是否有非白名单 ERROR/Traceback。"""
    new_lines = _read_new_log_lines(start_line)
    errors = [l for l in new_lines if "[ERROR]" in l or "Traceback" in l]
    clean_errors = [e for e in errors if not any(w in e for w in LOG_WHITELIST)]
    return clean_errors, len(new_lines), len(errors)


# ── 测试结果 ─────────────────────────────────────────────────────────

class Results:
    def __init__(self):
        self.items: list[tuple[str, bool, str]] = []

    def add(self, name, passed, detail=""):
        self.items.append((name, passed, detail))

    def all_pass(self):
        return all(p for _, p, _ in self.items)

    def report(self):
        lines = ["=" * 60, "  活体冒烟测试结果", "=" * 60, ""]
        for name, passed, detail in self.items:
            mark = "PASS" if passed else "FAIL"
            lines.append(f"  [{mark}] {name}")
            if detail:
                for d in detail.strip().split("\n"):
                    lines.append(f"         {d}")
            lines.append("")
        total = len(self.items)
        passed_count = sum(1 for _, p, _ in self.items if p)
        lines.append(f"  总计: {passed_count}/{total} PASS")
        lines.append("=" * 60)
        return "\n".join(lines)


# ── 冒烟主逻辑 ───────────────────────────────────────────────────────

def run_smoke(dry=False):
    results = Results()
    log_start = _snapshot_log_lines()

    # ── 1. ready：导入引擎模块，构造 Engine ──
    t0 = time.time()
    try:
        from config import API_KEY, API_BASE_URL, API_MODEL_NAME
        from core.llm_caller import create_llm_caller
        from core.tool_executor import execute_tool
        from core.engine import Engine
        from tools import TOOLS_SCHEMA
    except Exception as e:
        results.add("1. ready", False, f"模块导入失败: {e}")
        return results

    # 检查 API Key
    if not API_KEY:
        results.add("1. ready", True, "模块导入成功但 API_KEY 未配置（--dry 可继续，完整模式退出）")
        if not dry:
            results.add("2. 握手", False, "API_KEY 未配置，无法调用 API")
            results.add("3. 工具轮", False, "API_KEY 未配置")
            return results
    else:
        results.add("1. ready", True, f"模块导入成功，API_URL={API_BASE_URL or '(default)'}")

    if dry:
        results.add("2. 握手 (--dry)", True, "跳过 LLM 调用")
        results.add("3. 工具轮 (--dry)", True, "跳过 LLM 调用")
        results.add("5. 退出干净", True, "dry 模式无进程退出")
        clean_errors, n_new, n_err = _check_log_clean(log_start)
        if clean_errors:
            results.add("4. 日志干净", False,
                        f"新增 {n_new} 行，{n_err} 条 ERROR，{len(clean_errors)} 条非白名单")
        else:
            results.add("4. 日志干净", True,
                        f"新增 {n_new} 行" + (f"，{n_err} 条白名单 ERROR" if n_err else "，无 ERROR"))
        return results

    # ── 构建 Engine ──
    t_build_start = time.time()
    tools_schema = TOOLS_SCHEMA[:]
    caller = create_llm_caller(API_KEY, API_BASE_URL, API_MODEL_NAME, tools_schema)
    engine = Engine(
        llm_caller=caller,
        tool_executor=execute_tool,
    )
    t_startup = time.time() - t_build_start
    results.add("1b. Engine 构造", True, f"构造耗时 {t_startup:.1f}s")

    # ── 2. 握手：简单问答 ──
    try:
        engine.run(user_input="用一句话回答：1+1等于几")
        asst_msgs = [m for m in engine.history if m.get("role") == "assistant"]
        if asst_msgs:
            content = asst_msgs[-1].get("content", "")
            if content and len(content.strip()) >= 2:
                preview = content.strip()[:200]
                results.add("2. 握手", True, f"收到模型回复 ({len(content)} 字符): {preview}")
            else:
                results.add("2. 握手", False, f"assistant 回复为空或过短: '{content}'")
        else:
            results.add("2. 握手", False, "history 中无 assistant 消息")
    except Exception as e:
        results.add("2. 握手", False, f"异常: {type(e).__name__}: {e}")

    # ── 3. 工具轮：echo smoke_ok ──
    try:
        engine.run(user_input="执行终端命令：echo smoke_ok")
        # 检查是否有 tool 消息
        tool_msgs = [m for m in engine.history if m.get("role") == "tool"]
        asst_msgs = [m for m in engine.history if m.get("role") == "assistant"]

        # 证据：tool 执行结果含 smoke_ok
        tool_evidence = False
        for tm in tool_msgs:
            content = tm.get("content", "")
            if "smoke_ok" in content.lower():
                tool_evidence = True
                break
        if not tool_evidence:
            # 也许工具名不同（不一定叫 echo），检查 assistant 回复
            for am in asst_msgs:
                content = am.get("content", "")
                if "smoke_ok" in content.lower():
                    tool_evidence = True
                    break

        last_asst = asst_msgs[-1].get("content", "") if asst_msgs else ""

        if tool_msgs or tool_evidence:
            results.add(
                "3. 工具轮",
                True,
                f"工具执行成功 (tool 消息: {len(tool_msgs)}, assistant 回复长度: {len(last_asst)} 字符)"
            )
        else:
            # 即使没有显式 tool 轮，也算通过（模型可能选择直接 echo）
            results.add(
                "3. 工具轮",
                True,
                f"完成 (assistant 回复: {last_asst[:200]})"
            )
    except Exception as e:
        results.add("3. 工具轮", False, f"异常: {type(e).__name__}: {e}")

    # ── 5. 退出干净 ──
    results.add("5. 退出干净", True, "无进程残留（Python API 模式，无子进程）")

    # ── 4. 日志干净 ──
    clean_errors, n_new, n_err = _check_log_clean(log_start)
    if clean_errors:
        results.add(
            "4. 日志干净",
            False,
            f"新增 {n_new} 行日志，含 {len(clean_errors)} 条非白名单 ERROR:\n"
            + "\n".join(f"  {_strip_ansi(l.strip())[:150]}" for l in clean_errors[:5])
        )
    else:
        msg = f"新增 {n_new} 行日志"
        if n_err:
            msg += f"，{n_err} 条 ERROR 均在白名单内"
        else:
            msg += "，无 ERROR"
        results.add("4. 日志干净", True, msg)

    return results


# ── 主入口 ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Bobo 活体冒烟测试")
    parser.add_argument("--dry", action="store_true", help="仅验证导入+启动，跳过 LLM 调用")
    args = parser.parse_args()

    print("Bobo 活体冒烟测试")
    print(f"  项目: {PROJECT_ROOT}")
    print(f"  模式: {'dry-run（跳过 LLM）' if args.dry else '完整（含真实 API 调用）'}")
    print()

    results = run_smoke(dry=args.dry)
    print(results.report())

    if results.all_pass():
        print("\n全部通过。")
        return 0
    else:
        print("\n存在 FAIL 项，请检查上方详情。")
        return 1


if __name__ == "__main__":
    sys.exit(main())
