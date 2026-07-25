#!/usr/bin/env python3
"""
Context Engineering — Result Marking 效果对比基准测试

对比方案 A（传统方式：完整结果直接进上下文）vs 方案 B（标记方式：结果存 workspace，对话历史只留标记）。

不修改任何源代码。直接调用 Engine._maybe_mark_result() 和 load_result.execute()。
"""

import json
import os
import sys
import time
from pathlib import Path

# 确保能导入项目模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# ── 模拟的工具结果样本 ──

SAMPLE_RESULTS = {
    "read_local_file": {
        "tool": "read_local_file",
        "args": {"file_path": "/project/src/main.py"},
        "content": "\n".join(
            [f"# line {i}: some python code content for benchmarking purposes" for i in range(200)]
        ),
    },
    "web_search": {
        "tool": "web_search",
        "args": {"query": "Python async frameworks comparison 2026"},
        "content": (
            "DuckDuckGo 搜索结果:\n"
            "1. asyncio vs trio vs anyio: a comprehensive comparison\n"
            "   Asyncio is the standard library, trio focuses on structured concurrency,\n"
            "   anyio provides a unified API across both.\n"
            "2. Choosing the right async framework for your project\n"
            "   Consider: ecosystem, learning curve, error handling, cancellation.\n"
            "3. Performance benchmarks 2026\n"
            "   Trio shows 15% better throughput in I/O-bound tasks.\n"
            "   Anyio adds ~3% overhead but provides framework flexibility.\n"
            "4. Real-world adoption\n"
            "   FastAPI (anyio), Quart (asyncio), HTTPX (anyio).\n"
        ),
    },
    "grep_code": {
        "tool": "grep_code",
        "args": {"pattern": "def _call_llm", "path": "."},
        "content": "\n".join(
            [f"/project/core/engine.py:{100 + i * 10}: def _call_llm(self, ...)" for i in range(50)]
        ),
    },
    "web_fetch": {
        "tool": "web_fetch",
        "args": {"url": "https://example.com/docs/api"},
        "content": "<html><head><title>API Documentation</title></head><body>" + "x" * 8000 + "</body></html>",
    },
    "execute_terminal": {
        "tool": "execute_terminal",
        "args": {"command": "ls -la"},
        "content": "total 128\ndrwxr-xr-x  16 user  staff   512 Jul 20 10:00 .\ndrwxr-xr-x   8 user  staff   256 Jul 20 09:55 ..\n-rw-r--r--   1 user  staff  2048 Jul 20 09:55 main.py\n-rw-r--r--   1 user  staff  1024 Jul 20 09:55 utils.py",
    },
}


def format_bytes(n: int) -> str:
    if n < 1024:
        return f"{n}B"
    elif n < 1024 * 1024:
        return f"{n / 1024:.1f}KB"
    else:
        return f"{n / 1024 / 1024:.1f}MB"


