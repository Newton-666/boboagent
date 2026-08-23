"""startup_smoke.py — 后端启动冒烟测试（owner 2026-08-23：最怕修着修着启动不了）。

五层验证：模块导入 → 工具注册 → Engine 实例化 → 最小会话 → 网关进程启动（gateway.ready）。
用法：python3 scripts/startup_smoke.py
"""
import os
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> int:
    print("=== 启动冒烟测试 ===")
    # 1) 核心模块导入
    import core.engine, core.tool_runner, core.context, core.injector, core.command_safety
    import core.cu_policy, core.loop_detect, core.takeaway_filter
    import core.steps.base, core.steps.final_assembly
    import tools, bobo_tui_gateway.entry, bobo_tui_gateway.server
    print("[1] 核心模块导入 OK")

    # 2) 工具注册（自动发现 + 无悬挂 import）
    from tools import report_load_errors
    warn = report_load_errors()
    print(f"[2] 工具注册 OK（警告: {warn or '无'}）")

    # 3) Engine 实例化
    from core.engine import Engine
    from core.tool_executor import execute_tool
    from tests.mock_llm import MockLLMCaller, text_response
    eng = Engine(MockLLMCaller([text_response("ok")]), execute_tool, test_mode=True)
    print(f"[3] Engine 实例化 OK（state={eng.state}）")

    # 4) 最小会话
    eng.run("你好")
    print(f"[4] 最小会话 OK（state={eng.state}, history={len(eng.history)} 条）")

    # 5) 网关进程启动（gateway.ready 事件 = 启动成功标志）
    entry = os.path.join(os.getcwd(), "bobo_tui_gateway", "entry.py")
    env = dict(os.environ, BOBO_BACKEND="1", BOBO_DATA_DIR=tempfile.mkdtemp(prefix="bobo_smoke_"))
    proc = subprocess.Popen([sys.executable, entry], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    ready = False
    out = ""
    deadline = time.time() + 15
    while time.time() < deadline:
        if proc.poll() is not None:
            out += proc.stdout.read() if proc.stdout else ""
            ready = "gateway.ready" in out
            break
        import select
        r, _, _ = select.select([proc.stdout], [], [], 1.0)
        if r:
            chunk = proc.stdout.readline()
            out += chunk
            if "gateway.ready" in out:
                ready = True
                break
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
    if ready:
        print("[5] 网关进程启动 OK（gateway.ready 已发出）")
        print("=== 冒烟测试通过 ===")
        return 0
    print("[5] 网关启动异常（未收到 gateway.ready）")
    return 1


if __name__ == "__main__":
    sys.exit(main())
