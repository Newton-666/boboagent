# 票 LN-2R：活体笔记重写机制（追加式 → 进化式）

## 病灶

LN-2（commit 899a76b）的 `tools/living_notes.py` 是追加式 MVP：每轮把要点当子弹点堆到笔记末尾。
实测产出被否决：**简陋、无结构、比回复还简陋，散点罗列不产生逻辑**。
用户原话定调："后面聊的和前面冲突 → 覆盖修正；有缺失 → 追加进去；追加、添加、修正这些能力都得具备，
而不是一直往下罗列。只有'发现之前缺了、追加进去/修正掉'才会有结构。"

**笔记 = 每轮全量进化的结构化文档。更新全自动，绝不逐次问用户。**

## 目标

改造 `tools/living_notes.py`：`_write_note` 从"追加子弹点"改为"骨架重写式"。
已有笔记的主题，每轮拿【旧笔记全文 + 本轮要点】让 LLM 输出**整篇新笔记**：
合并、去重、重构章节、删除被推翻的旧结论、把新信息放进对应章节（不是文末堆）。

### 固定骨架（所有主题笔记统一）

```markdown
---
topic: <主题>
domain: <domain>
created: YYYY-MM-DD
last_touched: YYYY-MM-DD
version: <int，每次重写 +1>
source_sessions: [<session_id>...]
---

## 概述
## 关键结论
## 决策与原因
## 待办与未决
## 时间线
```

- `## 时间线` 保留**追加性质**（每轮一行 `- HH:MM 要点`），其余章节全量进化。
- 空章节直接删掉，不留空标题。

### 重写流程（每轮收工闸后，engine.py 钩子不动）

1. 旧笔记存在 → 先把旧版**整篇快照**存 `library/.history/<domain>/<topic>/v{N}.md`（无限保留，永不删）
2. LLM 调用：prompt = 骨架要求 + 旧笔记全文 + 本轮要点 + 冲突处理指令（见下），输出整篇新笔记
3. **结构校验三拒**（任一命中 → 拒写、保留旧版、发 `notes.error` 事件）：
   - 缺 frontmatter
   - 正文为空
   - 新笔记长度 < 旧版 30%（防 LLM 输出截断毁灭笔记）
4. 校验过 → 原子写（临时文件 + os.replace，与 memory_mirror 同款），version+1，last_touched 更新
5. 发 `notes.updated` 事件，data 带 version、旧长度、新长度

### LLM 重写 prompt 必须包含的冲突处理指令

- 新要点与旧结论冲突 → 用新结论**替换**旧表述，不要两句并列
- 旧章节缺少新要点相关信息 → **追加进对应章节**
- 与本轮无关的旧内容 → 原样保留
- 标有 `· 人手` 后缀的行 / `> 用户修订` 引用块 → **逐字保留，不许改**（人手段落保护）

### 迁移：LN-2 已产出的追加式旧笔记

首次重写时：旧笔记整篇进 `.history` 作 v1，再按骨架重写成 v2。不需要单独迁移脚本。

## 边界（不碰）

- engine.py 的 17 行钩子（write_living_notes 调用点）不动
- LN-3 蒸馏晋升、LN-4 反向注入不在本票
- MEMORY.md 镜像（memory_mirror.py）不动
- 每轮每个主题最多 1 次额外 LLM 调用（成本闸保留）

## 验收（全部 tmpdir 物理检查，禁止 mock 蒙混）

1. 首轮新主题 → 建骨架笔记（frontmatter + 五章节）
2. 第二轮重写 → 旧版出现在 `.history` 且 version+1、last_touched 更新
3. **冲突覆盖**：旧笔记有"方案选 A"，新要点"改选 B"→ 重写后"选 A"句消失、"选 B"在
4. **缺失追加**：新要点属于"待办"→ 出现在 `## 待办与未决` 章节内，不是文末
5. 结构校验三拒各一条测试（缺 frontmatter / 空 / <30%）
6. 人手段落保护：旧笔记含 `· 人手` 行，重写后该行逐字仍在
7. 时间线小节：两轮后有两行，且不被重构
8. BOBO_LIVING_NOTES=off → 零动作
9. library 只读（chmod 444）→ 收工不炸、有 notes.error 事件
10. 全量测试零回归（基线 1378 passed / 2 skipped）

## 纪律

- 从最新 main 切 `feat/note-rewrite`，开工前 `git branch --show-current` 确认
- 改 core/ 若涉及 → 五查第 6 项填"需重启"
- 五查汇报含 git status 原文 + git branch --show-current 原文
- ⛔ 禁止 merge、禁止 push，等 Kimi 终审
