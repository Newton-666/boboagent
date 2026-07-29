# 上下文实验台 — 实验方案

**基于当前 data/logs/events.jsonl 数据的压缩预算调优指南**

---

## 当前数据概况

| 指标 | 值 |
|------|-----|
| 总事件数 | 12,737 |
| 分析器处理的会话 | 389 |
| 事件类型 | state.change, llm.call, llm.reasoning, llm.stream_stall, tool.exec, engine.thread.exit, engine.thread.start, task.check, task.no_ledger |
| context.compressed | **当前无此事件**（票 T 刚合，未积累数据） |

---

## 实验一：建立基线 — 压缩前数据画像

**目标**：了解当前（无压缩状态下）的 token 消耗模式，为设定压缩预算提供依据。

**执行**：
```bash
python scripts/context_lab.py
```

**输出报表中的关键指标**：
- 每个会话的 `avg_tk/轮` — 平均每回合消耗的 prompt_tokens
- 全量 `平均 token/回合` — 所有会话的全局均值
- `p50(ms)` / `p95(ms)` — LLM 调用耗时分布

**决策依据**：
- 若平均 token/回合 ≈ 60：当前 budget=60 合适，不动
- 若平均 token/回合 << 60：budget 偏大，可调低（如 30~50）
- 若平均 token/回合 >> 60：budget 偏小，压缩触发太频繁

---

## 实验二：单会话深潜 — 找 token 增长异常

**目标**：找到 prompt_tokens 增长最快的会话，分析是否因缺少压缩导致。

**执行**：
```bash
python scripts/context_lab.py --session <top_session_id>
```

**重点关注**：
- `token 累积增长曲线` — 是否每轮都在快速增长
- `msg_count` 变化 — 消息数量是否累积过快
- `回合耗时分布` — 长回合是否集中在会话末尾

---

## 实验三：压缩启用后对比

**目标**：票 T 的 context.budget 开启并运行若干回合后，对比压缩前后的指标变化。

**执行**：
```bash
# 先跑压缩前的快照
python scripts/context_lab.py --json --json-path data/context_before.json

# 等压缩运行一段时间后，跑压缩后对比
python scripts/context_lab.py --json --json-path data/context_after.json

# 对比（手动分析 JSON 或 --compare 模式）
python scripts/context_lab.py --compare --group-by-file data/context_before.json data/context_after.json
```

**需观察的变化**：
- 预期：总 prompt_tokens 增长放缓（压缩有效）
- 预期：avg_tk/轮 下降（每轮消息数减少）
- 警惕：失忆信号（load_result_after_compress > 0）表示 LLM 重复读取已丢失内容

---

## 实验四：budget 灵敏度分析

**目标**：测试不同 budget 值的效果，找帕累托最优解。

**步骤**：
1. 修改 `config.py` 中 `BOBO_CONTEXT_BUDGET` 的值
2. 运行至少 5~10 个真实回合
3. 重新跑分析器
4. 观察 `compression_count`、`efficiency_ratios`、`失忆信号`

**候选 budget 值**：30, 45, 60（当前）, 80, 120

**评估维度**：
| budget | 压缩频率 | avg_tk/轮 | 失忆信号 | 推荐度 |
|--------|---------|-----------|---------|-------|
| 30 | 高 | 低 | 可能高 | 待定 |
| 45 | 中 | 中 | 可能中 | 待定 |
| 60(当前) | 低 | 基线 | 无 | 待定 |
| 80 | 极低 | 近基线 | 无 | 待定 |
| 120 | 几乎不触发 | 基线 | 无 | 待定 |

---

## 实验数据存档建议

```bash
# 每次实验前跑快照
python scripts/context_lab.py --json --json-path "data/context_baseline_$(date +%Y%m%d).json"
```

---

## 已知限制

1. **`context.compressed` 事件暂无数据** — 票 T 刚合，需等新会话积累。分析器已优雅处理（显示 0）。
2. **事件总线不存消息文本** — 失忆关键词检测目前只能用 `load_result` 调用和 `msg_count` 上涨做代理指标。
3. **boot- session_id 沾污** — 引擎启动过程可能产生大量 "boot-" 前缀的短命会话，它们在 `session_id` 上有冲突（多实例共用同一 ID），导致 token 数被聚合到同一个 session row。分析器见啥报啥，请忽略 "boot-" 会话的异常聚合值。
