"""cache_hit_probe2.py — 真实 prompt 形态的缓存命中探测（刀刃式：一次跑完出结论）

复用 engine 的真实上下文组装（系统提示词 + 工具 schema + 注入段），
跑一个真实多轮会话，逐轮报：命中率（usage）+ 前缀漂移段归属。
硬预算：≤60k token，超了即停。
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BUDGET = 60000


def main():
    from config import API_KEY, API_BASE_URL, API_MODEL_NAME
    from core.llm_caller import create_llm_caller
    from core.engine import Engine
    from core.tool_executor import execute_tool
    from tools import TOOLS_SCHEMA
    from tests.mock_llm import text_response  # 仅用于 Engine 构造占位

    caller = create_llm_caller(API_KEY, API_BASE_URL, API_MODEL_NAME, TOOLS_SCHEMA)

    class _Probe:
        def __init__(self, inner):
            self.inner = inner
            self.calls = []
        def __call__(self, messages, **kw):
            resp = self.inner(messages, **kw)
            self.calls.append({"messages": messages, "usage": resp.get("usage") or {}})
            return resp

    probe = _Probe(caller)
    eng = Engine(probe, execute_tool, test_mode=False)
    eng.test_mode = False
    eng.confirm_callback = lambda *a, **k: True
    total = 0
    print(f"=== 真实形态缓存探测（{API_MODEL_NAME}）===")
    turns = ["你好", "帮我看看今天天气", "谢谢，推荐个餐厅", "就用第一家吧"]
    for i, t in enumerate(turns):
        eng.callback = None
        eng.run(t)
        # 本轮产生的调用
        cur = probe.calls
        if not cur:
            print(f"[轮{i+1}] 无 LLM 调用")
            continue
        for j in range(len(cur)):
            c = cur[j]
            u = c["usage"]
            total += u.get("total_tokens", 0)
            hit = u.get("prompt_cache_hit_tokens", 0)
            miss = u.get("prompt_cache_miss_tokens", 0)
            rate = hit / (hit + miss) * 100 if (hit + miss) else None
            # 与前一次调用对比漂移
            drift = ""
            if len(cur) > 1 and j > 0:
                a, b = str(cur[j-1]["messages"]), str(c["messages"])
                d = 0
                while d < min(len(a), len(b)) and a[d] == b[d]:
                    d += 1
                drift = f"· 前缀漂移@{d}字符（{'稳定' if d > len(a)*0.9 else '可能断裂'}）"
            print(f"[轮{i+1}/调{j+1}] hit={hit} miss={miss} 命中率={f'{rate:.1f}%' if rate is not None else 'N/A'} {drift}")
        probe.calls = []
        if total >= BUDGET:
            print(f"⚠️ 触达硬预算 {BUDGET}，停止")
            break
    print(f"总 token ≈{total}（预算 {BUDGET}）")


if __name__ == "__main__":
    main()
