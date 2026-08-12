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

## 二、施工内容

### G1-1 L0 注入段（≤300 字符，常驻）

内容五要素（英文，与 GUIDANCE 语言一致）：
1. 身份：I am bobo, running inside the bobo harness
2. 架构一句话：engine（决策/执法 `_confirm`）→ gateway（会话/rpc）→ TUI 前端（渲染）
3. 闸位置：all enforcement at engine decision chain; tickets authorize paths
4. 绝对边界：protected_paths 只读清单一句话指引
5. 模式指针：当前模式由注入段告示（auto/office），未注入即普通模式

- 常驻注入，走 prompt.budget 审计（LN-4 分段新增 selfmap 段）
- 硬预算 ≤300 字符，超出即测试失败（预算即宪法原则一对上下文的态度）

### G1-2 GUIDANCE.md 指针

- 顶部加两行：宪章指针 + "L0 已常驻，细节才查本文件"的分层说明

### G1-3 测试（F 卷雏形）

- L0 段存在、五要素齐全、≤300 字符、计入 budget
- 闭卷模拟：在不挂载 describe_tool/读文件工具的上下文里，模型能凭 L0 段答出
  闸位置/边界/模式（断言注入段文本包含答案要点即可，模型侧验收由 F 卷题库接续）
- 全量零回归（基线 2016）+ md5 闸门

## 三、验收清单

1. G1-3 测试全过 + 全量零回归 + md5 闸门
2. 实弹：新会话直接问"你的闸在哪个文件、票据授权怎么走"——不翻文件直接答
   （owner 亲测，对照 O-8 施工的考古行为）
3. 五查汇报附测试原始输出

## 四、纪律

- 分支 `feat/ticket-g1` 自最新 main 切出；未终审不 merge 不 push。
- 排期：O-8 → O-7 → G-1（或按老板队列调整，与 O 系零路径交集可并行）。
- 不做：L1/L2 层改造、EVAL 跑道工程、office_manager。
