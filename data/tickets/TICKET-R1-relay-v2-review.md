---
ticket: TICKET-R1
title: relay v2 评审转正——结构化通道并入 main（O-2 搭建器前置）
branch: feat/ticket-r1
status: 待施工
author: Kimi 开票（封存分支 feat/team-relay-v2 三 commit 转正评审）
date: 2026-08-10
authorized_paths:
  - tools/team_relay_v2.py
  - tests/
---

# TICKET-R1 relay v2 评审转正

## 一、背景与定位

四 Agent 讨论产出的 relay v2（文件即总线：消息带 ID+单调序号、消费确认 ack、思考流不进通道、屏幕 diff 只做空闲判定）封存在 `feat/team-relay-v2`（三 commit：b9fa652 骨架 356 行 / 00595ce v1 物证收编 / 7004305 引用修复）。O-2 搭建器将用它做多员工调度总线，本票把它评审转正进 main。

## 二、范围裁决（开票即生效）

1. **进 main 的只有 `tools/team_relay_v2.py` + 测试**。v1 物证脚本（ch_relay.py / team_relay.py）**不进 main**——它们已封存在 archive 标签 `archive/team-relay-v2-unauthorized` 与封存分支上，物证使命已完成。
2. **施工方式**：自最新 main（c91ab3a）切 `feat/ticket-r1`，把 `feat/team-relay-v2:tools/team_relay_v2.py`（7004305 版）取过来作为起点——**不是 merge/rebase 那个分支**（它带着 L4 前的旧历史，diff 混乱）。
3. **依赖已闭合**：main 的 `tools/pi_relay.py:62` 已有 `pi_finished`，v2 引用满足；本票不动 pi_relay.py。
4. **与 agent_connect.py 的关系**：v2 是多员工轮巡总线，agent_connect 是双 agent 互传——本票只做一件事：在 v2 文件头部 docstring 写明两者分工与边界（各管什么、什么时候用哪个），不改 agent_connect 代码。深度融合留给 O-2。

## 三、施工内容

### R1-1 代码评审修正（先审后改）

按四 Agent 共识逐条核对 v2 实现，缺什么补什么：

1. 消息带 ID + 单调序号（断点续传/重放去重）
2. 消费确认 ack（转发后标记已消费，防重复注入——v1 hermes 队列堆 10 条的根因）
3. 思考流与正式发言严格分离（结构化通道只收正式发言事件）
4. 屏幕 capture 只做空闲判定+调度触发，不做内容提取
5. unknown pane 永不通过身份复核（L3 铁律沿用）
6. 会话名硬编码检查：`SES = "staff_office"` 等应为参数/配置，不许写死（O-2 搭建器要传不同 session 名）

### R1-2 测试（tests/test_ticket_r1_relay_v2.py）

- ID/序号单调递增、断点续传不丢不重
- ack 消费后不重复转发
- 思考流（💭 块）不进通道
- 空闲判定与内容提取分离
- unknown pane 拒绝
- 会话名参数化
- 全程用临时目录/mock tmux，不碰真实 relay_v2 目录、不碰真实库

### R1-3 验证

- 全量 pytest 零回归（基线 1829 passed / 2 skipped）+ 新增全过
- 真实库三文件 md5 闸门
- 五查汇报附测试原始输出文本

## 四、验收清单

1. 六条评审点逐条汇报（实现状态：已有/补了/不适用，给行号）
2. 测试全过 + 全量零回归 + md5 闸门
3. docstring 写清 v2 与 agent_connect 分工
4. ch_relay/team_relay 未混入分支（`git diff main...HEAD --stat` 只有 v2+测试）
5. 五查汇报 + 测试原始输出

## 五、纪律

- 分支 `feat/ticket-r1` 自最新 main 切出；commit 前核对分支名；未终审不 merge 不 push。
- 不做：agent_connect 改动、/office、搭建器、前端、pi_relay 改动。
- 评审发现 v2 实现有结构性缺陷（非缺漏）→ 停下来汇报，不擅自重写。
