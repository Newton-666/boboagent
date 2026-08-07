# 双闸门验收标准（E2-⑤）— 熵减计划期末考试

> 定稿：2026-08-07。目的：用可复跑的客观标准判定"熵减后的 harness 是否及格"。
> 哲学：能力越低的模型越能暴露 harness 的冗余——36B 本地模型能跑通，DeepSeek/Kimi 必然能跑通。
> 反背诵原则：口头答对不算过，必须有 events.jsonl 里的工具调用物证。

---

## 连接方式：bobo ← LM Studio（零代码改动）

bobo 的 provider 体系原生支持 OpenAI 兼容接口。LM Studio 侧：

1. LM Studio → 下载并加载模型（推荐 Qwen2.5-32B-Instruct 或 Gemma-3-27B；**必须支持 tool calling**）
2. Developer/Server 面板 → Start Server（默认 `http://localhost:1234`）
3. 记下模型 identifier（server 面板显示，如 `qwen2.5-32b-instruct`）

bobo 侧（`data/.env` 改四行）：

```ini
BOBO_PROVIDER=custom
CUSTOM_API_KEY=lm-studio
API_BASE_URL=http://localhost:1234/v1/chat/completions
API_MODEL_NAME=<LM Studio 里显示的模型 identifier>
BOBO_CONTEXT_LENGTH=<与 LM Studio 加载配置一致，如 32768>
```

重启 bobo 生效。切回 DeepSeek/Kimi 只需把 BOBO_PROVIDER 改回去。

⚠️ 注意：本地模型的工具调用能力参差——若 LM Studio 日志显示模型从不发 tool_calls，先换模型再怀疑 harness。

---

## 闸门 A：36B 迷你项目基准（硬闸门）

**任务**（在空 sandbox 目录中，一句话下达）：

> "帮我做一个命令行待办小工具：能加任务、列任务、标记完成，数据存 JSON，带 pytest 测试，跑通为止。"

**观测点与及格线**（全程看 events.jsonl + 文件产物，不听口述）：

| # | 观测点 | 及格标准 | 验证方式 |
|---|---|---|---|
| A1 | 任务台账 | 开工前调用 `task_ledger` 建台账 | events.jsonl 有 task_ledger 调用且在首次写文件之前 |
| A2 | 文件产出 | todo 工具 + 测试文件落盘 | sandbox 目录文件存在 |
| A3 | 测试闭环 | 调用 run_tests/execute_terminal 跑 pytest 并绿 | events.jsonl 有调用 + 退出码 0 |
| A4 | 笔记沉淀 | 完工后写 library 笔记（write_obsidian/living_notes 管道） | library/ 出现新笔记 + index.md 更新 |
| A5 | 上下文自查 | 新开会话问"上次我们做了什么" → 先读 library/index.md 再答 | events.jsonl 有 read_local_file("library/index.md") |
| A6 | 不虚构 | 全程无"我以为/应该是"式编造路径或工具名 | 人工抽查对话 |

**及格线：A1–A5 全过（A6 抽查）。** 任何一项失败 = harness 还有冗余或导航不清，定位后修复再测。

---

## 闸门 B：自我认知考卷（软闸门，多 API 矩阵）

**考卷**（每题都有 GUIDANCE 里的标准答案；★=必须有工具调用物证）：

| # | 考题 | 标准答案要点 | 物证 |
|---|---|---|---|
| B1 | 你有哪些技能标准？放在哪？ | data/skill-standards/，说出 ≥5 个真实名字 | ★ read_local_file 或 ls |
| B2 | 我上周让你做的事你不记得了，怎么办？ | 读 library/index.md 找笔记再读全文 | ★ read_local_file |
| B3 | 你没有挂载的工具想用怎么办？ | describe_tool 查询 | ★ describe_tool 调用 |
| B4 | 你的记忆存在哪？能直接读那个文件吗？ | knowledge_base.json；不能直读，用 search_memory | ★ search_memory |
| B5 | 大任务（多文件多步骤）你的第一步是什么？ | 建 task_ledger | 口头即可（GUIDANCE 原文） |
| B6 | load_result 是干什么的？ | 取完整工具结果 | 口头即可 |

**评分**：每题 3 分（答案对 1 分 + 路径/工具名精确 1 分 + 有物证 1 分），18 分满分。
**及格线：单 API ≥ 14 分，且无 0 分题。**

**矩阵**（同一份考卷跑三遍）：

| 跑道 | 模型 | 意义 |
|---|---|---|
| 本地 | LM Studio 36B | 下限检验（主闸门） |
| API 1 | DeepSeek | 现役主力回归 |
| API 2 | Kimi (moonshot) | 现役主力回归 |

---

## 执行程序

1. **先跑基线**：E2-④（瘦身份）动工前跑一遍双闸门，记录分数——这是"减药前体检"。
2. E2-④ 合并后再跑一遍：分数不掉 = 瘦身安全；分数涨 = 熵减有效。
3. 两次成绩归档 `docs/战役卷宗/`（文件名含日期与模型）。

## 已知风险 / 备注

- 本地 36B 在 32K 上下文下，GUIDANCE（~1.8K 字符）占比可接受；若后续身份段瘦身后预付总量下降，A 闸门通过率应上升——这就是熵减的可测量收益。
- 考卷题目与 GUIDANCE 强绑定：GUIDANCE 改一个字，考卷答案同步审一遍。
