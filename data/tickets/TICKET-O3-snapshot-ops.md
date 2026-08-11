---
ticket: TICKET-O3
title: OFFICE MODE 快照与运营手册——保护路径 md5 快照 + tmux-office skill 定稿
branch: feat/ticket-o3
mode: office（第一张纯 relay 团队票·神经康复仪式）
status: 待施工
author: Kimi 开票（依据设计稿 v0.3.1 路线图 O-3 + owner 2026-08-11 体验指令）
date: 2026-08-11
assignees:
  dispatcher: 派工+收五查（只读）
  staff-a: O3-1 快照机制施工
  staff-b: O3-2 skill 运营手册定稿
  reviewer: 评审挑刺（只读）
authorized_paths:
  - core/command_safety.py
  - core/engine.py
  - data/skill-standards/tmux-office/standard.md
  - tests/
---

# TICKET-O3 快照与运营手册（第一张纯 relay 团队票）

## 一、双重目的

1. **交付 O-3**：执法层的兜底防线——事前拦截只有 6-7 成（bobo 实证），事后快照把漏的抓回来。
2. **神经康复仪式**：relay 修好后第一张**全程 relay 派工**的团队票——不许 tmux 直派（除非 relay 故障，那本身就是验收失败，如实记录降级事件）。派工/汇报/评审全走 relay 通道。

## 二、施工内容

### O3-1 受保护路径快照（staff-a）

- 决策时刻快照：office 角色会话中，每次写类工具调用通过决策链**后**，对 `data/protected_paths.json` 清单内文件做 md5 快照（复用票 B-2 快照机制），写 `data/guardsnap_<sid>.json`（sid 维度滚动保留，7 天）。
- 收工闸比对：回合收工时比对快照与当前 md5，不一致 → 写审计 `office.snap`（含路径/前后 md5/会话）+ 回复中明示告警（不阻断收工——快照是抓漏不是执法，执法在 O-1）。
- 无角色（普通模式）：整段跳过，零开销零行为变化（对照组铁律）。

### O3-2 tmux-office skill 运营手册定稿（staff-b）

- 基于现有 `data/skill-standards/tmux-office/standard.md` 合并定稿，纳入三章新内容：
  1. **执法层摘要**（O-1 矩阵一句话版 + 指向 protected_paths.json，手册不管执法只管引用）
  2. **relay 降级机制**（relay 故障时调度员可 tmux 直派，每次降级必须写审计——今晚实战经验的制度化）
  3. **编制规则**（1 调度+2-3 员工+1 评审标准小队；relay 饱和线 6 人；按模块不切工序派工）
- 手册是建议性文档，不许塞任何"开关/拦截"语义。

### O3-3 测试（staff-a 为主）

- 快照：写后快照生成、收工比对一致零告警、篡改后告警（模拟）、7 天滚动、无角色对照组零开销
- 全量零回归（基线 1989）+ md5 闸门

## 三、验收清单

1. O3-3 测试全过 + 全量零回归 + 真实库 md5 闸门
2. skill 手册三章齐全、无执法语义混入
3. **康复验收**：本票派工/汇报/评审全程 relay 通道——relay 日志四方互通、零双实例、零降级（如发生降级，附事件记录与原因）
4. 评审员独立评审意见落库
5. 五查汇报附测试原始输出

## 四、纪律

- 分支 `feat/ticket-o3` 自最新 main（695b4cf）切出；未终审不 merge 不 push。
- 不做：auto 决策树、O-1/O-2 代码、relay 代码（刚修好，冻它一周）。
- 普通模式零影响对照组每条必配。
