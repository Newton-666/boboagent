---
ticket: TICKET-EV1
title: EVAL 跑道 v1——考题执行器 + A/E 自动判分 + 冒烟合卷
branch: feat/ticket-ev1
mode: 单人票（bobo 施工，Kimi 终审）
status: 待施工（题库 docs/EVAL_QUESTIONS.md 待 owner 审定后开工）
author: Kimi 开票（EVAL_DESIGN §五 落地次序第 3 步）
date: 2026-08-12
assignees:
  staff-a: 施工
authorized_paths:
  - tools/eval_runner.py
  - data/eval/
  - tests/
---

# TICKET-EV1 EVAL 跑道 v1

## 一、目标

让 `docs/EVAL_QUESTIONS.md` 的 15 题可以**一键跑分**：A 卷 8 题 + E 卷 3 题全自动判分，
B 卷 4 题半自动（pytest 判据自动、改动行数人核），F 卷 3 题录实战结果。

## 二、施工内容

### EV1-1 考题格式

- `data/eval/questions/*.yaml`：每题一文件（id/scene/expected/judge 规则/origin 血案号）
- judge 规则类型：tool_call_count / event_exists / file_md5 / reply_contains / pytest_green

### EV1-2 执行器（tools/eval_runner.py）

- 逐题：隔离环境（临时 worktree + 临时 library/data，md5 闸门纪律）→ 驱动 bobo
  会话执行场景 → 采集工具调用/事件/回复 → 按 judge 规则打分 → 汇总报告
- 输出 `data/eval/runs/<timestamp>.json`：每题 通过/失败 + 证据指针
- 冒烟模式：`--smoke` 只跑 ≤15 分钟精选子集（A1/A2/A3/E1/E2 + B1）

### EV1-3 基线与报告

- 首跑结果=基线写入 `data/eval/baseline.json`；之后跑分输出 Δ 对比
- 报告落 library/agent开发/EVAL-首跑报告.md

### EV1-4 测试

- 执行器自测：判分规则五种类型各有单测；隔离环境不碰真实库（md5 闸门）
- 全量零回归（基线 2050）+ md5 闸门

## 三、验收清单

1. EV1-4 测试全过 + 全量零回归 + md5 闸门
2. 首跑 15 题全执行，报告落库（分数多少都接受——首跑是基线不是审判）
3. 冒烟模式 ≤15 分钟实测
4. 五查汇报附测试原始输出 + 首跑报告路径

## 四、纪律

- 分支 `feat/ticket-ev1` 自最新 main 切出；独立 worktree 施工；未终审不 merge 不 push。
- 不做：轨迹回放采集器、扰动器（下一票 EV-2）、C/D 卷跑道。
- 考题内容冻结：以 owner 审定的 EVAL_QUESTIONS.md 为准，施工中发现题目不可判分
  如实上报，不擅自改题。
- **考题保密纪律（owner 2026-08-12 裁决）**：考题内容/judge 规则只允许存在于
  `data/eval/` 工程目录，**禁止写入 library/ 或 knowledge_base**（防止应考 bobo
  开卷）；五查汇报引用题目只写题号不写题干全文。
