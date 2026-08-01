# 票 TICKET-024：token 驱动三层压缩——度量单位从"条数"换成"token"

## 背景

pi agent 审计结论（Kimi 已复核数据）：压缩策略的根病是**度量单位用错**——
"60 条消息"与 token 毫无关系，工具密集会话 60 条可能只有 2 万 token
（压太早、慢性失忆），长文本会话 60 条可能 10 万 token（压太晚、烧钱）。
TICKET-023 已修窗口/空转/零摘要兜底，本票做结构性改革。

依赖：TICKET-023 已合并（窗口修正 + 估算器补丁是本票地基）。

## 目标

### A. 触发条件改 token 驱动（条数降级为兜底）

```
预算 = (context_length − max_tokens 预留 − 固定开销) × 0.7
固定开销 = 工具 schema + system prompt + 记忆注入（实测 ≈20~25K token）
触发 = history 估算 token > 预算
兜底 = 消息条数 > 200 硬上限（保留现有行为）
```

- 每轮入口算一次；BOBO_CONTEXT_BUDGET 环境变量保留为"条数兜底"的覆盖项
- 压缩目标：压缩后 history ≤ 预算 × 25%（数据依据：历史最佳一次 15.5%
  保留率后工作正常、失忆信号为零）

### B. 三层分层保留

| 层 | 内容 | 预算占比 |
|---|---|---|
| 层0 逐字保留 | 最近消息按 token 计，约 15K token（≈15~20 条） | ~18% |
| 层1 分段摘要 | 中段每 20~30 轮一条结构化摘要，100~300 token/段 | ~5% |
| 层2 极简摘要 | 最旧段只留 Active Task / Completed / Key Decisions 要点 | ~2% |

- 二次压缩时：层1 段落达到 5 条以上 → 合并下沉为层2（治"摘要堆积永不整合"）
- 工作锚点（TICKET-020）继续豁免，不计入层预算

### C. 估算器彻底校准（二选一，施工时拍板并写理由）

- tiktoken（cl100k_base 近似）；或
- 023 的启发式补丁 + 用 llm.call 的 prompt_tokens 实测值做在线校准
  （滑动窗口比率，events.jsonl 里有真实反馈信号）

### D. 压缩沉淀记忆（打通上下文 → 记忆）

LLM 压缩调用同一次产出"摘要 + 值得沉淀条目"（关键决策/用户偏好），
以信号分 100 写入 knowledge_base.json——会话归档后知识不再断线。
写入走 v5_memory 现有 API，失败静默降级不阻塞压缩。

## 边界（不碰）

- 工作锚点（020）、失忆协议（021）、会话笔记台账（022）逻辑不动
- 压缩归档 JSONL 不动；TUI 展示不动

## 验收

1. token 触发：构造 history 估算 token 超预算 → 压缩；条数 61 但 token
   远低于预算 → 不压（条数不再单独触发，200 硬上限除外）
2. 压缩率：构造 100 条混合历史（含工具/长文本）→ 压缩后 ≤ 预算 25%，
   层0 逐字保留最近内容完整
3. 摘要合并：连续触发 3 次压缩 → 层1 段合并下沉层2，[对话历史摘要]
   消息总数 ≤ 层1 上限 + 层2 一条
4. 记忆沉淀：mock LLM 返回沉淀条目 → knowledge_base.json 出现对应条目
   信号分 100；LLM 失败 → 压缩正常完成无沉淀
5. 事件：context.compressed 补 layer_stats（各层 token）字段
6. 全量 pytest 零回归；用真实 events.jsonl 回放 3 个高频压缩会话，
   新策略下压缩次数与平均保留率写进五查汇报（与 61 次/75% 基线对比）
7. 改 core/ → 五查第 6 项填"是，需重启"

## 纪律

- 从最新 main 切 `feat/ticket-024-token-compression`，开工先 `git branch --show-current`
- ⛔ 禁止 merge、禁止 push 到 main，完成后 `git checkout main` 归位，等 Kimi 终审
- 五查汇报含 git status 原文 + git branch --show-current 原文
