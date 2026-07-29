# 票 Y：上下文实验台 — 用摄像头数据找压缩最优解

**优先级**：中（数据平台，不急着上）｜ **风险**：低（纯只读分析，不动引擎）
**分支**：`feat/context-lab` ｜ **禁止**：merge / push，完成后五查汇报 + git status 原文等 Kimi 终审
**开工铁律**：第一件事 `git branch --show-current` 确认在 feat/context-lab；commit 完报告并 `git checkout main` 归位 HEAD。

---

## 一、背景

事件总线（`data/logs/events.jsonl`）已积累全部所需观测数据：llm.call（prompt_tokens / msg_count / duration_ms）、context.compressed（pre/post 条数与 token）、tool.exec、engine.thread.exit（reason）。票 T 的压缩预算默认 60 是拍脑袋值，要用真实数据找最优。

## 二、交付物一：分析器 `scripts/context_lab.py`

只读脚本（不动任何引擎代码），用 duckdb 或 pandas 直接查 events.jsonl，输出一份终端报表（可选 --json 导出），按会话分组统计：

| 指标 | 说明 | 来源 |
|---|---|---|
| 会话总 prompt_tokens | 烧钱主指标 | llm.call.prompt_tokens 求和 |
| 会话总 LLM 调用数 / 工具调用数 | 工作量 | llm.call / tool.exec 计数 |
| token 增长曲线 | 每会话按时间序列的 prompt_tokens（--ascii-plot 画简易曲线） | llm.call |
| 压缩次数与间隔 | 每会话 context.compressed 次数、距上次压缩的轮数 | context.compressed |
| 压缩效率 | post_tokens/pre_tokens 比值分布 | context.compressed |
| 失忆信号（两个代理指标） | ①压缩后 10 轮内 load_result 调用次数；②用户消息命中"说过|前面|已经告诉|我不是说了"模式计数 | tool.exec(name=load_result) / llm.call 的 msg 文本（若事件无文本则只做①） |
| 故障统计 | engine.thread.exit 各 reason 分布 | engine.thread.exit |
| 回合耗时分布 | llm.call.duration_ms 的 p50/p95 | llm.call |

要求：
- 支持 `--since 2026-07-29` / `--session <sid>` 过滤
- 支持 `--compare`：把会话按当时的 BOBO_CONTEXT_BUDGET 值分组对比（预算值可从 context.compressed 事件推断或从会话首条记录注入；若不可得，支持 `--group-by-file A.jsonl B.jsonl` 多文件对比模式）
- 零依赖新增：用项目 .venv 已有的 duckdb/pandas
- 写测试：构造样例 events.jsonl（tmp_path），断言各指标计算正确

## 三、交付物二：实验方案 `docs/context-lab-plan.md`

四组对照实验设计：
- A 组 BOBO_CONTEXT_BUDGET=30 / B=45 / C=60（现状）/ D=90
- 每组使用 2~3 天的真实使用，不刻意演戏
- 切换方式：桌面端启动前设环境变量（写清楚操作步骤）
- 评审会判据：烧钱曲线 vs 失忆信号的交点；p95 回合耗时不得劣于现状 20%
- 每个实验日结束跑一次 context_lab.py --since 今天，报表存档到 docs/context-lab/

## 四、验收标准

1. 用真实 events.jsonl（当前 data/logs/ 里已有的）跑分析器，输出完整报表不报错
2. 测试覆盖：各指标计算 / 过滤 / 对比模式，tmp_path 构造样例
3. 全量 pytest 基线 1047 passed / 2 skipped 不回归
4. 不改 core/ 任何文件（纯 scripts/ + docs/ + tests/），五查第 6 项填"否"
5. 报表截图或文本附在五查汇报里（用真实数据跑的一次）

## 五、交付清单

- scripts/context_lab.py
- tests/test_context_lab.py
- docs/context-lab-plan.md
- 五查汇报 + git status 原文 + git branch --show-current 原文
