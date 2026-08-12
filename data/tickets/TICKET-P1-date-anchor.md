---
ticket: TICKET-P1
title: injector 常驻日期时间锚点——bobo 不该为"今天周几"调工具
branch: feat/ticket-p1
mode: 单人票（bobo 施工，Kimi 终审）
status: 排队（EV-1 合并后开工）
author: Kimi 开票（EV-1 首跑 E1 题暴露：注入无日期锚点，bobo 必调 get_current_time）
date: 2026-08-12
assignees:
  staff-a: 施工
authorized_paths:
  - core/injector.py
  - tests/
---

# TICKET-P1 日期时间锚点注入

## 一、缺口（EV-1 首跑实证）

E1 题（纯问答零工具）发现：bobo 上下文无日期锚点，问"今天周几"必须调
get_current_time（3 次工具调用）。主流 harness 均在系统提示注入当前时间戳。

## 二、施工内容

- injector 常驻一行锚点：`[NOW] 2026-08-12 18:23 Thursday (Asia/Shanghai)`——
  每轮组装时取当前时间，≤60 字符，计入 prompt.budget（selfmap 相邻段）
- 普通/auto/office 全模式一致注入（无差别基础信息）
- 测试：锚点存在、格式正确、随时间变化、计入 budget、E1 题复测工具调用=0
- 全量零回归（基线 2067）+ md5 闸门

## 三、验收

1. 测试全过 + 全量零回归 + md5 闸门
2. E1 题复测：0 次工具调用答对日期（严格标准恢复）
3. 实弹：新会话问"今天周几"，秒答不调工具（owner 亲测）

## 四、纪律

- 分支 `feat/ticket-p1` 自最新 main 切出；未终审不 merge 不 push。
- 不做：其他注入段调整。
