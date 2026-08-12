---
ticket: TICKET-G1
title: L0 自我地图常驻注入——agent 对自身架构/能力/边界的肌肉记忆
branch: feat/ticket-g1
mode: 单人票（bobo 施工，Kimi 终审）
status: 待施工
author: Kimi 开票（依据 2026-08-12 O-8 施工实证：翻 gatewayClient.ts 找 engine 的闸，L0 掉进 L2）
date: 2026-08-12
assignees:
  staff-a: 施工
authorized_paths:
  - core/injector.py
  - docs/GUIDANCE.md
  - tests/
related: docs/EVAL_DESIGN.md §四（F 卷即本票验收）
---

# TICKET-G1 L0 自我地图常驻注入

## 一、设计标准（owner 原话，即验收标准）

对自我的认知"不需要思考、不需要去检查的情况下都应该知道"——
"我还有这个工具吗让我去查一查"是事故级体验。

## 二、施工内容（母子结构，owner 2026-08-12 审定 SELF.md 后升级）

母文档已定稿入库：`docs/SELF.md`（commit 8b3ae58，六章 + 顶部 L0 段）。
本票只交付**机制**，文档内容本身不许改（改动需 owner 终审，同宪法）。

### G1-1 L0 常驻注入（≤300 字符硬预算）

- injector 常驻注入 SELF.md 顶部 `[SELF]` 段的**原文**（不许改写、不许摘要——母子同源）
- 走 prompt.budget 审计（selfmap 段）；>300 字符即测试失败

### G1-2 章节触发展开（L1）

- 任务涉及对应主题时注入该章全文：改 engine/gateway/TUI → §2 架构章；
  崩溃排查/测试汇报 → §5 自救章；执法/票据/角色 → §4 边界章
- 触发关键词表写在 injector 内，测试覆盖每章至少一条触发路径 + 无触发不注入对照

### G1-3 GUIDANCE.md 指针

- 顶部加两行：宪章指针 + "SELF L0 已常驻，细节才查本文件"

### G1-4 同步锁测试（关键）

- 断言 L0 段与 SELF.md 顶部代码块**逐字节一致**（改一边不改另一边 → 测试红）
- 断言 L0 每个声明可追溯到章节（关键词映射表）
- 常驻/触发的 budget 记账；全量零回归（基线 2030）+ md5 闸门

## 三、验收清单

1. G1-3 测试全过 + 全量零回归 + md5 闸门
2. 实弹：新会话直接问"你的闸在哪个文件、票据授权怎么走"——不翻文件直接答
   （owner 亲测，对照 O-8 施工的考古行为）
3. 五查汇报附测试原始输出

## 四、纪律

- 分支 `feat/ticket-g1` 自最新 main 切出；未终审不 merge 不 push。
- 排期：O-8 → O-7 → G-1（或按老板队列调整，与 O 系零路径交集可并行）。
- 不做：L1/L2 层改造、EVAL 跑道工程、office_manager。
