---
ticket: TICKET-O9
title: 收工闸补账检测在 eval 驱动环境未触发——A2 题 FAIL 根因彻查
branch: feat/ticket-o9
mode: 单人票（bobo 施工，Kimi 终审）
status: 排队
author: Kimi 开票（EV-1 首跑 A2 实证：office_on 驱动下同轮建台账全 done，goal_gate.deny 未触发）
date: 2026-08-12
assignees:
  staff-a: 施工
authorized_paths:
  - core/engine.py
  - tools/eval_runner.py
  - tests/
---

# TICKET-O9 A2 闸未触发彻查

## 一、实证（EV-1 首跑 20260812_183139）

A2 场景（drive: office_on）：bobo 同轮建台账 3 项全标 done（回复原文"台账已建立，
3 项全部标 done"），全程无 goal_gate.deny 事件。O-8 补账检测（同轮批量创建+批量 done
→ deny + ledger_backfill 审计）未触发。

## 二、排查方向（二选一定位）

1. **驱动问题**：eval_runner 的 office_on 驱动未真正翻转 gate 判定的状态源
   （ctx.office_state vs engine 侧读取路径不一致？）
2. **闸条件问题**：O-8 判定内核的时序/轮次条件在真实驱动路径下覆盖不到
   （比如只在特定收口路径检查，eval 的直驱路径绕过了检查点）

定位后修复，并在 eval 环境复测 A2 必须 deny。

## 三、验收

1. 根因写明（驱动 or 闸条件）+ 修复
2. A2 复测：闸 deny 触发，ledger_backfill 审计落盘
3. 全量零回归（基线 2067）+ md5 闸门
4. 五查附原始输出

## 四、纪律

- 分支 `feat/ticket-o9` 自最新 main 切出；未终审不 merge 不 push。
- 排期：EV-1 合并后。
