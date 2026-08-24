"""cache_hit_probe.py — 前缀缓存命中率探测（成本纪律：真 LLM，硬预算）

两段测量：
  A. 真实命中率：从 usage 读 prompt_cache_hit/miss_tokens（COST-1c 已透传）
  B. 前缀漂移点：逐 token 对比相邻调用的 prompt，标出第一个分歧点
     → 直接指向破坏缓存的元凶（哪段变了）

硬预算：单次运行 ≤50k token（多轮太贵，跑最小会话 4 次调用）。
用法：python3 scripts/cache_hit_probe.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BUDGET_TOKENS = 50000


def main():
    from config import API_KEY, API_BASE_URL, API_MODEL_NAME
    from core.llm_caller import create_llm_caller
    from tools import TOOLS_SCHEMA

    if not API_KEY:
        print("未配置 API_KEY，跳过")
        return

    caller = create_llm_caller(API_KEY, API_BASE_URL, API_MODEL_NAME, TOOLS_SCHEMA)

    # 最小会话（4 次调用，同 session_id 走同一前缀缓存）
    session_msgs = [
        [{"role": "system", "content": "你是 Bobo。"},
         {"role": "user", "content": "你好"}],
        [{"role": "system", "content": "你是 Bobo。"},
         {"role": "user", "content": "你好"},
         {"role": "assistant", "content": "你好！有什么可以帮你？"},
         {"role": "user", "content": "帮我看看今天天气"}],
        [{"role": "system", "content": "你是 Bobo。"},
         {"role": "user", "content": "你好"},
         {"role": "assistant", "content": "你好！有什么可以帮你？"},
         {"role": "user", "content": "帮我看看今天天气"},
         {"role": "assistant", "content": "我帮你查天气，稍等。"},
         {"role": "user", "content": "谢谢，顺便推荐个餐厅"}],
    ]

    total_tokens = 0
    prev_prompt = None
    print(f"=== 缓存命中探测（{API_MODEL_NAME}）===")
    for i, msgs in enumerate(session_msgs, 1):
        if total_tokens >= BUDGET_TOKENS:
            print("⚠️ 触达硬预算，停止")
            break
        try:
            resp = caller(msgs, use_tools=False)
        except Exception as e:
            print(f"[调用{i}] 失败: {e}")
            continue
        usage = resp.get("usage") or {}
        total_tokens += usage.get("total_tokens", 0)
        hit = usage.get("prompt_cache_hit_tokens", 0)
        miss = usage.get("prompt_cache_miss_tokens", 0)
        rate = hit / (hit + miss) * 100 if (hit + miss) else None
        # 前缀漂移：与上一调用的 prompt 对比
        cur_prompt = str(msgs)
        drift = ""
        if prev_prompt is not None:
            d = 0
            while d < min(len(prev_prompt), len(cur_prompt)) and prev_prompt[d] == cur_prompt[d]:
                d += 1
            drift = f"· 漂移@字符 {d}（前缀{'稳定' if d > len(prev_prompt)*0.9 else '已断'}）"
        print(f"[调用{i}] hit={hit} miss={miss} "
              f"命中率={f'{rate:.1f}%' if rate is not None else 'N/A'} {drift}")
        prev_prompt = cur_prompt
    print(f"总 token（含重算）≈{total_tokens}（预算 {BUDGET_TOKENS}）")


if __name__ == "__main__":
    main()