def run_benchmark():
    from core.tool_runner import ToolRunnerMixin
    from tools.load_result import execute as load_result_execute, WORKSPACE_DIR

    print("=" * 70)
    print("  Context Engineering — Result Marking 效果对比基准测试")
    print("=" * 70)
    print()

    # 创建临时 workspace
    import tempfile
    import shutil

    tmp_ws = Path(tempfile.mkdtemp(prefix="ctx_bench_"))
    original_ws = ToolRunnerMixin.WORKSPACE_DIR
    ToolRunnerMixin.WORKSPACE_DIR = str(tmp_ws)
    # 同步 load_result 的 WORKSPACE_DIR（它是一个同路径的独立变量）
    import tools.load_result as lr_mod
    lr_mod.WORKSPACE_DIR = str(tmp_ws)

    # 偷懒建一个 mock engine 来调用 _maybe_mark_result
    # 需要 engine 实例，但 _maybe_mark_result 只用了 self.MARKING_TOOLS, self.WORKSPACE_DIR
    # 和 self.current_tool_round，所以我们 mock 一下
    class MockEngine:
        MARKING_TOOLS = ToolRunnerMixin.MARKING_TOOLS
        WORKSPACE_DIR = str(tmp_ws)
        current_tool_round = 5

    engine = MockEngine()
    # 把 _maybe_mark_result 绑到 engine 上（它是 ToolRunnerMixin 的方法，需要 self）
    import types
    engine._maybe_mark_result = types.MethodType(ToolRunnerMixin._maybe_mark_result, engine)

    results = []

    for name, sample in SAMPLE_RESULTS.items():
        tool = sample["tool"]
        args = sample["args"]
        content = sample["content"]
        raw_size = len(content)

        # ── 方案 A：传统方式（完整结果直接进上下文） ──
        context_a = content  # 这就是传统方式：内容直接进上下文

        # ── 方案 B：标记方式（结果存 workspace，标记进上下文） ──
        marker = engine._maybe_mark_result(tool, args, content, 5)
        if marker == content:
            # 非标记工具：方案 B = 方案 A
            context_b = content
            marked = False
        else:
            context_b = marker
            marked = True

        # ── 验证 load_result 能取回完整内容 ──
        load_ok = False
        if marked:
            # 从 marker 中提取 id
            import re
            m = re.search(r"id:\s*([a-zA-Z0-9_]+)", marker)
            if m:
                marker_id = m.group(1)
                loaded = load_result_execute(marker_id, max_chars=99999)
                # 应该包含原始内容
                # load_result 返回格式是 [FULL RESULT] ... \n\n{content}
                loaded_content = loaded.split("\n\n", 1)[-1] if "\n\n" in loaded else loaded
                # 去掉可能的截断标记
                truncated_marker = "\n...(截断" 
                if truncated_marker in loaded_content:
                    loaded_content = loaded_content.split(truncated_marker)[0]
                load_ok = len(loaded_content) > 0 and (content[:100] in loaded_content or loaded_content[:100] in content)

        saving = (1 - len(context_b) / max(len(context_a), 1)) * 100
        results.append({
            "tool": tool,
            "args": str(args),
            "raw_size": raw_size,
            "marker_size": len(context_b),
            "saving_pct": saving,
            "marked": marked,
            "load_ok": load_ok,
        })

    # ── 打印结果表格 ──
    header = f"{'工具':<20} {'原始大小':>10} {'标记后':>10} {'节省':>8} {'标记?':>5} {'load验证':>8}"
    print(header)
    print("-" * len(header))
    total_raw = 0
    total_marked = 0
    for r in results:
        status = "✅" if r["load_ok"] else ("-" if not r["marked"] else "❌")
        print(
            f"{r['tool']:<20} {format_bytes(r['raw_size']):>10} "
            f"{format_bytes(r['marker_size']):>10} "
            f"{r['saving_pct']:>7.1f}% {'Y' if r['marked'] else 'N':>5} {status:>8}"
        )
        total_raw += r["raw_size"]
        total_marked += r["marker_size"]
    print("-" * len(header))
    total_saving = (1 - total_marked / max(total_raw, 1)) * 100
    print(f"{'合计':<20} {format_bytes(total_raw):>10} {format_bytes(total_marked):>10} {total_saving:>7.1f}%")

    # ── 汇总 ──
    print()
    print("─" * 50)
    print("  结论")
    print("─" * 50)
    marked_count = sum(1 for r in results if r["marked"])
    load_ok_count = sum(1 for r in results if r.get("load_ok"))
    print(f"  - 标记工具: {marked_count}/{len(results)}")
    print(f"  - 非标记工具（execute_terminal 等保持原样）: {len(results) - marked_count}/{len(results)}")
    print(f"  - load_result 验证通过: {load_ok_count}/{marked_count}")
    print(f"  - 总上下文节省: {total_saving:.1f}%")
    print(f"  - 假设 10 次工具调用：传统方式约 {format_bytes(total_raw * 2)}，标记方式约 {format_bytes(total_marked * 2)}")

    # 清理
    shutil.rmtree(tmp_ws, ignore_errors=True)
    ToolRunnerMixin.WORKSPACE_DIR = original_ws

    # 返回是否全部通过
    return all(r.get("load_ok", True) for r in results if r["marked"])


if __name__ == "__main__":
    success = run_benchmark()
    sys.exit(0 if success else 1)
