---
ticket: TICKET-O8
title: office 模式默认启用收工闸 + 事后补账检测
branch: feat/ticket-o8
mode: 单人票（bobo 施工，Kimi 终审）
status: 待施工
author: Kimi 开票（依据 2026-08-11 20:47 实测：office 无 auto 时闸失效 + 台账事后补登记）
date: 2026-08-11
assignees:
  staff-a: 施工
authorized_paths:
  - core/engine.py
  - tests/
---

# TICKET-O8 office 默认收工闸 + 补账检测

## 一、事故背景（2026-08-11 20:47 实测）

owner 新会话只打 `/office`（未打 `/auto`），老板搭建办公室**完成后**才建台账，
3 项创建即全部标 done——事后补登记。根因两层：

1. TICKET-C 收工闸仅在 auto on 时激活；office 模式不带 auto → 完全无闸。
2. 闸的判定只查"缺 verify/evidence 字段"，不查"同轮批量创建+批量 done"的补账时序。

宪法原则一（模式决定能力/执法矩阵）：office = 团队施工模式，收工闸应默认在场。

## 二、施工内容

### O8-1 闸激活条件扩展

- 收工闸激活条件：`proactive.mode != "off"`（auto on）**或** office on（会话级）。
- 普通模式（两者皆无）：整段跳过零开销（对照组铁律不变）。

### O8-2 补账检测

- 判定：台账同一轮内"批量创建且全部/大部直接标 done"（创建与 done 无中间轮次）→
  视为事后补账 → deny 收工 + history 追加指令（要求列出**下一步真实待办**）+
  `goal_gate.deny` 审计（reason=ledger_backfill）。
- 合法场景豁免：resume 恢复的既有台账不算补账（有历史轮次）。

### O8-3 测试

- office on（无 auto）闸生效；office on 补账 deny；resume 豁免；普通模式对照组零开销
- 全量零回归（基线 2016）+ 真实库 md5 闸门

## 三、验收清单

1. O8-3 测试全过 + 全量零回归 + md5 闸门
2. 实弹：office（无 auto）会话里故意事后补账 → 被 deny（终审复验）
3. 五查汇报附测试原始输出

## 四、纪律

- 分支 `feat/ticket-o8` 自最新 main 切出；未终审不 merge 不 push。
- 排期：O-5 → O-7 → O-8。
- 不做：auto 决策树其他闸、injector、前端。
