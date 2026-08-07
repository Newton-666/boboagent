# TICKET-E2-④ — 瘦身份段：预付层减药（16 节 → 7 节）

- 分支：`fix/ticket-e2-4-slim-identity`（从最新 main 切出）
- 类型：熵减计划 · 重构期减药（风险最大的一张票，双闸门护航）
- 纪律：禁止 merge、禁止 push、禁止碰 main；完成后五查汇报等 Kimi 终审
- 基线：1501 passed / 2 skipped + **闸门 A/B 基线已落定**（docs/dual-gate-exam.md）

## 哲学（owner 定稿，不许偏离）

预付层只留"没有它模型就不是 bobo"的行为内核。一切"导航类/查询类/手册类"内容已在 GUIDANCE（docs/GUIDANCE.md）里有对应——**搬家不烧书**：从身份段删掉的内容，必须能指出它在 GUIDANCE 或技能标准里的对应位置；指不出的不准删。

## 现状（core/engine.py `_build_system_prompt`，16 节 ~4.5K 字符）

## 保留（7 节，行为内核）

| 节 | 保留理由 |
|---|---|
| 核心原则 | 执行纪律（并行编辑/纯文字=结束/失败诚实）——行为之本 |
| 防循环规则 | 防死循环，行为安全 |
| 对话规则 | 目标跟踪 |
| 收工汇报 | 用户可观测的收工格式，battle-tested |
| 可信度 | 证据纪律、失败报告 |
| 命令安全 | 安全分级不可动 |
| 输出格式 | 输出规范 |

## 退役（9 节，逐一对应去处）

| 节 | 去处（施工时逐条核对原文覆盖） |
|---|---|
| ⚡ 项目任务拆分 | GUIDANCE "## Big tasks"（task_ledger + spawn_worker 已在） |
| 工具结果标记 | GUIDANCE Quick reference "Full tool result: load_result(id)"；"拿不准就加载"精神并入该节一行 |
| 记住指令 | GUIDANCE Memory 节（save_memory 已在） |
| 用户资料 | 同上（target="profile" 细节并入 GUIDANCE Memory 节一行） |
| 技能 | GUIDANCE Skills 节；教学模式触发词（开始教学/保存为 skill）并入 GUIDANCE Skills 节两行 |
| 工具并行 | 核心原则已有并行编辑条款，重复 |
| 会话记忆 | GUIDANCE Notes/Memory 节已覆盖 |
| 代码修改工作流 | 搬家至 data/skill-standards/code-fix/standard.md（已存在，核对覆盖后删身份段原文） |
| 工具使用 | GUIDANCE Quick reference 已覆盖；write_obsidian 4万字符分界等独有细节并入 code-fix 标准 |

## GUIDANCE 同步增补（owner 已授权范围内）

仅允许为上表"并入"目的向 docs/GUIDANCE.md 添加行，每处增补在汇报中列 before/after。**禁止改写 GUIDANCE 既有行的措辞。**

## 验收（双闸门，缺一不可）

1. **考卷自测**：跑闸门 B 六题（docs/dual-gate-exam.md），本地自评每题答案要点仍可从 GUIDANCE/身份段推出；把答案要点对照表附进汇报。
2. **行为回归测试**（新增 tests/）：身份段含 7 保留节标题、不含 9 退役节标题；长度从 ~4.5K 降到 ≤2.5K 字符。
3. 全量 pytest 零回归（基线 1501 + 新增）。
4. 汇报里给出"退役节 → 去处"逐条对照表（每节一行：去处文件+行号证据）。

## Kimi 终审加试（不在 bobo 施工范围）

- 合并后 Kimi 用 DeepSeek 跑道重跑闸门 A 快速版 + 闸门 B 考卷，对比基线分数——分数不掉才算真通过。

## 边界（不许碰）

- 核心原则/防循环/收工汇报/可信度/命令安全/输出格式/对话规则 7 节的**措辞一字不动**（只删节，不改保留节）。
- injector、GUIDANCE 既有行、技能标准匹配算法。

## 五查汇报要求
1. 退役 9 节逐条去处对照表（文件+行号）。
2. GUIDANCE 增补处 before/after。
3. 闸门 B 六题自测答案要点表。
4. 新旧身份段全文字符数对比。
5. 测试清单 + 全量输出 + 分支状态 + 需重启（改 core/ 必是）。
