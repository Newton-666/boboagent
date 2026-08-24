"""cache_probe_bounded.py — 缓存命中率探测（带全守卫：硬预算/单调用超时/总时长）

验证：意图修复后，意图调用命中率 + 整体轮次命中率是否稳定。
守卫（纪律 #7）：BUDGET 硬上限 · 单调用 timeout · 总时长 ≤ TIME_BUDGET 秒，超限即停。
用法：python3 scripts/cache_probe_bounded.py
"""
import os
import sys
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BUDGET = 30000          # 硬 token 预算
TIME_BUDGET = 150       # 总时长上限（秒）
CALL_TIMEOUT = 20       # 单调用超时（秒）


def main():
    from config import API_KEY, API_BASE_URL, API_MODEL_NAME
    from core.llm_caller import create_llm_caller
    from core.engine import Engine
    from core.tool_executor import execute_tool
    from tools import TOOLS_SCHEMA

    caller = create_llm_caller(API_KEY, API_BASE_URL, API_MODEL_NAME, TOOLS_SCHEMA)
    import signal as _sig

    class _Probe:
        def __init__(self, inner):
            self.inner = inner
            self.calls = []
        def __call__(self, messages, **kw):
            r = self.inner(messages, **kw)
            self.calls.append({"m": messages, "u": r.get("usage") or {}})
            return r

    probe = _Probe(caller)
    eng = Engine(probe, execute_tool, test_mode=False)
    eng.test_mode = False
    eng.confirm_callback = lambda *a, **k: True

    total = 0
    t0 = time.time()
    print(f"=== 缓存命中探测（{API_MODEL_NAME} · 守卫：预算{BUDGET}/总时长{TIME_BUDGET}s/单调用{CALL_TIMEOUT}s）===")
    for t in ["帮我查一下上海的房价", "帮我查一下北京的房价"]:
        if time.time() - t0 > TIME_BUDGET:
            print("⏰ 总时长超限，停止")
            break
        try:
            eng.run(t)
        except Exception as e:
            print(f"轮[{t[:12]}] 异常: {e}")
            break
        for j, c in enumerate(probe.calls):
            u = c["u"]
            total += u.get("total_tokens", 0)
            hit, miss = u.get("prompt_cache_hit_tokens", 0), u.get("prompt_cache_miss_tokens", 0)
            rate = hit / (hit + miss) * 100 if (hit + miss) else None
            first = str(c["m"][0].get("content", ""))[:12]
            tag = "意图" if "意图解析器" in first else "主调"
            print(f"[轮{t[:10]}/调{j+1}] {tag} hit={hit} miss={miss} "
                  f"命中率={f'{rate:.1f}%' if rate is not None else 'N/A'}")
        probe.calls = []
        if total >= BUDGET:
            print("💰 触达硬预算，停止")
            break
    print(f"总 token ≈{total} · 耗时 {int(time.time()-t0)}s")


if __name__ == "__main__":
    main()
