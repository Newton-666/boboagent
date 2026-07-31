# 票 LN-2S：笔记原料换血 — takeaways → 完整回复全文

## 病灶（真人首考失败）

LN-2R 骨架重写机制上线后，真人笔记 `library/技术研究/矩阵B构造与训练.md` 被判"一塌糊涂"：
- 每条要点只有一句话，信息量远低于 bobo 当轮回复
- 用户原话："笔记起码得和回复的量基本一致，甚至要比回复更多——它要填充东西。
  比回复还短，那笔记的作用是什么？这不是给人看的东西。"

**根因（代码实锤）**：
- `core/engine.py:549`：`_extract_takeaways` 把 user/assistant 消息**各截断到前 300 字**
- takeaways 的 prompt 要求"提取 1-2 条关键结论"——双重压缩
- `write_living_notes(takeaways, ...)` 拿到的只是这两句话 → 笔记 = 压缩的压缩的截断版

**结论**：骨架重写机制（LN-2R）没问题，是喂给它的原料先天贫血。
笔记管线必须与 takeaways 脱钩，改吃本轮完整回复全文。

## 目标

### 1. engine.py 钩子改签名（唯一 core 改动）

`write_living_notes` 调用点（engine.py 约 1054 行）：
- 新增参数 `full_reply: str` —— 本轮 assistant 完整回复全文（不截断）。
  来源与 `_extract_takeaways(fallback_content=...)` 同一内容（history 末条 assistant 或
  `_pending_content`），但**不做 [:300] 截断**。
- takeaways 参数保留（用于主题判定的廉价信号 + 记忆草稿流程不受影响）。

### 2. living_notes.py 重写 prompt 换原料

- `_rewrite_note` 的 user 消息：`旧笔记全文` + `本轮完整回复全文`（不再只是要点列表）
- `_REWRITE_SYSTEM` 增补密度铁律：
  - "笔记的信息量必须 ≥ 本轮回复。回复中的公式、代码、参数、结论、推理链、
    待办，一个都不许丢——你的任务是**组织**它们进骨架章节，不是缩略它们。"
  - "宁多勿少：拿不准是否该记的，记进对应章节。"
  - 过程花絮（如"Bobo承认表述混淆"这类元对话）→ 进时间线或丢弃，不进正文。
- `_write_new_note` 同样：概述章节不再只放要点，放从全文提炼的完整内容。
  新主题也需要 1 次 LLM 成文调用（不再有"免成文"捷径）。

### 3. 成本闸调整

- 每轮每主题仍最多 2 次 LLM 调用（判定 1 + 重写/成文 1），但 prompt 变长。
  不设长度上限截断回复；若回复超过 32000 字符，取前 32000（防爆 token，记 notes.error 事件 data.truncated=true）。

### 4. 旧笔记迁移兼容

存量旧格式笔记（无 version、追加式小节）首次重写仍走 LN-2R 迁移路径
（整篇快照 v1 → 骨架 v2），本票不改该逻辑。

## 边界（不碰）

- `_extract_takeaways` 本身及其 prompt 不动（它服务记忆草稿，职责不变）
- 记忆镜像 memory_mirror、MEMORY.md 不动
- LN-3 蒸馏、LN-4 注入不碰
- 骨架五章节结构不改

## 验收（tmpdir 物理检查 + 密度断言）

1. 钩子传全文：fake engine 场景，回复 2000 字 → write_living_notes 收到的 full_reply 未被截断
2. **密度金标准**：模拟一轮含"3 个公式 + 2 个参数决策 + 1 条推理链"的长回复 →
   重写后笔记正文**字符数 ≥ 回复正文的 60%**，且 3 个公式、2 个决策逐字可在笔记中找到
3. 花絮过滤：回复含"Bobo承认此前表述混淆" → 该句不进 `## 关键结论`（可在时间线或不存在）
4. 新主题成文：首轮笔记的概述不再是单行要点，含多句完整表述
5. 32000 字符截断路径：超长回复 → 截断 + notes.error data.truncated=true + 流程不炸
6. BOBO_LIVING_NOTES=off 零动作
7. library 只读降级不炸
8. 全量测试零回归（基线 1389 passed / 2 skipped）

## 纪律

- 从最新 main 切 `feat/note-source`，开工前 `git branch --show-current` 确认
- 改了 core/engine.py → 五查第 6 项填"是，需重启"
- 五查汇报含 git status 原文 + git branch --show-current 原文
- ⛔ 禁止 merge、禁止 push，等 Kimi 终审
