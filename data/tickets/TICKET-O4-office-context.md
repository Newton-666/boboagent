---
ticket: TICKET-O4
title: OFFICE MODE 上下文注入——office on 时模型必须知道自己处在 office 模式
branch: feat/ticket-o4
mode: 单人票（bobo 施工，Kimi 终审）
status: 待施工
author: Kimi 开票（依据 2026-08-11 实测事故：owner /office 后老板说"没看到任务内容"，拿昨天笔记当待办）
date: 2026-08-11
assignees:
  staff-a: 施工
authorized_paths:
  - core/injector.py
  - bobo_tui_gateway/server.py
  - tests/
---

# TICKET-O4 office 上下文注入

## 一、事故背景（为什么要做）

2026-08-11 14:33 实测：owner 输入 `/office`（底栏 OFFICE 已亮）+ `/auto`，说"两个 worker 就行"，
老板的回复是"我这边没有看到任务内容——台账是空的，记忆里也没有待办任务"，然后连续 23 次
工具调用翻笔记考古，要把**已合并的阶段 0 / G2 当成待办任务**。

根因实锤：`/office` 只翻转了 gateway 会话状态 + 底栏指示（O-2），**模型上下文里没有任何
office 模式的注入**（core/injector.py、core/engine.py 零处引用 office_state）。模型不知道
自己是老板、不知道搭建流程、不知道"两个 worker"是编制需求。

## 二、施工内容

### O4-1 状态 plumbing

- `bobo_tui_gateway/server.py`：office_state 翻转时（含 resume/activate 恢复路径），把
  `office_on: bool` 写入 engine 会话上下文（ctx 字段，与现有 proactive.mode 同级）。

### O4-2 injector 注入

- `core/injector.py`：ctx.office_on 为真时，注入一段固定告示（≤300 字符），内容四要素：
  1. 模式名：当前处于 OFFICE MODE（会话级，owner 用 /office 显式开启）
  2. 身份：你是老板（owner 的直接对话方），不是员工
  3. 职责：听懂 owner 的编制需求（几人/什么角色）→ 用 office_manager 搭建办公室 →
     relay 派工 → 收五查汇报 → 呈交 owner 终审
  4. 边界：普通对话/笔记考古不是本模式职责；owner 未给任务时先问清需求，不自行翻旧账
- office off / 普通模式：**零注入**（对照组铁律——连字段都不读）。
- 注入段走 prompt.budget 预算审计（与 LN-4 分段一致），不参与记忆信号排序。

### O4-3 测试

- office on → 注入存在且含四要素；office off → 零注入（对照组）
- resume/activate 恢复后注入状态正确
- 注入段计入 prompt.budget 事件
- 全量零回归（基线 1989）+ 真实库 md5 三文件闸门

## 三、验收清单

1. O4-3 测试全过 + 全量零回归 + md5 闸门
2. 实弹：重启 bobo → /office → 说"两个 worker"→ 老板应直接问编制细节或用
   office_manager，不得翻笔记考古（终审时 owner 亲测，附对话记录）
3. 五查汇报附测试原始输出

## 四、纪律

- 分支 `feat/ticket-o4` 自最新 main 切出；未终审不 merge 不 push。
- 不做：office_manager 逻辑、relay、O-3 快照（在隔壁票）、前端。
- 与 O-3 并行不撞车（authorized_paths 零交集）。
