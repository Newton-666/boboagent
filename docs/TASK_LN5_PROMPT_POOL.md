# 票 LN-5：系统提示总池比例化 + prompt.budget 数据分析

## 背景

LN-4 留下了两块明确 deferred 的地基工程，本票一并收口（它们共享同一数据源：
LN-4 埋下的 `prompt.budget` 事件）：

1. **总池 5000 是硬编码拍脑袋值**（`core/injector.py`）。不同模型 context window
   差一个数量级（32k ~ 1M），固定 5000 对小窗口浪费预算、对大窗口浪费能力。
   LN-4 已把共享池改成分段保底，但各段的地板/天花板仍是绝对字符数。
2. **prompt.budget 埋点已积累数据但零消费**。每轮组装的四段字符数、记忆淘汰数、
   笔记指针命中主题全都写在 events.jsonl 里，没人看。比例化参数该定多少，
   必须用这些数据说话，不能再拍脑袋。

## 目标

### A. 总池比例化（core/injector.py）

- 新增配置项 `BOBO_PROMPT_POOL_RATIO`（默认 0.05，即 context window 的 5%）与
  `BOBO_PROMPT_POOL_CHARS`（显式覆盖，优先级高于比例；不设则按比例算）
- 总池 = min(显式覆盖, 比例 × 当前模型 context_window)，下限 3000、上限 20000
  （防呆：窗口读不到/异常时回退 5000，与现状一致）
- 各段地板/天花板改为**总池的比例**，默认值对齐 LN-4 现状换算：
  skill 16%/30%、记忆 20%/50%、笔记指针 6%（300/5000）——比例值写成常量，
  注释注明来源
- 模型 context_window 从哪读：用项目已有的模型配置通道；读不到就走回退值，
  绝不阻塞注入（WARNING + prompt.budget 事件加 `pool_source: "fallback"` 字段）
- prompt.budget 事件扩展字段：`pool_total`、`pool_source`（"override"/"ratio"/"fallback"）

### B. context_lab 消费 prompt.budget（scripts/context_lab.py，纯只读）

新增 `--prompt-budget` 报表模式，按会话/按天统计：

| 指标 | 说明 |
|---|---|
| 总池实际用量分布 | total_chars 的 p50/p95/max，对照 pool_total 的利用率 |
| 分段占用 | identity/skills/memory/note_pointers 四段各自 p50/p95 |
| 记忆淘汰压力 | evicted > 0 的轮次占比、平均淘汰条数（淘汰频繁 = 记忆天花板该抬） |
| skill 截断频率 | truncated=true 占比（频繁 = skill 段该抬或该减注入） |
| 笔记指针命中率 | note_pointers.count > 0 的轮次占比、主题 top 榜 |

- 复用现有 `--since` / `--session` 过滤；零新增依赖
- 报表末尾输出一行**调参建议**（哪段最接近天花板就建议抬哪段，附数据依据）

## 边界（不碰）

- 各段内容生成逻辑不动（记忆排序、skill 相关度、指针格式都保持现状）
- 历史层压缩（context.budget=60）不动
- living_notes / MEMORY.md 镜像不动
- 默认值换算后必须与 LN-4 现状等价（5000 池时各段数值不变）——行为零变化是默认路径

## 验收（隔离环境物理检查）

1. 比例化正确性：mock context_window=128000 → 池=6400；=32000 → 池=3000（触下限）；
   读不到窗口 → 5000 + pool_source=fallback
2. 显式覆盖：BOBO_PROMPT_POOL_CHARS=8000 → 池=8000，pool_source=override
3. **默认等价性（金标准）**：不设任何新环境变量、窗口回退 5000 时，
   各段地板/天花板数值与 LN-4 现状逐一相等（800/1500、1000/2500、300）
4. 保底仍成立：记忆吃满场景下 skill ≥ 地板、指针段仍在（LN-4 金标准回归）
5. prompt.budget 事件带 pool_total/pool_source，值与实测一致
6. context_lab --prompt-budget 用真实 events.jsonl 跑出不报错；
   构造样例数据断言各指标计算正确（tmp_path）
7. 全量 pytest 零回归（基线 1415 passed / 2 skipped）+ 新增测试全绿，连跑 3 次
8. 改了 core/ → 五查第 6 项填"是，需重启"

## 纪律

- 从最新 main 切 `feat/prompt-pool-ratio`，开工第一件事 `git branch --show-current` 确认
- 五查汇报含 git status 原文 + git branch --show-current 原文
- ⛔ 禁止 merge、禁止 push，完成后 `git checkout main` 归位，等 Kimi 终审
